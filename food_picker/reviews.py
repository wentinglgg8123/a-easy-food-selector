"""Permanent shared reviews stored through a server-side Supabase REST client.

No local fallback is provided: successful submissions always come from the
configured remote database. The service-role key is only used in HTTP headers.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from http.client import HTTPException
import json
import math
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID


class ReviewError(RuntimeError):
    """A safe user-facing error without remote response bodies or credentials."""


class ReviewValidationError(ReviewError):
    """A review or query must be corrected before contacting the database."""


class _MissingRatingsRPC(ReviewError):
    """Only the versioned read endpoint is missing; legacy reads may still work."""


@dataclass(frozen=True)
class Review:
    id: str
    restaurant_id: str
    author: str
    body: str
    created_at: str
    rating: float | None = None


_RESTAURANT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", re.ASCII)
_MAX_RESPONSE_BYTES = 512_000
_CONFIG_ERROR = "公開留言服務設定不完整或格式有誤，請聯絡網站管理員。"
_REMOTE_ERROR = "公開留言服務暫時無法使用，請稍後再試。"
_MIGRATION_ERROR = "留言評分功能尚未完成資料庫升級，請聯絡網站管理員；既有評論會保留。"


class _NoRedirect(HTTPRedirectHandler):
    """Never forward the service-role headers to a redirect destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_request(request: Request, *, timeout: float):
    # The default HTTPS handler keeps normal certificate and hostname checking.
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


def _restaurant_id(value: object) -> str:
    if not isinstance(value, str) or not _RESTAURANT_ID.fullmatch(value):
        raise ReviewValidationError("餐廳識別碼無效，請重新整理頁面後再試。")
    return value


def _submission_id(value: object) -> str:
    if not isinstance(value, str):
        raise ReviewValidationError("這次送出的識別碼無效，請重新整理頁面後再試。")
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        raise ReviewValidationError("這次送出的識別碼無效，請重新整理頁面後再試。") from None


def _author(value: object) -> str:
    if not isinstance(value, str):
        raise ReviewValidationError("暱稱請使用文字，最多 40 字。")
    value = value.strip() or "訪客"
    if len(value) > 40:
        raise ReviewValidationError("暱稱最多 40 字，請縮短後再送出。")
    return value


def _body(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 500:
        raise ReviewValidationError("留言請填寫 1–500 字的文字內容。")
    return value.strip()


def _name(value: object) -> str:
    if not isinstance(value, str) or len(value.strip()) > 200:
        raise ReviewValidationError("餐廳名稱格式有誤，請重新整理頁面後再試。")
    return value.strip()


def _rating(value: object) -> float | None:
    """Half stars are exactly representable, so no rounding or tolerance is needed."""
    if value is None:
        return None
    message = "評分請選擇 1–5 顆星，每次以半顆星為單位。"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReviewValidationError(message)
    try:
        number = float(value)
    except OverflowError:
        raise ReviewValidationError(message) from None
    if not math.isfinite(number) or not 1 <= number <= 5 or not (number * 2).is_integer():
        raise ReviewValidationError(message)
    return number


def _base_url(value: object) -> str:
    if not isinstance(value, str):
        raise ReviewError(_CONFIG_ERROR)
    try:
        cleaned = value.strip()
        parsed = urlsplit(cleaned)
        valid = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment
            and not any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in cleaned)
            and not any(char.isspace() or char == "\\" for char in parsed.netloc)
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ReviewError(_CONFIG_ERROR)
    return value.strip().rstrip("/")


