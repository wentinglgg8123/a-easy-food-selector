"""Python food discovery website with a quiet, light interface."""

from html import escape
from pathlib import Path
from unicodedata import normalize

import streamlit as st

from food_picker.catalog import location_label
from food_picker.defaults import DEFAULT_DATA_PATH
from food_picker.excel import build_template, export_restaurants, parse_excel
from food_picker.models import Filters, Restaurant, ValidationError
from food_picker.presentation import (
    area_label, coin_label, feature_labels, food_icon, map_url, poster_tone,
    price_label, price_legend_html, restaurant_card, table_rows,
)
from food_picker.reviews import ReviewError, configured_review_store
from food_picker.review_ui import render_reviews
from food_picker.session import PickerSession

ROOT = Path(__file__).parent
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FILTER_DEFAULTS = {
    "location_choices": [], "category_choices": [], "price_choices": [],
    "occasion_choice": [], "pace_choice": [], "query_choice": "", "include_closed": False,
    "max_price_choice": None,
}
CATALOG_PAGE_SIZE = 6
SEARCH_PAGE_SIZE = 3


class PageReviews:
    """Reuse one review connection and each restaurant's results within a page run."""

    def __init__(self) -> None:
        self.store = None
        self.failed = False
        self.reviews = {}
        self.notice_shown = False
        try:
            try:
                config = st.secrets.get("reviews", {})
            except FileNotFoundError:
                config = {}
            self.store = configured_review_store(config)
        except ReviewError:
            self.failed = True

    def load(self, restaurants: list[Restaurant]) -> dict:
        if self.store is not None and not self.failed:
            missing = list(dict.fromkeys(r.id for r in restaurants if r.id not in self.reviews))
            if missing:
                try:
                    self.reviews.update(self.store.load_reviews(missing, limit=3))
                except ReviewError:
                    self.failed = True
        return {r.id: self.reviews.get(r.id, []) for r in restaurants}

    def show_status(self) -> None:
        if self.notice_shown:
            return
        if self.failed:
            st.warning("評論暫時無法載入，請稍後再試。")
        elif self.store is None:
            st.info("評論尚未啟用，請網站管理員完成資料庫設定。")
        elif not self.store.ratings_ready:
            st.info("評分功能尚待啟用，請網站管理員執行資料庫升級。")
        else:
            return
        self.notice_shown = True


def picker() -> PickerSession:
    if "picker" not in st.session_state:
        st.session_state["picker"] = PickerSession()
    return st.session_state["picker"]


def reset_filters() -> None:
    for key, value in FILTER_DEFAULTS.items():
        st.session_state[key] = list(value) if isinstance(value, list) else value


def set_filter_choices(key: str, choices: list) -> None:
    st.session_state[key] = list(choices)


def set_catalog_page(index: int) -> None:
    st.session_state["catalog_page"] = max(0, index)


def set_search_page(index: int) -> None:
    st.session_state["search_page"] = max(0, index)


def read_filters() -> Filters:
    occasions = st.session_state.get("occasion_choice", [])
    paces = st.session_state.get("pace_choice", [])
    return Filters(
        locations=tuple(st.session_state.get("location_choices", [])),
        categories=tuple(st.session_state.get("category_choices", [])),
        price_levels=tuple(st.session_state.get("price_choices", [])),
        max_price=st.session_state.get("max_price_choice"),
        query=st.session_state.get("query_choice", ""),
        one_person="一個人吃" in occasions, dating="約會" in occasions,
        gathering="聚餐" in occasions, fast_serve="快速上菜" in paces,
        slow_eat="慢慢享用" in paces,
        include_closed=st.session_state.get("include_closed", False),
    )


def pick_meal() -> None:
    picker().choose(read_filters())


def clear_import() -> None:
    picker().reset()
    reset_filters()
    st.session_state["upload_generation"] = st.session_state.get("upload_generation", 0) + 1
    st.session_state["notice"] = "已恢復內建完整名單。"


@st.cache_data(show_spinner=False)
def template_bytes() -> bytes:
    return build_template()


