"""Exercise public review forms against an explicitly injected shared test store."""

from dataclasses import replace
from types import ModuleType
import sys
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from food_picker.models import Restaurant
from food_picker.reviews import Review, ReviewError, ReviewValidationError
from food_picker.review_ui import stars_html


class FakeStore:
    """Test-only storage shared across separate AppTest visitor sessions."""

    def __init__(self):
        self.rows = []
        self.submissions = {}
        self.fail_next = False
        self.validation_error = False
        self.calls = []

    def load_reviews(self, ids, limit=3):
        return {restaurant_id: [row for row in reversed(self.rows) if row.restaurant_id == restaurant_id][:limit] for restaurant_id in ids}

    def add_review(self, restaurant_id, author, body, submission_id, restaurant_name="", *, rating=None):
        self.calls.append((restaurant_id, author, body, submission_id, restaurant_name, rating))
        if self.fail_next:
            self.fail_next = False
            raise ReviewError("private backend detail must not be displayed")
        if self.validation_error:
            raise ReviewValidationError("validation detail from backend")
        if submission_id in self.submissions:
            return self.submissions[submission_id]
        row = Review(str(uuid4()), restaurant_id, author or "訪客", body, "2026-10-22T08:30:00+00:00", rating)
        self.rows.append(row)
        self.submissions[submission_id] = row
        return row


@pytest.fixture
def review_app(monkeypatch):
    support = ModuleType("review_ui_test_support")
    support.store = FakeStore()
    support.restaurants = [Restaurant("review-first", "第一間店", "other", "咖啡", None, None, "", "")]
    support.enabled = True
    support.load_error = False
    support.contexts = ("catalog",)
    monkeypatch.setitem(sys.modules, support.__name__, support)
    source = """
import review_ui_test_support as support
from food_picker.review_ui import render_reviews
store = support.store if support.enabled else None
ids = [restaurant.id for restaurant in support.restaurants]
reviews = store.load_reviews(ids) if store is not None and not support.load_error else {}
for restaurant in support.restaurants:
    for context in support.contexts:
        render_reviews(restaurant, store, reviews.get(restaurant.id, []), load_error=support.load_error, context=context)
"""

    def create():
        app = AppTest.from_string(source, default_timeout=10).run()
        assert not app.exception
        return app

    support.create = create
    return support


def _publish(app, body, *, author="食客", restaurant_id="review-first", rating=3.0, context="catalog"):
    prefix = restaurant_id if context == "catalog" else f"{context}_{restaurant_id}"
    app.text_input(key=f"review_author_{prefix}").set_value(author)
    app.slider(key=f"review_rating_{prefix}").set_value(rating)
    app.text_area(key=f"review_body_{prefix}").set_value(body)
    app.button(key=f"review_submit_{prefix}").click().run()
    assert not app.exception


def _html(app):
    return "\n".join(element.value for element in app.get("html"))


def test_successful_review_is_shared_with_a_new_visitor_and_clears_only_body(review_app):
    app = review_app.create()
    previous_token = app.session_state["review_submission_review-first"]
    _publish(app, "麵很香\n值得再訪！", author="食客 A", rating=1.5)

    assert len(review_app.store.rows) == 1
    assert review_app.store.calls[0][:3] == ("review-first", "食客 A", "麵很香\n值得再訪！")
    assert review_app.store.calls[0][4] == "第一間店"
    assert review_app.store.calls[0][5] == review_app.store.rows[0].rating == 1.5
    assert app.text_area(key="review_body_review-first").value == ""
    assert app.text_input(key="review_author_review-first").value == "食客 A"
    assert app.slider(key="review_rating_review-first").value == 1.5
    assert app.session_state["review_submission_review-first"] != previous_token
    assert any("評論已發布" in message.value for message in app.success)
    assert "麵很香<br>值得再訪！" in _html(app)
    assert "2026/10/22 16:30" in _html(app)
    assert 'aria-label="1.5 / 5 顆星"' in _html(app)
    assert 'width:30%' in _html(app)

    fresh_visitor = review_app.create()
    assert "食客 A" in _html(fresh_visitor)
    assert "麵很香<br>值得再訪！" in _html(fresh_visitor)
    assert 'aria-label="1.5 / 5 顆星"' in _html(fresh_visitor)
    assert fresh_visitor.text_area(key="review_body_review-first").value == ""
    fresh_visitor.run()
    assert "麵很香" in _html(fresh_visitor)


def test_backend_error_preserves_draft_author_and_retry_token(review_app):
    app = review_app.create()
    token = app.session_state["review_submission_review-first"]
    review_app.store.fail_next = True
    _publish(app, "尚未發布的草稿", author="訪客 B", rating=2.5)
    assert not review_app.store.rows
    assert app.text_area(key="review_body_review-first").value == "尚未發布的草稿"
    assert app.text_input(key="review_author_review-first").value == "訪客 B"
    assert app.slider(key="review_rating_review-first").value == 2.5
    assert app.session_state["review_submission_review-first"] == token
    assert any("輸入內容已保留" in message.value for message in app.error)
    assert all("private backend" not in message.value for message in app.error)

    app.button(key="review_submit_review-first").click().run()
    assert not app.exception
    assert len(review_app.store.rows) == 1
    assert review_app.store.calls[0][3] == review_app.store.calls[1][3] == token
    assert review_app.store.rows[0].rating == 2.5
    assert app.text_area(key="review_body_review-first").value == ""


