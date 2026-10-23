"""Exercise the remote review contract without any external reads or writes."""

from datetime import datetime, timedelta, timezone
from http.client import BadStatusLine
from io import BytesIO
import json
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from food_picker.reviews import (
    ReviewError,
    ReviewValidationError,
    SupabaseReviewStore,
    configured_review_store,
)

URL = "https://reviews.example.com"
KEY = "server-only-unit-test-key"


class FakeSupabase:
    """Independent remote table shared by client instances, including conflict behavior."""

    def __init__(self):
        self.rows = {}
        self.calls = []
        self.fail_after_commit = False

    def __call__(self, request, *, timeout):
        self.calls.append((request, timeout))
        assert request.get_header("Apikey") == KEY
        assert request.get_header("Authorization") == f"Bearer {KEY}"
        assert 0 < timeout <= 15
        url = urlsplit(request.full_url)
        payload = json.loads(request.data) if request.data is not None else None
        if url.path == "/rest/v1/rpc/food_picker_reviews_for_restaurants":
            assert request.method == "POST"
            result = []
            for restaurant_id in payload["restaurant_ids"]:
                matching = [row for row in self.rows.values() if row["restaurant_id"] == restaurant_id]
                matching.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
                result.extend(matching[:payload["review_limit"]])
        elif request.method == "POST" and url.path == "/rest/v1/restaurant_reviews":
            assert parse_qs(url.query) == {"on_conflict": ["id"]}
            assert request.get_header("Prefer") == "resolution=ignore-duplicates,return=representation"
            assert "created_at" not in payload
            if payload["id"] in self.rows:
                result = []
            else:
                instant = datetime(2026, 10, 22, tzinfo=timezone.utc) + timedelta(seconds=len(self.rows))
                row = {**payload, "created_at": instant.isoformat()}
                self.rows[row["id"]] = row
                result = [row]
                if self.fail_after_commit:
                    self.fail_after_commit = False
                    raise URLError("server already committed; private response: " + KEY)
        elif request.method == "GET" and url.path == "/rest/v1/restaurant_reviews":
            query = parse_qs(url.query)
            assert query["limit"] == ["1"]
            row = self.rows.get(query["id"][0].removeprefix("eq."))
            result = [row] if row else []
        else:
            pytest.fail("Unexpected remote operation")
        return BytesIO(json.dumps(result, ensure_ascii=False).encode())


@pytest.fixture(autouse=True)
def no_existing_review_configuration(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)


@pytest.fixture
def remote():
    return FakeSupabase()


def store(remote):
    return SupabaseReviewStore(URL, KEY, transport=remote)


def test_missing_configuration_disables_reviews_without_a_local_store():
    assert configured_review_store() is None
    assert configured_review_store({}) is None
    assert configured_review_store({"url": " ", "service_role_key": ""}) is None


