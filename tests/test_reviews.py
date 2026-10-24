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
    Review,
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
        if url.path in (
            "/rest/v1/rpc/food_picker_reviews_for_restaurants_v2",
            "/rest/v1/rpc/food_picker_reviews_for_restaurants",
        ):
            assert request.method == "POST"
            result = []
            for restaurant_id in payload["restaurant_ids"]:
                matching = [row for row in self.rows.values() if row["restaurant_id"] == restaurant_id]
                matching.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
                result.extend(matching[:payload["review_limit"]])
            if not url.path.endswith("_v2"):
                result = [{key: value for key, value in row.items() if key != "rating"} for row in result]
        elif request.method == "POST" and url.path == "/rest/v1/restaurant_reviews":
            assert parse_qs(url.query) == {"on_conflict": ["id"]}
            assert request.get_header("Prefer") == "resolution=ignore-duplicates,return=representation"
            assert "created_at" not in payload
            if payload["id"] in self.rows:
                result = []
            else:
                instant = datetime(2026, 10, 22, tzinfo=timezone.utc) + timedelta(seconds=len(self.rows))
                row = {**payload, "created_at": instant.isoformat(), "rating": payload.get("rating")}
                self.rows[row["id"]] = row
                result = [row]
                if self.fail_after_commit:
                    self.fail_after_commit = False
                    raise URLError("server already committed; private response: " + KEY)
        elif request.method == "GET" and url.path == "/rest/v1/restaurant_reviews":
            query = parse_qs(url.query)
            assert query["limit"] == ["1"]
            row = self.rows.get(query["id"][0].removeprefix("eq."))
            fields = query["select"][0].split(",")
            result = [dict(row) if fields == ["*"] else {field: row.get(field) for field in fields}] if row else []
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
    assert request.full_url.endswith("/rpc/food_picker_reviews_for_restaurants_v2")


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


@pytest.mark.parametrize("rating", [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5])
def test_half_star_ratings_are_persisted_and_loaded_by_another_client(remote, rating):
    saved = store(remote).add_review("restaurant-a", "甲", "值得推薦", str(uuid4()), rating=rating)
    loaded = store(remote).load_reviews(["restaurant-a"])["restaurant-a"][0]
    assert saved.rating == rating and loaded.rating == rating
    assert remote.rows[saved.id]["rating"] == rating


@pytest.mark.parametrize("rating", [True, False, 0, .5, 5.5, 6, 1.25, 3.49999999999, float("inf"), float("-inf"), float("nan"), "3.5"])
def test_invalid_ratings_are_rejected_before_contacting_supabase(remote, rating):
    with pytest.raises(ReviewValidationError):
        store(remote).add_review("restaurant-a", "甲", "好吃", str(uuid4()), rating=rating)
    assert remote.calls == []


def test_legacy_reviews_remain_unrated_without_a_fabricated_default(remote):
    client = store(remote)
    token = str(uuid4())
    legacy = client.add_review("restaurant-a", "甲", "原有評論", token)
    assert legacy.rating is None
    assert "rating" not in json.loads(remote.calls[0][0].data)
    assert remote.rows[token]["rating"] is None
    assert client.load_reviews(["restaurant-a"])["restaurant-a"][0].rating is None
    remote.rows[token].pop("rating")
    assert client.load_reviews(["restaurant-a"])["restaurant-a"][0].rating is None
    assert Review(token, "restaurant-a", "甲", "舊版呼叫", legacy.created_at).rating is None


def test_idempotent_rating_retry_keeps_original_id_timestamp_and_rating(remote):
    first, second = store(remote), store(remote)
    token = str(uuid4())
    saved = first.add_review("restaurant-a", "甲", "好吃", token, rating=3.5)
    retried = second.add_review("restaurant-a", "甲", "修改後草稿", token, rating=5)
    assert retried == saved
    assert retried.rating == 3.5
    assert retried.id == token and retried.created_at == saved.created_at
    assert len(remote.rows) == 1
    assert parse_qs(urlsplit(remote.calls[-1][0].full_url).query)["select"] == ["*"]


def test_legacy_idempotent_retry_does_not_assign_a_new_rating_to_an_old_review(remote):
    client = store(remote)
    token = str(uuid4())
    original = client.add_review("restaurant-a", "甲", "舊有評論", token)
    retried = client.add_review("restaurant-a", "甲", "舊有評論", token, rating=4.5)
    assert retried == original and retried.rating is None
    assert remote.rows[token]["rating"] is None


@pytest.mark.parametrize("rating", [True, 0, 1.25, 6, "4.5", float("inf"), float("nan")])
def test_invalid_remote_ratings_are_rejected_without_fabricating_a_star_value(remote, rating):
    client = store(remote)
    saved = client.add_review("restaurant-a", "甲", "好吃", str(uuid4()), rating=4.5)
    remote.rows[saved.id]["rating"] = rating
    with pytest.raises(ReviewError):
        client.load_reviews(["restaurant-a"])