def test_optional_author_uses_the_shared_stores_guest_name(review_app):
    app = review_app.create()
    _publish(app, "匿名用餐心得", author="")
    assert review_app.store.rows[0].author == "訪客"
    assert app.text_input(key="review_author_review-first").value == ""
    assert app.text_area(key="review_body_review-first").value == ""
    assert any("評論已發布" in message.value for message in app.success)


def test_blank_comment_is_rejected_without_calling_store_or_erasing_draft(review_app):
    app = review_app.create()
    token = app.session_state["review_submission_review-first"]
    _publish(app, "   ", author="保留暱稱")
    assert not review_app.store.calls
    assert app.text_area(key="review_body_review-first").value == "   "
    assert app.text_input(key="review_author_review-first").value == "保留暱稱"
    assert app.session_state["review_submission_review-first"] == token
    assert any("請先填寫評論內容" in message.value for message in app.error)


def test_backend_validation_error_preserves_the_draft(review_app):
    app = review_app.create()
    review_app.store.validation_error = True
    _publish(app, "後端尚未接受的評論")
    assert app.text_area(key="review_body_review-first").value == "後端尚未接受的評論"
    assert not review_app.store.rows
    assert any("請檢查" in message.value for message in app.error)


def test_review_content_and_restaurant_name_are_escaped_without_markdown_links(review_app):
    restaurant = review_app.restaurants[0]
    review_app.restaurants = [replace(restaurant, name='店家"<script>')]
    review_app.store.rows = [Review(
        "untrusted", restaurant.id, '<img src=x onerror="alert(1)">',
        '[點我](https://example.com) <script>alert(2)</script>\n& 後一行',
        '<svg onload="alert(3)">',
    )]
    app = review_app.create()
    html = _html(app)
    assert '<script>' not in html and '<img ' not in html and '<svg ' not in html
    assert '&lt;script&gt;' in html and '&lt;img ' in html and '&lt;svg ' in html
    assert '[點我](https://example.com)' in html
    assert '<a ' not in html
    assert 'aria-label="店家&quot;&lt;script&gt;的評論"' in html
    assert '&amp; 後一行' in html


def test_missing_store_disables_publishing_without_claiming_success(review_app):
    review_app.enabled = False
    app = review_app.create()
    assert app.button(key="review_submit_review-first").disabled
    assert not app.success
    assert not review_app.store.calls
    assert "還沒有評論，分享你的用餐心得。" in _html(app)


def test_failed_load_disables_publishing_and_shows_unavailable_state(review_app):
    review_app.load_error = True
    app = review_app.create()
    assert app.button(key="review_submit_review-first").disabled
    assert "評論暫時無法載入" in _html(app)
    assert "還沒有評論" not in _html(app)


def test_database_waiting_for_rating_migration_shows_old_comments_but_disables_new_writes(review_app):
    review_app.store.ratings_ready = False
    review_app.store.rows.append(Review("old", "review-first", "舊訪客", "升級前留下的評論", "2026-10-22T08:30:00Z"))
    app = review_app.create()
    assert "升級前留下的評論" in _html(app)
    assert "未評分" in _html(app)
    assert app.button(key="review_submit_review-first").disabled
    assert not review_app.store.calls


def test_restaurant_forms_and_drafts_are_isolated(review_app):
    first = review_app.restaurants[0]
    second = replace(first, id="review-second", name="第二間店")
    review_app.restaurants.append(second)
    app = review_app.create()
    second_token = app.session_state["review_submission_review-second"]
    # A failed submission leaves a server-side draft in the second form.
    review_app.store.fail_next = True
    _publish(app, "第二間的草稿", author="第二位訪客", restaurant_id=second.id)
    _publish(app, "第一間的評論", author="第一位訪客")
    assert [(row.restaurant_id, row.body) for row in review_app.store.rows] == [(first.id, "第一間的評論")]
    assert app.text_area(key="review_body_review-first").value == ""
    assert app.text_area(key="review_body_review-second").value == "第二間的草稿"
    assert app.text_input(key="review_author_review-second").value == "第二位訪客"
    assert app.session_state["review_submission_review-second"] == second_token


def test_only_three_latest_shared_reviews_are_displayed(review_app):
    restaurant_id = review_app.restaurants[0].id
    review_app.store.rows = [Review(str(number), restaurant_id, "訪客", f"評論第 {number} 則", "2026-10-22T08:30:00Z") for number in range(5)]
    app = review_app.create()
    html = _html(app)
    assert all(f"評論第 {number} 則" in html for number in (2, 3, 4))
    assert all(f"評論第 {number} 則" not in html for number in (0, 1))