@st.dialog("匯入餐廳名單", width="medium")
def import_dialog() -> None:
    st.write("網站已內建完整名單；也可以用你自己的 Excel 暫時替換。")
    uploaded = st.file_uploader(
        "選擇 Excel 餐廳名單", type=["xlsx"], max_upload_size=5,
        key=f"upload_{st.session_state.get('upload_generation', 0)}",
        help="讀取第一張工作表，最大 5 MB、5,000 筆資料。",
    )
    if st.button("確認匯入", type="primary", disabled=uploaded is None, width="stretch"):
        assert uploaded is not None
        try:
            result = parse_excel(uploaded.getvalue(), uploaded.name)
        except ValidationError as exc:
            st.error(str(exc))
        else:
            picker().import_catalog(result, uploaded.name)
            reset_filters()
            st.session_state["notice"] = f"已匯入 {len(result.restaurants)} 間餐廳，開始你的美食探索。"
            st.session_state["upload_generation"] = st.session_state.get("upload_generation", 0) + 1
            st.rerun()
    st.markdown("**支援這份名單的完整欄位：**")
    st.code("Restaurant, Location, Genre, Price, OnePerson, Dating,\nGathering, FastServe, SlowEat, Coordinates, Comments", language=None)
    st.caption("Price 填 1–5，依畫面上的金幣與價格區間對照；用餐情境／節奏填 O 表示有標記。Coordinates 填「緯度, 經度」。舊版中文欄位格式也可使用。")
    st.download_button(
        "下載 Excel 範本", template_bytes(), file_name="食刻決定_餐廳名單範本.xlsx",
        mime=MIME_XLSX, on_click="ignore", key="dialog_template", icon=":material/download:",
        width="stretch",
    )
    st.info("自訂名單會傳送至本站 Python 服務解析，僅保留於你的工作階段；重新整理後會回到內建名單。")


def render_header() -> None:
    brand, upload = st.columns([3, 1], vertical_alignment="center")
    with brand:
        st.html('<header class="brand" id="top"><h1><a href="#discover" class="wordmark">食刻決定</a></h1><span>找一家，吃頓好的。</span></header>')
    with upload:
        if st.button("匯入 Excel 名單", icon=":material/upload:", width="stretch"):
            import_dialog()


def render_restaurant_cards(restaurants: list[Restaurant], access: PageReviews, *, context: str) -> None:
    reviews = access.load(restaurants)
    access.show_status()
    for offset in range(0, len(restaurants), 3):
        columns = st.columns(3, gap="medium")
        for column, restaurant in zip(columns, restaurants[offset:offset + 3]):
            with column:
                key = f"restaurant_{restaurant.id}" if context == "catalog" else f"{context}_restaurant_{restaurant.id}"
                with st.container(border=True, key=key):
                    st.html(restaurant_card(restaurant))
                    render_reviews(restaurant, access.store, reviews.get(restaurant.id, []),
                                   load_error=access.failed, context=context)