class SupabaseReviewStore:
    """Small bounded client for the schema in ``sql/reviews.sql``."""

    def __init__(
        self,
        url: str,
        service_role_key: str,
        *,
        transport: Callable | None = None,
        timeout: float = 8.0,
    ) -> None:
        self._url = _base_url(url)
        if not isinstance(service_role_key, str) or not service_role_key.strip():
            raise ReviewError(_CONFIG_ERROR)
        if any(char.isspace() for char in service_role_key):
            raise ReviewError(_CONFIG_ERROR)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 15:
            raise ReviewError(_CONFIG_ERROR)
        self._key = service_role_key
        self._transport = transport if transport is not None else _open_request
        self._timeout = float(timeout)
        self.ratings_ready = True

    def _request(self, method: str, path: str, payload: object = None, *, prefer: str | None = None) -> object:
        headers = {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer is not None:
            headers["Prefer"] = prefer
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(self._url + path, data=data, headers=headers, method=method)
        try:
            with self._transport(request, timeout=self._timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                raise ReviewError(_REMOTE_ERROR)
            return json.loads(raw)
        except HTTPError as error:
            if error.code == 404 and path == "/rest/v1/rpc/food_picker_reviews_for_restaurants_v2":
                raise _MissingRatingsRPC(_MIGRATION_ERROR) from None
            else:
                message = _CONFIG_ERROR if error.code in (401, 403, 404) else _REMOTE_ERROR
            raise ReviewError(message) from None
        except (URLError, OSError, TimeoutError, HTTPException, ValueError, TypeError, UnicodeError):
            raise ReviewError(_REMOTE_ERROR) from None

    @staticmethod
    def _review(value: object) -> Review:
        """Treat remote records as untrusted, even when the schema validates them."""
        try:
            if not isinstance(value, dict):
                raise ValueError
            review_id = _submission_id(value["id"])
            restaurant_id = _restaurant_id(value["restaurant_id"])
            author = _author(value["author"])
            body = _body(value["body"])
            rating = _rating(value.get("rating"))
            created_at = value["created_at"]
            if not isinstance(created_at, str):
                raise ValueError
            timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if timestamp.utcoffset() is None:
                raise ValueError
        except (KeyError, ValueError, TypeError, ReviewValidationError):
            raise ReviewError(_REMOTE_ERROR) from None
        return Review(review_id, restaurant_id, author, body, created_at, rating)

    def load_reviews(self, restaurant_ids: Sequence[str], limit: int = 3) -> dict[str, list[Review]]:
        """Fetch up to ten newest reviews each for at most 24 restaurant IDs."""
        if isinstance(restaurant_ids, (str, bytes)) or not isinstance(restaurant_ids, Sequence):
            raise ReviewValidationError("請提供餐廳識別碼清單。")
        ids = list(dict.fromkeys(_restaurant_id(value) for value in restaurant_ids))
        if len(ids) > 24:
            raise ReviewValidationError("一次最多讀取 24 間餐廳的留言。")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise ReviewValidationError("每間餐廳只能讀取 1–10 則最新留言。")
        result: dict[str, list[Review]] = {restaurant_id: [] for restaurant_id in ids}
        if not ids:
            return result
        arguments = {"restaurant_ids": ids, "review_limit": limit}
        try:
            payload = self._request(
                "POST", "/rest/v1/rpc/food_picker_reviews_for_restaurants_v2", arguments,
            )
        except _MissingRatingsRPC:
            self.ratings_ready = False
            payload = self._request(
                "POST", "/rest/v1/rpc/food_picker_reviews_for_restaurants", arguments,
            )
        else:
            self.ratings_ready = True
        if not isinstance(payload, list):
            raise ReviewError(_REMOTE_ERROR)
        seen: set[str] = set()
        for value in payload:
            if not self.ratings_ready and isinstance(value, dict):
                value = {**value, "rating": None}
            review = self._review(value)
            if review.restaurant_id not in result:
                raise ReviewError(_REMOTE_ERROR)
            if review.id not in seen:
                result[review.restaurant_id].append(review)
                seen.add(review.id)
        for restaurant_id, reviews in result.items():
            result[restaurant_id] = sorted(
                reviews, key=lambda review: (datetime.fromisoformat(review.created_at.replace("Z", "+00:00")), review.id), reverse=True,
            )[:limit]
        return result

    def add_review(
        self,
        restaurant_id: str,
        author: str,
        body: str,
        submission_id: str,
        restaurant_name: str = "",
        *,
        rating: float | None = None,
    ) -> Review:
        """Persist once per submission UUID, recovering safely from uncertain retries."""
        restaurant_id = _restaurant_id(restaurant_id)
        review_id = _submission_id(submission_id)
        author, body, restaurant_name = _author(author), _body(body), _name(restaurant_name)
        rating = _rating(rating)
        if rating is not None and not self.ratings_ready:
            raise ReviewError(_MIGRATION_ERROR)
        payload = {
            "id": review_id, "restaurant_id": restaurant_id, "restaurant_name": restaurant_name,
            "author": author, "body": body,
        }
        if rating is not None:
            payload["rating"] = rating
        response = self._request(
            "POST", "/rest/v1/restaurant_reviews?on_conflict=id", payload,
            prefer="resolution=ignore-duplicates,return=representation",
        )
        if response == []:
            query = urlencode({"id": f"eq.{review_id}", "select": "*", "limit": 1})
            response = self._request("GET", "/rest/v1/restaurant_reviews?" + query)
        if not isinstance(response, list) or len(response) != 1:
            raise ReviewError(_REMOTE_ERROR)
        review = self._review(response[0])
        if review.id != review_id or review.restaurant_id != restaurant_id:
            raise ReviewError(_REMOTE_ERROR)
        return review


def configured_review_store(config: Mapping[str, object] | None = None) -> SupabaseReviewStore | None:
    """Use explicit server secrets first, then existing environment bindings.

    Missing credentials disable public reviews. Partial or invalid configuration
    is reported explicitly instead of pretending to save comments elsewhere.
    """
    if config is not None and not isinstance(config, Mapping):
        raise ReviewError(_CONFIG_ERROR)
    values: list[str] = []
    for key, environment_name in (("url", "SUPABASE_URL"), ("service_role_key", "SUPABASE_SERVICE_ROLE_KEY")):
        value = config.get(key) if config is not None else None
        if value is None or isinstance(value, str) and not value.strip():
            value = os.environ.get(environment_name, "")
        if not isinstance(value, str):
            raise ReviewError(_CONFIG_ERROR)
        values.append(value.strip())
    url, key = values
    if not url and not key:
        return None
    if not url or not key:
        raise ReviewError(_CONFIG_ERROR)
    return SupabaseReviewStore(url, key)