def test_idempotent_retry_does_not_discard_a_newer_edited_draft(review_app):
    app = review_app.create()
    token = app.session_state["review_submission_review-first"]
    older = Review("previous", "review-first", "食客", "先前已送出的內容", "2026-10-22T08:30:00Z")
    review_app.store.rows.append(older)
    review_app.store.submissions[token] = older
    _publish(app, "修改過的新草稿")
    assert app.text_area(key="review_body_review-first").value == "修改過的新草稿"
    assert app.session_state["review_submission_review-first"] != token
    assert len(review_app.store.rows) == 1
    assert any("草稿已保留" in message.value for message in app.info)
    app.button(key="review_submit_review-first").click().run()
    assert len(review_app.store.rows) == 2
    assert app.text_area(key="review_body_review-first").value == ""


@pytest.mark.parametrize("rating", [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0])
def test_every_half_star_rating_can_be_selected_and_saved(review_app, rating):
    app = review_app.create()
    slider = app.slider(key="review_rating_review-first")
    assert slider.label == "您的評分"
    assert slider.min == 1.0 and slider.max == 5.0 and slider.step == 0.5
    assert app.text_input(key="review_author_review-first").label == "您的暱稱"
    _publish(app, "不同星等的用餐心得", rating=rating)
    assert review_app.store.rows[0].rating == rating
    assert app.slider(key="review_rating_review-first").value == rating
    assert app.text_area(key="review_body_review-first").value == ""
    html = _html(app)
    assert f'aria-label="{rating:g} / 5 顆星"' in html
    assert f'width:{rating * 20:g}%' in html


@pytest.mark.parametrize("rating", [None, float("nan"), float("inf"), 0, 5.5, 1.25, True])
def test_unrated_or_invalid_values_never_appear_as_five_stars(rating):
    assert stars_html(rating) == '<span class="review-unrated">未評分</span>'


def test_older_shared_review_without_a_rating_is_explicitly_unrated(review_app):
    review_app.store.rows.append(Review("old", "review-first", "舊訪客", "評分功能之前的評論", "2026-10-22T08:30:00Z"))
    app = review_app.create()
    assert 'class="review-unrated">未評分' in _html(app)
    assert 'class="review-star-fill"' not in _html(app)


def test_context_forms_for_the_same_restaurant_have_independent_drafts_and_tokens(review_app):
    review_app.contexts = ("catalog", "recommendation", "search")
    app = review_app.create()
    assert len(app.text_input) == len(app.text_area) == len(app.slider) == 3
    prefixes = ("review-first", "recommendation_review-first", "search_review-first")
    tokens = {prefix: app.session_state[f"review_submission_{prefix}"] for prefix in prefixes}
    assert len(set(tokens.values())) == 3

    review_app.store.fail_next = True
    _publish(app, "推薦結果下方的草稿", author="推薦頁訪客", rating=2.5, context="recommendation")
    _publish(app, "名單卡片下方的評論", author="名單頁訪客", rating=4.5)
    assert not app.exception
    assert len(review_app.store.rows) == 1
    assert review_app.store.rows[0].rating == 4.5
    assert app.text_area(key="review_body_review-first").value == ""
    assert app.text_area(key="review_body_recommendation_review-first").value == "推薦結果下方的草稿"
    assert app.text_input(key="review_author_recommendation_review-first").value == "推薦頁訪客"
    assert app.slider(key="review_rating_recommendation_review-first").value == 2.5
    assert app.session_state["review_submission_recommendation_review-first"] == tokens["recommendation_review-first"]
    assert app.session_state["review_submission_search_review-first"] == tokens["search_review-first"]
    assert app.session_state["review_submission_review-first"] != tokens["review-first"]
    assert _html(app).count("名單卡片下方的評論") == 3


def test_idempotent_retry_keeps_a_draft_when_only_its_rating_has_changed(review_app):
    app = review_app.create()
    token = app.session_state["review_submission_review-first"]
    previous = Review("previous", "review-first", "食客", "同一份用餐心得", "2026-10-22T08:30:00Z", 1.5)
    review_app.store.rows.append(previous)
    review_app.store.submissions[token] = previous
    _publish(app, "同一份用餐心得", rating=4.5)
    assert len(review_app.store.rows) == 1
    assert app.slider(key="review_rating_review-first").value == 4.5
    assert app.text_area(key="review_body_review-first").value == "同一份用餐心得"
    assert app.session_state["review_submission_review-first"] != token
    assert any("草稿已保留" in message.value for message in app.info)
    app.button(key="review_submit_review-first").click().run()
    assert not app.exception
    assert len(review_app.store.rows) == 2
    assert review_app.store.rows[1].rating == 4.5
    assert app.text_area(key="review_body_review-first").value == ""