def test_environment_bindings_and_explicit_server_secrets_are_supported(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", KEY)
    assert isinstance(configured_review_store(), SupabaseReviewStore)
    monkeypatch.setenv("SUPABASE_URL", "http://invalid.example.com")
    assert isinstance(configured_review_store({"url": URL, "service_role_key": KEY}), SupabaseReviewStore)


@pytest.mark.parametrize("config", [
    {"url": URL}, {"service_role_key": KEY}, {"url": URL, "service_role_key": 42},
    {"url": [URL], "service_role_key": KEY},
])
def test_partial_or_invalid_configuration_reports_a_safe_error(config):
    with pytest.raises(ReviewError) as error:
        configured_review_store(config)
    assert KEY not in str(error.value)


@pytest.mark.parametrize("url", [
    "http://reviews.example.com", "https://", "https://user:password@reviews.example.com",
    URL + "/rest/v1", URL + "?key=private", URL + "#fragment",
    "https://reviews.example.com:invalid", "https://rev\niews.example.com",
    "https://reviews.example.com\\elsewhere",
])
def test_configuration_requires_a_clean_https_origin(url):
    with pytest.raises(ReviewError):
        SupabaseReviewStore(url, KEY)


@pytest.mark.parametrize("timeout", [0, -1, 16, float("nan"), True])
def test_network_timeout_is_bounded(timeout):
    with pytest.raises(ReviewError):
        SupabaseReviewStore(URL, KEY, timeout=timeout)


@pytest.mark.parametrize("changes", [
    {"restaurant_id": "bad/id"}, {"restaurant_id": "bad\nheader"},
    {"restaurant_id": "x" * 101}, {"author": "字" * 41},
    {"author": None}, {"body": " \n\t "}, {"body": "字" * 501},
    {"body": 1}, {"submission_id": "not-a-uuid"}, {"restaurant_name": "店" * 201},
])
def test_invalid_submissions_never_contact_the_database(remote, changes):
    arguments = {"restaurant_id": "restaurant-abc", "author": "", "body": "好吃", "submission_id": str(uuid4())}
    arguments.update(changes)
    with pytest.raises(ReviewValidationError):
        store(remote).add_review(**arguments)
    assert remote.calls == []


def test_submission_trims_text_defaults_anonymous_name_and_uses_server_timestamp(remote):
    saved = store(remote).add_review("restaurant-abc", " \t ", "  好吃\n會再來  ", str(uuid4()), " 小店 ")
    assert (saved.author, saved.body) == ("訪客", "好吃\n會再來")
    assert saved.created_at == "2026-10-22T00:00:00+00:00"
    assert remote.rows[saved.id]["restaurant_name"] == "小店"
    body = "字" * 500
    author = "字" * 40
    boundary = store(remote).add_review("restaurant-abc", author, body, str(uuid4()))
    assert (boundary.author, boundary.body) == (author, body)


def test_reviews_are_shared_by_independent_store_instances(remote):
    first, second = store(remote), store(remote)
    saved = first.add_review("restaurant-abc", "訪客甲", "值得推薦", str(uuid4()))
    assert second.load_reviews(["restaurant-abc"]) == {"restaurant-abc": [saved]}


def test_batch_rpc_returns_latest_reviews_per_restaurant_and_empty_groups(remote):
    client = store(remote)
    for index in range(5):
        client.add_review("restaurant-a", "甲", f"a{index}", str(uuid4()))
    for index in range(2):
        client.add_review("restaurant-b", "乙", f"b{index}", str(uuid4()))
    result = client.load_reviews(["restaurant-a", "restaurant-b", "restaurant-c", "restaurant-a"])
    assert [review.body for review in result["restaurant-a"]] == ["a4", "a3", "a2"]
    assert [review.body for review in result["restaurant-b"]] == ["b1", "b0"]
    assert result["restaurant-c"] == []
    request = remote.calls[-1][0]
    assert json.loads(request.data) == {"restaurant_ids": ["restaurant-a", "restaurant-b", "restaurant-c"], "review_limit": 3}
    assert "rpc/food_picker_reviews_for_restaurants" in request.full_url


def test_duplicate_submission_uuid_returns_the_persisted_record_without_another_insert(remote):
    first, second = store(remote), store(remote)
    token = str(uuid4())
    saved = first.add_review("restaurant-a", "甲", "好吃", token)
    assert second.add_review("restaurant-a", "甲", "好吃", token) == saved
    assert len(remote.rows) == 1
    assert remote.calls[-1][0].method == "GET"


def test_retry_after_uncertain_network_result_preserves_the_original_submission(remote):
    client = store(remote)
    token = str(uuid4())
    remote.fail_after_commit = True
    with pytest.raises(ReviewError) as error:
        client.add_review("restaurant-a", "甲", "原始評論", token)
    assert KEY not in str(error.value)
    saved = client.add_review("restaurant-a", "甲", "使用者繼續編輯的草稿", token)
    assert saved.body == "原始評論"
    assert len(remote.rows) == 1


def test_reusing_a_submission_for_another_restaurant_is_rejected(remote):
    token = str(uuid4())
    client = store(remote)
    client.add_review("restaurant-a", "甲", "好吃", token)
    with pytest.raises(ReviewError):
        client.add_review("restaurant-b", "甲", "好吃", token)


@pytest.mark.parametrize("ids, limit", [
    ("restaurant-a", 3), (["bad/id"], 3), ([f"restaurant-{index}" for index in range(25)], 3),
    (["restaurant-a"], 0), (["restaurant-a"], 11), (["restaurant-a"], True),
])
def test_invalid_batch_queries_never_contact_the_database(remote, ids, limit):
    with pytest.raises(ReviewValidationError):
        store(remote).load_reviews(ids, limit)
    assert remote.calls == []


def test_empty_batch_does_not_contact_the_database(remote):
    assert store(remote).load_reviews([]) == {}
    assert remote.calls == []


@pytest.mark.parametrize("error", [
    HTTPError(URL, 401, "private: " + KEY, {}, None),
    HTTPError(URL, 403, "private: " + KEY, {}, None),
    HTTPError(URL, 404, "private: " + KEY, {}, None),
    HTTPError(URL, 500, "private: " + KEY, {}, None),
    URLError("private: " + KEY), TimeoutError("private: " + KEY),
    BadStatusLine("private: " + KEY),
])
def test_remote_errors_do_not_expose_headers_or_response_details(error):
    def fail(request, *, timeout):
        raise error

    client = SupabaseReviewStore(URL, KEY, transport=fail)
    with pytest.raises(ReviewError) as failure:
        client.load_reviews(["restaurant-a"])
    assert KEY not in str(failure.value)
    assert "private" not in str(failure.value)
    assert failure.value.__suppress_context__


@pytest.mark.parametrize("payload", [b"not JSON", b'{"error":"private"}', b"x" * 512_001])
def test_malformed_or_oversized_remote_response_is_reported_safely(payload):
    client = SupabaseReviewStore(URL, KEY, transport=lambda request, timeout: BytesIO(payload))
    with pytest.raises(ReviewError):
        client.load_reviews(["restaurant-a"])


def test_remote_rows_cannot_be_attributed_to_a_different_restaurant(remote):
    client = store(remote)
    saved = client.add_review("restaurant-b", "甲", "好吃", str(uuid4()))
    unrelated = json.dumps(remote.rows[saved.id]).encode()
    bad_client = SupabaseReviewStore(URL, KEY, transport=lambda request, timeout: BytesIO(b"[" + unrelated + b"]"))
    with pytest.raises(ReviewError):
        bad_client.load_reviews(["restaurant-a"])
