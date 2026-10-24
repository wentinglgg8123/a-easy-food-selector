"""Public restaurant review display and forms backed by the shared review store."""

from datetime import datetime, timezone
from html import escape
import math
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st

from .models import Restaurant
from .reviews import Review, ReviewError, ReviewValidationError, SupabaseReviewStore


def stars_html(value: float | None) -> str:
    """Render actual half-star ratings; legacy unrated comments stay unrated."""
    if (
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(value) or not 1 <= value <= 5 or value * 2 % 1
    ):
        return '<span class="review-unrated">未評分</span>'
    number = f"{value:g}"
    return (
        f'<span class="review-rating" role="img" aria-label="{number} / 5 顆星">'
        '<span class="review-star-track" aria-hidden="true" '
        'style="position:relative;display:inline-block;white-space:nowrap;line-height:1;letter-spacing:0">'
        '<span style="color:#dce3da">★★★★★</span>'
        f'<span class="review-star-fill" style="position:absolute;left:0;top:0;width:{value * 20:g}%;'
        'overflow:hidden;white-space:nowrap;color:#a56300">★★★★★</span></span>'
        f'<span class="review-rating-value" aria-hidden="true"> {number} / 5</span></span>'
    )


def _review_time(value: str) -> str:
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        return instant.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y/%m/%d %H:%M")
    except (TypeError, ValueError):
        return str(value)


def _publish_review(
    restaurant: Restaurant,
    store: SupabaseReviewStore | None,
    load_error: bool,
    prefix: str,
) -> None:
    """Callbacks run before widget creation, so only a confirmed save clears the body."""
    notice_key = f"review_notice_{prefix}"
    if store is None or load_error or not getattr(store, "ratings_ready", True):
        st.session_state[notice_key] = ("error", "目前無法發布評論，請稍後再試；輸入內容已保留。")
        return
    author = st.session_state.get(f"review_author_{prefix}", "").strip()
    body = st.session_state.get(f"review_body_{prefix}", "").strip()
    rating = st.session_state.get(f"review_rating_{prefix}", 3.0)
    if not body:
        st.session_state[notice_key] = ("error", "請先填寫評論內容。")
        return
    if len(author) > 40 or len(body) > 500:
        st.session_state[notice_key] = ("error", "暱稱最多 40 字，評論內容最多 500 字；請縮短後再發布。")
        return
    if (
        isinstance(rating, bool) or not isinstance(rating, (int, float))
        or not math.isfinite(rating) or not 1 <= rating <= 5 or rating * 2 % 1
    ):
        st.session_state[notice_key] = ("error", "請選擇 1 至 5 顆星的評分，可使用半顆星。")
        return
    token_key = f"review_submission_{prefix}"
    token = st.session_state.setdefault(token_key, str(uuid4()))
    try:
        saved = store.add_review(
            restaurant.id, author, body, token, restaurant_name=restaurant.name, rating=rating
        )
    except ReviewValidationError:
        st.session_state[notice_key] = ("error", "請檢查暱稱及評論內容後再試；輸入內容已保留。")
    except ReviewError:
        st.session_state[notice_key] = ("error", "評論暫時無法發布，請稍後再試；輸入內容已保留。")
    else:
        st.session_state[token_key] = str(uuid4())
        # A timeout may have saved an earlier version of the draft. Idempotent
        # retries must not discard newer text that differs from the stored row.
        if saved.body.strip() != body or saved.author != (author or "訪客") or saved.rating != rating:
            st.session_state[notice_key] = ("info", "先前送出的評論已儲存。目前草稿已保留，可再次發布。")
            return
        st.session_state[f"review_body_{prefix}"] = ""
        st.session_state[notice_key] = ("success", "評論已發布，所有訪客都能看到。")


def render_reviews(
    restaurant: Restaurant,
    store: SupabaseReviewStore | None,
    reviews: list[Review],
    *,
    load_error: bool = False,
    context: str = "catalog",
) -> None:
    """Display the latest shared comments and an independently keyed restaurant form."""
    label = escape(f"{restaurant.name}的評論", quote=True)
    prefix = restaurant.id if context == "catalog" else f"{context}_{restaurant.id}"
    if load_error:
        content = '<p class="review-empty">評論暫時無法載入，請稍後再試。</p>'
    elif reviews:
        content = ''.join(
            '<article class="restaurant-review"><p class="review-meta">'
            f'<strong>{escape(review.author or "匿名訪客")}</strong>'
            f'<time>{escape(_review_time(review.created_at))}</time></p>'
            f'{stars_html(review.rating)}'
            f'<p class="review-body">{escape(review.body).replace(chr(10), "<br>")}</p></article>'
            for review in reviews[:3]
        )
    else:
        content = '<p class="review-empty">還沒有評論，分享你的用餐心得。</p>'
    st.html(
        f'<section class="restaurant-reviews" aria-label="{label}">'
        '<h4>用餐評論</h4>' + content + '</section>'
    )
    st.caption("公開評論 · 顯示最新 3 則 · 時間為台北時間")
    if notice := st.session_state.pop(f"review_notice_{prefix}", None):
        kind, message = notice
        {"error": st.error, "success": st.success, "info": st.info}[kind](message)
    st.session_state.setdefault(f"review_submission_{prefix}", str(uuid4()))
    with st.form(f"review_form_{prefix}", clear_on_submit=False, border=False):
        st.text_input("您的暱稱", max_chars=40, key=f"review_author_{prefix}", help="選填，留白時顯示為訪客。")
        st.slider(
            "您的評分", min_value=1.0, max_value=5.0, step=0.5, value=3.0,
            key=f"review_rating_{prefix}", help="1 至 5 顆星，每 0.5 顆一格。",
        )
        st.text_area("評論內容", max_chars=500, height=90, key=f"review_body_{prefix}")
        st.form_submit_button(
            "發布評論", key=f"review_submit_{prefix}",
            on_click=_publish_review, args=(restaurant, store, load_error, prefix),
            disabled=store is None or load_error or not getattr(store, "ratings_ready", True),
            width="stretch",
        )
