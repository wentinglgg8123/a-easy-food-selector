"""Run the actual page, callbacks, and Supabase client with a test-only HTTP transport."""

from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from streamlit.testing.v1 import AppTest

from food_picker import reviews
from food_picker.defaults import load_default_catalog

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


class FakeAPI:
    def __init__(self, *, missing_v2=False):
        self.rows, self.calls, self.missing_v2 = {}, [], missing_v2

    def __call__(self, request, *, timeout):
        url = urlsplit(request.full_url)
        data = json.loads(request.data) if request.data else None
        self.calls.append((request.method, url.path, data))
        if url.path.startswith("/rest/v1/rpc/"):
            if self.missing_v2 and url.path.endswith("_v2"):
                raise HTTPError(request.full_url, 404, "RPC not installed", {}, BytesIO())
            result = [row for row in self.rows.values() if row["restaurant_id"] in data["restaurant_ids"]]
            if not url.path.endswith("_v2"):
                result = [{key: value for key, value in row.items() if key != "rating"} for row in result]
        elif request.method == "POST" and url.path == "/rest/v1/restaurant_reviews":
            assert parse_qs(url.query) == {"on_conflict": ["id"]}
            if data["id"] in self.rows:
                result = []
            else:
                row = {**data, "created_at": "2026-10-24T08:30:00+00:00"}
                self.rows[row["id"]] = row
                result = [row]
        elif request.method == "GET" and url.path == "/rest/v1/restaurant_reviews":
            row = self.rows.get(parse_qs(url.query)["id"][0].removeprefix("eq."))
            result = [row] if row else []
        else:
            raise AssertionError("Unexpected fake HTTP operation")
        return BytesIO(json.dumps(result, ensure_ascii=False).encode())


def page(monkeypatch, api):
    monkeypatch.setattr(reviews, "configured_review_store", lambda config: reviews.SupabaseReviewStore(
        "https://test-reviews.example.com", "test-only-key", transport=api,
    ))
    app = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    assert not app.exception
    return app


def search_and_pick(app):
    app.text_input(key="query_choice").set_value(load_default_catalog().restaurants[0].name).run()
    app.button(key="pick_meal").click().run()
    assert not app.exception
    return app.session_state["picker"].selected.id


def html(app):
    return "\n".join(element.value for element in app.get("html"))


def test_real_callback_saves_half_star_review_once_and_shares_it_across_contexts(monkeypatch):
    api = FakeAPI()
    app = page(monkeypatch, api)
    restaurant_id = search_and_pick(app)
    prefixes = [restaurant_id, f"search_{restaurant_id}", f"recommendation_{restaurant_id}"]
    assert all(app.text_area(key=f"review_body_{prefix}").value == "" for prefix in prefixes)
    prefix = prefixes[2]
    app.text_input(key=f"review_author_{prefix}").set_value("整合測試訪客")
    app.slider(key=f"review_rating_{prefix}").set_value(1.5)
    app.text_area(key=f"review_body_{prefix}").set_value("從推薦結果發布的共用評論")
    api.calls.clear()
    app.button(key=f"review_submit_{prefix}").click().run()
    assert not app.exception and len(api.rows) == 1
    assert next(iter(api.rows.values()))["rating"] == 1.5
    assert app.text_area(key=f"review_body_{prefix}").value == ""
    assert app.text_input(key=f"review_author_{prefix}").value == "整合測試訪客"
    assert html(app).count('aria-label="1.5 / 5 顆星"') == 3
    assert html(app).count("從推薦結果發布的共用評論") == 3
    reads = [data["restaurant_ids"] for _, path, data in api.calls if path.endswith("_v2")]
    assert reads == [[restaurant_id]]
    visitor = page(monkeypatch, api)
    visitor.text_input(key="query_choice").set_value(load_default_catalog().restaurants[0].name).run()
    assert not visitor.exception
    assert html(visitor).count('aria-label="1.5 / 5 顆星"') == 2
    assert "從推薦結果發布的共用評論" in html(visitor)
    assert len(api.rows) == 1


def test_missing_rating_rpc_preserves_old_reviews_and_disables_all_context_submissions(monkeypatch):
    api = FakeAPI(missing_v2=True)
    restaurant_id = load_default_catalog().restaurants[0].id
    row = {"id": str(uuid4()), "restaurant_id": restaurant_id, "author": "舊訪客",
           "body": "升級之前的公開評論仍然可見", "created_at": "2026-10-22T08:30:00Z"}
    api.rows[row["id"]] = row
    app = page(monkeypatch, api)
    assert search_and_pick(app) == restaurant_id
    submits = [button for button in app.button if button.key and button.key.startswith("review_submit_")]
    assert len(submits) == 3 and all(button.disabled for button in submits)
    assert html(app).count("升級之前的公開評論仍然可見") == 3
    assert html(app).count('class="review-unrated">未評分') == 3
    assert sum("評分功能尚待啟用" in message.value for message in app.info) == 1
    api.calls.clear()
    app.pills(key="category_choices").set_value(["牛排"]).run()
    assert not app.exception and not app.button(key="pick_meal").disabled
    assert [path for _, path, _ in api.calls] == [
        "/rest/v1/rpc/food_picker_reviews_for_restaurants_v2",
        "/rest/v1/rpc/food_picker_reviews_for_restaurants",
    ]
    assert len(api.rows) == 1