def test_missing_rating_rpc_keeps_legacy_reviews_visible_and_blocks_rated_writes(remote):
    original = store(remote).add_review("restaurant-a", "甲", "既有評論", str(uuid4()))
    calls = []

    def old_database(request, *, timeout):
        calls.append(request.full_url)
        if request.full_url.endswith("_v2"):
            raise HTTPError(request.full_url, 404, "private: " + KEY, {}, None)
        return remote(request, timeout=timeout)

    client = SupabaseReviewStore(URL, KEY, transport=old_database)
    assert client.ratings_ready
    result = client.load_reviews(["restaurant-a"])
    assert result == {"restaurant-a": [original]}
    assert result["restaurant-a"][0].rating is None
    assert not client.ratings_ready
    assert calls == [
        URL + "/rest/v1/rpc/food_picker_reviews_for_restaurants_v2",
        URL + "/rest/v1/rpc/food_picker_reviews_for_restaurants",
    ]
    with pytest.raises(ReviewError, match="升級") as failure:
        client.add_review("restaurant-a", "甲", "新評分評論", str(uuid4()), rating=3.5)
    assert len(calls) == 2
    assert KEY not in str(failure.value)


def test_later_reads_detect_completed_rating_upgrade_without_changing_existing_rows(remote):
    saved = store(remote).add_review("restaurant-a", "甲", "半星評論", str(uuid4()), rating=3.5)
    ready = False

    def upgradeable_database(request, *, timeout):
        if not ready and request.full_url.endswith("_v2"):
            raise HTTPError(request.full_url, 404, "missing function", {}, None)
        return remote(request, timeout=timeout)

    client = SupabaseReviewStore(URL, KEY, transport=upgradeable_database)
    old_view = client.load_reviews(["restaurant-a"])["restaurant-a"][0]
    assert not client.ratings_ready and old_view.rating is None
    assert (old_view.id, old_view.body, old_view.created_at) == (saved.id, saved.body, saved.created_at)
    ready = True
    assert client.load_reviews(["restaurant-a"])["restaurant-a"] == [saved]
    assert client.ratings_ready
    assert len(remote.rows) == 1


@pytest.mark.parametrize("failure", [
    HTTPError(URL, 401, "private: " + KEY, {}, None),
    HTTPError(URL, 403, "private: " + KEY, {}, None),
    HTTPError(URL, 429, "private: " + KEY, {}, None),
    HTTPError(URL, 500, "private: " + KEY, {}, None),
    URLError("private: " + KEY), TimeoutError("private: " + KEY),
])
def test_other_rating_read_failures_do_not_fall_back_or_hide_the_error(failure):
    calls = []

    def failed_database(request, *, timeout):
        calls.append(request.full_url)
        raise failure

    client = SupabaseReviewStore(URL, KEY, transport=failed_database)
    with pytest.raises(ReviewError) as error:
        client.load_reviews(["restaurant-a"])
    assert calls == [URL + "/rest/v1/rpc/food_picker_reviews_for_restaurants_v2"]
    assert KEY not in str(error.value)


def test_missing_rating_column_never_retries_a_write_without_the_rating():
    calls = []

    def unmigrated_database(request, *, timeout):
        calls.append(request)
        raise HTTPError(request.full_url, 400, "private: " + KEY, {}, None)

    client = SupabaseReviewStore(URL, KEY, transport=unmigrated_database)
    with pytest.raises(ReviewError):
        client.add_review("restaurant-a", "甲", "評分評論", str(uuid4()), rating=4.5)
    assert len(calls) == 1
    assert json.loads(calls[0].data)["rating"] == 4.5


def test_legacy_unrated_insert_and_idempotent_retry_work_before_rating_column_exists(remote):
    calls = []

    def old_schema(request, *, timeout):
        calls.append(request)
        url = urlsplit(request.full_url)
        if url.path.endswith("_v2"):
            raise HTTPError(request.full_url, 404, "function does not exist", {}, None)
        if request.method == "GET":
            selected = parse_qs(url.query)["select"][0].split(",")
            if "rating" in selected:
                raise HTTPError(request.full_url, 400, "column does not exist", {}, None)
        if request.method == "POST" and url.path == "/rest/v1/restaurant_reviews":
            assert "rating" not in json.loads(request.data)
        response = remote(request, timeout=timeout)
        rows = json.loads(response.read())
        # The original table genuinely has no rating column in rows or responses.
        for row in remote.rows.values():
            row.pop("rating", None)
        for row in rows:
            row.pop("rating", None)
        return BytesIO(json.dumps(rows).encode())

    client = SupabaseReviewStore(URL, KEY, transport=old_schema)
    assert client.load_reviews(["restaurant-a"]) == {"restaurant-a": []}
    assert not client.ratings_ready
    token = str(uuid4())
    first = client.add_review("restaurant-a", "甲", "舊版未評分評論", token, rating=None)
    retried = client.add_review("restaurant-a", "甲", "舊版未評分評論", token, rating=None)
    assert retried == first and first.rating is None
    assert len(remote.rows) == 1 and "rating" not in remote.rows[token]
    assert calls[-1].method == "GET"
    assert parse_qs(urlsplit(calls[-1].full_url).query)["select"] == ["*"]
    request_count = len(calls)
    with pytest.raises(ReviewError):
        client.add_review("restaurant-a", "甲", "新評分評論", str(uuid4()), rating=4.5)
    assert len(calls) == request_count