def render_search(state: PickerSession, access: PageReviews) -> None:
    with st.container(key="top_search"):
        query = st.text_input(
            "搜尋店家", key="query_choice", max_chars=200,
            placeholder="輸入店名，按 Enter 搜尋並直接評論", icon=":material/search:",
        )
    normalized = normalize("NFKC", query).casefold().strip()
    if not normalized:
        return
    matches = [r for r in state.restaurants if normalized in normalize("NFKC", r.name).casefold()]
    signature = (normalized, tuple(r.id for r in matches))
    if st.session_state.get("search_signature") != signature:
        st.session_state["search_signature"] = signature
        st.session_state["search_page"] = 0
    page_count = max(1, (len(matches) + SEARCH_PAGE_SIZE - 1) // SEARCH_PAGE_SIZE)
    page = min(st.session_state.get("search_page", 0), page_count - 1)
    visible = matches[page * SEARCH_PAGE_SIZE:(page + 1) * SEARCH_PAGE_SIZE]
    with st.container(key="search_results"):
        st.subheader("搜尋結果", anchor=False)
        st.caption(f"找到 {len(matches)} 間店家 · 搜尋整份名單，不受下方篩選限制")
        if visible:
            render_restaurant_cards(visible, access, context="search")
            if page_count > 1:
                with st.container(horizontal=True, vertical_alignment="center", key="search_pagination"):
                    st.button("上一頁搜尋結果", key="search_previous", disabled=page == 0,
                              on_click=set_search_page, args=(page - 1,))
                    st.caption(f"搜尋結果第 {page + 1} / {page_count} 頁", width="stretch")
                    st.button("下一頁搜尋結果", key="search_next", disabled=page + 1 >= page_count,
                              on_click=set_search_page, args=(page + 1,))
        else:
            st.info("找不到這間店家，試試其他店名或較短的關鍵字。")


def render_source(state: PickerSession) -> None:
    if notice := st.session_state.pop("notice", None):
        st.success(notice)
    available = sum(not r.is_closed for r in state.restaurants)
    with st.container(key="source_strip"):
        info, action = st.columns([3, 1], vertical_alignment="center")
        with info:
            if state.is_default:
                st.markdown(f"**內建餐廳名單** · {len(state.restaurants)} 筆資料 · {available} 間可抽選")
                st.caption("已註記歇業的店家會保留供查詢，不參與推薦。")
            else:
                st.html('<p class="source-filename"><strong>目前名單：</strong> ' + escape(str(state.filename)) + '</p>')
                st.caption(f"{len(state.restaurants)} 筆資料 · {available} 間可抽選 · 僅保留於目前工作階段")
        with action:
            if state.is_default:
                st.html('<span class="source-badge"><span></span> 內建完整名單</span>')
            else:
                st.button("恢復內建名單", on_click=clear_import, width="stretch")
    if state.warnings:
        with st.expander(f"資料提醒（{len(state.warnings)} 項）"):
            for warning in state.warnings:
                st.warning(warning)


def render_filter_group(label: str, options: list, key: str, format_func=str) -> None:
    with st.container(key=f"group_{key}"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f"**{label}**", width="stretch")
            st.button("全選", key=f"select_all_{key}", on_click=set_filter_choices,
                      args=(key, options), type="tertiary", disabled=not options)
            st.button("取消", key=f"clear_{key}", on_click=set_filter_choices,
                      args=(key, []), type="tertiary", disabled=not options)
        if options:
            st.pills(label, options, selection_mode="multi", format_func=format_func,
                     key=key, width="stretch", wrap=True, label_visibility="collapsed")
        else:
            st.caption("名單未提供這項分類。")


def render_filters(state: PickerSession) -> Filters:
    st.html('<div id="discover"></div>')
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader("篩選條件", anchor=False, width="stretch")
        st.button("全部取消", key="clear_all_filters", on_click=reset_filters, type="tertiary")
    st.caption("可複選，再點一次取消；地點、料理與價格各組內符合任一項，未選則不限。")
    locations = sorted({r.location for r in state.restaurants if r.location}, key=location_label)
    places, cuisines = st.columns([1, 2], gap="large")
    with places:
        render_filter_group("地點", locations, "location_choices", location_label)
    with cuisines:
        render_filter_group("食物種類", sorted({r.category for r in state.restaurants}), "category_choices")
    prices, occasions, paces = st.columns([1.2, 1, 1], gap="large")
    with prices:
        render_filter_group("價格等級", list(range(1, 6)), "price_choices", coin_label)
    with occasions:
        render_filter_group("用餐情境", ["一個人吃", "約會", "聚餐"], "occasion_choice")
        st.caption("需同時符合所選情境")
    with paces:
        render_filter_group("用餐節奏", ["快速上菜", "慢慢享用"], "pace_choice")
        st.caption("需同時符合所選節奏")
    st.html(price_legend_html())
    with st.expander("更多選項"):
        st.checkbox("包含已註記歇業店家", key="include_closed", help="僅供瀏覽與查詢；歇業店家不參與隨機推薦。")
        if any(r.price is not None for r in state.restaurants):
            st.number_input("最高均消（元）", min_value=0.0, value=None, key="max_price_choice", help="僅適用舊版中文名單中提供均消的資料。")
    filters = read_filters()
    candidates = state.candidates(filters)
    available = sum(not r.is_closed for r in candidates)
    st.caption(f"{len(candidates)} 間符合條件 · {available} 間可抽選")
    return filters


def render_recommendation(state: PickerSession, filters: Filters, access: PageReviews) -> None:
    candidates = state.candidates(filters)
    available = sum(not r.is_closed for r in candidates)
    current = state.current(filters)
    st.html('<div class="pick-topline"><span>隨機推薦</span><span>給下一餐一點靈感</span></div>')
    if not available:
        st.html('<div class="empty-result"><h2>沒有符合條件的餐廳</h2><p>取消幾個條件，再試一次。</p></div>')
    elif current is None:
        st.caption("選好條件，按一下就能推薦一家。")
    else:
        tags = ''.join(f'<span class="tag">{escape(label)}</span>' for label in feature_labels(current))
        st.html(
            f'<section class="recommendation tone-{poster_tone(current)}" aria-label="餐廳推薦結果">'
            '<div class="result-visual" aria-hidden="true">'
            f'<span class="result-icon">{food_icon(current)}</span></div>'
            '<div class="result-copy"><p class="result-eyebrow">這次推薦給你</p>'
            f'<h2>{escape(current.name)}</h2>'
            f'<div class="result-meta"><a class="location-link" href="{escape(map_url(current), quote=True)}" target="_blank" rel="noopener noreferrer" aria-label="在 Google 地圖搜尋{escape(current.name, quote=True)}">{escape(current.address or area_label(current))} ↗</a><span>{escape(current.category)}</span><span>{escape(price_label(current))}</span></div>'
            f'<div class="result-tags">{tags}</div>'
            f'<p class="result-note">{escape(current.note or "名單沒有額外備註，出發前記得確認營業資訊。")}</p>'
            '</div></section>'
        )
        st.link_button("在 Google 地圖查看", map_url(current), icon=":material/map:")
    st.button(
        "再推薦一家" if current else "幫我決定這一餐", on_click=pick_meal,
        type="primary", icon=":material/shuffle:", disabled=not available,
        width="stretch", key="pick_meal",
    )
    st.caption("目前只有 1 間可抽選，會推薦同一家。" if available == 1 else "每間符合條件的可用店家均等抽選，連續推薦不重複上一間。")
    if current is not None:
        reviews = access.load([current])
        access.show_status()
        with st.container(key="recommendation_reviews"):
            render_reviews(current, access.store, reviews.get(current.id, []),
                           load_error=access.failed, context="recommendation")


def render_rail(title: str, subtitle: str, restaurants: list[Restaurant], key: str) -> None:
    if not restaurants:
        return
    st.html(
        f'<section class="collection" aria-label="{escape(title, quote=True)}" id="{key}">'
        f'<div class="collection-heading"><h2>{escape(title)}</h2><span>{escape(subtitle)}</span></div>'
        '<div class="poster-rail">' + ''.join(restaurant_card(r, i) for i, r in enumerate(restaurants)) + '</div></section>'
    )


def render_catalog(state: PickerSession, filters: Filters, access: PageReviews) -> None:
    candidates = state.candidates(filters)
    signature = tuple(restaurant.id for restaurant in candidates)
    if st.session_state.get("catalog_signature") != signature:
        st.session_state["catalog_page"] = 0
        st.session_state["catalog_signature"] = signature
    page_count = max(1, (len(candidates) + CATALOG_PAGE_SIZE - 1) // CATALOG_PAGE_SIZE)
    page = min(st.session_state.get("catalog_page", 0), page_count - 1)
    visible = candidates[page * CATALOG_PAGE_SIZE:(page + 1) * CATALOG_PAGE_SIZE]
    st.html('<div id="catalog"></div>')
    st.subheader("餐廳名單", anchor=False)
    st.caption(f"{len(candidates)} 間符合條件 · 每頁 {CATALOG_PAGE_SIZE} 間，可直接在餐廳下方留言")
    if visible:
        with st.container(key="catalog_grid"):
            render_restaurant_cards(visible, access, context="catalog")
        with st.container(horizontal=True, vertical_alignment="center", key="catalog_pagination"):
            st.button("上一頁", key="catalog_previous", disabled=page == 0,
                      on_click=set_catalog_page, args=(page - 1,))
            st.caption(f"第 {page + 1} / {page_count} 頁", width="stretch")
            st.button("下一頁", key="catalog_next", disabled=page + 1 >= page_count,
                      on_click=set_catalog_page, args=(page + 1,))
    if not candidates:
        st.info("沒有符合條件的餐廳，調整上方篩選再試試。")
    with st.expander(f"查看全部符合條件的餐廳（{len(candidates)} 間）"):
        if candidates:
            st.dataframe(
                table_rows(candidates), hide_index=True, width="stretch",
                column_config={"Google 地圖": st.column_config.LinkColumn(
                    "Google 地圖", display_text="開啟餐廳地圖", help="以店名與地址／地點搜尋 Google 地圖。",
                )},
            )
            st.download_button("匯出篩選名單", export_restaurants(candidates), file_name="食刻決定_篩選餐廳.xlsx", mime=MIME_XLSX, on_click="ignore", icon=":material/download:")
        else:
            st.write("目前沒有符合條件的餐廳。")
    if state.history:
        with st.expander("最近推薦"):
            render_rail("最近推薦", "保留最近 3 間不同的推薦", state.history, "recent")


def render_footer(state: PickerSession) -> None:
    render_source(state)
    st.download_button("下載完整名單", DEFAULT_DATA_PATH.read_bytes(), file_name="食物.xlsx", mime=MIME_XLSX, on_click="ignore", icon=":material/download:")
    st.caption("金幣依你指定的價格區間對照 Excel 分級；未填價格不推測。店家資訊與實際消費請以現場為準。")
    st.caption("內建名單供所有訪客使用；你額外匯入的名單僅存於自己的工作階段，重新整理後會恢復內建名單。")


def main() -> None:
    st.set_page_config(page_title="食刻決定｜簡單找到下一餐", page_icon="🍽️", layout="wide")
    st.html(ROOT / "static" / "styles.css")
    try:
        state = picker()
    except (OSError, ValidationError) as exc:
        st.error(f"無法載入內建名單：{exc}")
        st.stop()
    access = PageReviews()
    render_search(state, access)
    render_header()
    with st.container(border=True, key="filters_panel"):
        filters = render_filters(state)
    with st.container(border=True, key="pick_panel"):
        render_recommendation(state, filters, access)
    render_catalog(state, filters, access)
    render_footer(state)


if __name__ == "__main__":
    main()
