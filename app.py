"""Python food discovery website with a cinema-inspired dark interface."""

from html import escape
from pathlib import Path

import streamlit as st

from food_picker.catalog import location_label
from food_picker.defaults import DEFAULT_DATA_PATH
from food_picker.excel import build_template, export_restaurants, parse_excel
from food_picker.models import Filters, Restaurant, ValidationError
from food_picker.presentation import (
    area_label, feature_labels, food_icon, map_url, poster_tone,
    price_label, restaurant_card, table_rows,
)
from food_picker.session import PickerSession

ROOT = Path(__file__).parent
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PRICE_OPTIONS = {"不限等級": None, **{f"等級 {i} 以內": i for i in range(1, 6)}}
FILTER_DEFAULTS = {
    "location_choice": "all", "category_choice": "所有種類", "price_choice": "不限等級",
    "occasion_choice": [], "pace_choice": [], "query_choice": "", "include_closed": False,
    "max_price_choice": None,
}


def picker() -> PickerSession:
    if "picker" not in st.session_state:
        st.session_state["picker"] = PickerSession()
    return st.session_state["picker"]


def reset_filters() -> None:
    for key, value in FILTER_DEFAULTS.items():
        st.session_state[key] = list(value) if isinstance(value, list) else value


def read_filters() -> Filters:
    category = st.session_state.get("category_choice", "所有種類")
    occasions = st.session_state.get("occasion_choice", [])
    paces = st.session_state.get("pace_choice", [])
    return Filters(
        location=st.session_state.get("location_choice", "all"),
        category="all" if category == "所有種類" else category,
        max_price_level=PRICE_OPTIONS[st.session_state.get("price_choice", "不限等級")],
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


@st.dialog("帶上你的美食片單", width="medium")
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
    st.caption("Price 為 1–5 的價格等級；用餐情境／節奏填 O 表示有標記。Coordinates 填「緯度, 經度」。舊版中文欄位格式也可使用。")
    st.download_button(
        "下載 Excel 範本", template_bytes(), file_name="食刻決定_餐廳名單範本.xlsx",
        mime=MIME_XLSX, on_click="ignore", key="dialog_template", icon=":material/download:",
        width="stretch",
    )
    st.info("自訂名單會傳送至本站 Python 服務解析，僅保留於你的工作階段；重新整理後會回到內建名單。")


def render_header() -> None:
    brand, upload = st.columns([3, 1], vertical_alignment="center")
    with brand:
        st.html('<header class="brand"><a href="#top" class="wordmark">FOODFLIX</a><span class="brand-sub">食刻決定</span><nav><a href="#discover">探索美食</a><a href="#catalog">美食片單</a></nav><span class="profile" aria-hidden="true">F</span></header>')
    with upload:
        if st.button("匯入 Excel 名單", icon=":material/upload:", width="stretch"):
            import_dialog()


def render_hero(state: PickerSession) -> None:
    count = len(state.restaurants)
    places = len({r.location or r.area for r in state.restaurants})
    genres = len({r.category for r in state.restaurants})
    st.html(
        '<section class="hero" id="top">'
        '<div class="hero-copy"><p class="eyebrow"><span>F</span> ORIGINAL FOOD COLLECTION</p>'
        '<h1>下一餐，<br>值得<span>一看。</span></h1>'
        '<p class="hero-kicker">你的下一口驚喜，現在開播。</p>'
        '<p class="hero-description">選擇地點、料理與用餐情境，<br>讓今天的美食主角自己出場。</p>'
        f'<div class="hero-facts"><strong>{count} 間餐廳</strong><span>{places} 個地點</span><span>{genres} 種料理</span></div>'
        '<a class="hero-link" href="#discover">▶ 開始探索</a>'
        '</div><div class="hero-visual" aria-hidden="true"><div class="spotlight"></div>'
        '<img src="app/static/meal.svg" alt=""><span class="hero-stamp">TONIGHT’S SPECIAL</span>'
        '<span class="hero-visual-note">每一餐，都有值得期待的劇情。</span></div>'
        '<div class="hero-rating">美食片單 <span>｜</span> 隨機驚喜 <span>｜</span> 由你決定</div>'
        '</section>'
    )


def render_source(state: PickerSession) -> None:
    if notice := st.session_state.pop("notice", None):
        st.success(notice)
    available = sum(not r.is_closed for r in state.restaurants)
    with st.container(key="source_strip"):
        info, action = st.columns([3, 1], vertical_alignment="center")
        with info:
            if state.is_default:
                st.markdown(f"**完整片單已就緒** · {len(state.restaurants)} 筆資料 · {available} 間可抽選")
                st.caption("來自你提供的 Excel，所有訪客開啟網站即可使用。")
            else:
                st.html('<p class="source-filename"><strong>目前片單：</strong> ' + escape(str(state.filename)) + '</p>')
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


def render_filters(state: PickerSession) -> Filters:
    st.html('<div class="panel-label" id="discover">CUSTOMIZE YOUR NEXT BITE</div>')
    st.subheader("選擇你的用餐劇情", anchor=False)
    locations = sorted({r.location for r in state.restaurants if r.location}, key=location_label)
    st.selectbox("地點", ["all", *locations], format_func=lambda code: "所有地點" if code == "all" else location_label(code), key="location_choice")
    st.selectbox("食物種類", ["所有種類", *sorted({r.category for r in state.restaurants})], key="category_choice")
    st.selectbox("價格等級", list(PRICE_OPTIONS), key="price_choice", help="保留 Excel 的 1–5 分級，未換算成新臺幣；選擇上限時不包含未分級資料。")
    st.multiselect("用餐情境", ["一個人吃", "約會", "聚餐"], key="occasion_choice", placeholder="所有情境", help="多選時，店家需同時有這些標記。未標記不代表不適合。")
    st.multiselect("用餐節奏", ["快速上菜", "慢慢享用"], key="pace_choice", placeholder="不限節奏", help="多選時需同時符合；標記來自原始 Excel。")
    st.text_input("搜尋餐廳", placeholder="店名、地點、料理或備註", key="query_choice", max_chars=200)
    with st.expander("更多選項"):
        st.checkbox("包含已註記歇業店家", key="include_closed", help="僅供瀏覽與查詢；歇業店家不參與隨機推薦。")
        if any(r.price is not None for r in state.restaurants):
            st.number_input("最高均消（元）", min_value=0.0, value=None, key="max_price_choice", help="僅適用舊版中文名單中提供均消的資料。")
    filters = read_filters()
    candidates = state.candidates(filters)
    available = sum(not r.is_closed for r in candidates)
    st.caption(f"{len(candidates)} 間符合條件 · {available} 間可抽選")
    st.button("重設篩選", on_click=reset_filters, type="tertiary")
    return filters


def render_recommendation(state: PickerSession, filters: Filters) -> None:
    candidates = state.candidates(filters)
    available = sum(not r.is_closed for r in candidates)
    current = state.current(filters)
    st.html('<div class="pick-topline"><span>NOW PICKING</span><span class="live-dot"></span> 今天的主角</div>')
    if not available:
        st.html('<div class="empty-result"><div class="empty-symbol">⌕</div><p class="result-eyebrow">NO MATCH THIS TIME</p><h2>這個劇情，有點挑嘴。</h2><p>目前沒有可推薦的餐廳。<br>試試其他地點、料理或用餐情境。</p></div>')
    elif current is None:
        st.html('<div class="empty-result"><div class="dice" aria-hidden="true">⚄</div><p class="result-eyebrow">READY FOR A PLOT TWIST?</p><h2>好吃的，下一秒登場。</h2><p>不用再問「隨便吃什麼」。<br>按下播放，讓命運幫你選一家。</p><div class="empty-tags"><span>隨機驚喜</span><span>不連續重複</span><span>專屬你的篩選</span></div></div>')
    else:
        tags = ''.join(f'<span class="tag">{escape(label)}</span>' for label in feature_labels(current))
        st.html(
            f'<section class="recommendation tone-{poster_tone(current)}" aria-label="餐廳推薦結果">'
            '<div class="result-visual" aria-hidden="true">'
            f'<span class="result-icon">{food_icon(current)}</span><span class="result-watermark">F</span></div>'
            '<div class="result-copy"><p class="result-eyebrow">YOUR NEXT FOOD EPISODE</p>'
            f'<h2>{escape(current.name)}</h2>'
            f'<div class="result-meta"><strong>{escape(area_label(current))}</strong><span>{escape(current.category)}</span><span>{escape(price_label(current))}</span></div>'
            f'<div class="result-tags">{tags}</div>'
            f'<p class="result-note">{escape(current.note or "名單沒有額外備註，出發前記得確認營業資訊。")}</p>'
            '</div></section>'
        )
        st.link_button("在 Google 地圖查看", map_url(current), icon=":material/map:")
    st.button(
        "再抽一間，換個劇情" if current else "幫我決定這一餐", on_click=pick_meal,
        type="primary", icon=":material/play_arrow:", disabled=not available,
        width="stretch", key="pick_meal",
    )
    st.caption("目前只有 1 間可抽選，會推薦同一家。" if available == 1 else "每間符合條件的可用店家均等抽選，連續推薦不重複上一間。")
    st.html('<div class="pick-footer">下一餐的主角，值得好好期待。</div>')


def render_rail(title: str, subtitle: str, restaurants: list[Restaurant], key: str) -> None:
    if not restaurants:
        return
    st.html(
        f'<section class="collection" aria-label="{escape(title, quote=True)}" id="{key}">'
        f'<div class="collection-heading"><h2>{escape(title)}</h2><span>{escape(subtitle)}</span></div>'
        '<div class="poster-rail">' + ''.join(restaurant_card(r, i) for i, r in enumerate(restaurants)) + '</div></section>'
    )


def render_catalog(state: PickerSession, filters: Filters) -> None:
    candidates = state.candidates(filters)
    render_rail("最近播放的美食" if state.history else "你的下一餐片單", "左右滑動，探索更多美食", state.history or candidates[:12], "catalog")
    if state.history:
        render_rail("為你篩選的美食", f"{len(candidates)} 間符合條件 · 顯示前 12 間", candidates[:12], "matches")
    render_rail("一人食，也值得好好吃", "原表標記適合單人用餐", [r for r in candidates if r.one_person and not r.is_closed][:10], "solo")
    render_rail("把美食，留給相聚的時刻", "約會與聚餐的用餐靈感", [r for r in candidates if (r.dating or r.gathering) and not r.is_closed][:10], "together")
    if not candidates:
        st.info("沒有符合條件的餐廳，調整上方篩選再試試。")
    with st.expander(f"查看全部符合條件的餐廳（{len(candidates)} 間）"):
        if candidates:
            st.dataframe(table_rows(candidates), hide_index=True, width="stretch")
            st.download_button("匯出篩選名單", export_restaurants(candidates), file_name="食刻決定_篩選餐廳.xlsx", mime=MIME_XLSX, on_click="ignore", icon=":material/download:")
        else:
            st.write("目前沒有符合條件的餐廳。")


def render_footer(state: PickerSession) -> None:
    with st.container(key="download_panel"):
        text, action = st.columns([2, 1], vertical_alignment="center")
        with text:
            st.markdown("**把整份美食片單，收藏起來。**")
            st.caption("下載你提供的原始 Excel，保留所有地點、料理與用餐標記。")
        with action:
            st.download_button("下載完整名單", DEFAULT_DATA_PATH.read_bytes(), file_name="食物.xlsx", mime=MIME_XLSX, on_click="ignore", icon=":material/download:", width="stretch")
    st.caption("價格以 Excel 的 1–5 等級呈現，未定義對應金額；空白標記代表原表未提供。店家營業狀態、情境與價格未即時查證，出發前請再次確認。")
    st.caption("內建名單供所有訪客使用；你額外匯入的名單僅存於自己的工作階段，重新整理後會恢復內建名單。")
    st.html('<footer class="site-footer"><div><span class="footer-wordmark">FOODFLIX</span><span>食刻決定 · 把下一餐，變成值得期待的事。</span></div><span>下一餐，現在開播。</span></footer>')


def main() -> None:
    st.set_page_config(page_title="FOODFLIX 食刻決定｜你的下一餐，現在開播", page_icon="🍿", layout="wide")
    st.html(ROOT / "static" / "styles.css")
    try:
        state = picker()
    except (OSError, ValidationError) as exc:
        st.error(f"無法載入內建名單：{exc}")
        st.stop()
    render_header()
    render_hero(state)
    render_source(state)
    left, right = st.columns([1, 2], gap="large")
    with left:
        with st.container(border=True, key="filters_panel"):
            filters = render_filters(state)
    with right:
        with st.container(border=True, key="pick_panel"):
            render_recommendation(state, filters)
        st.html('<div class="data-legend"><span class="legend-mark">F</span><div><strong>你的偏好，就是推薦的線索。</strong><p>從地點、料理，到一人食或聚餐，所有條件會一起篩選。</p></div></div>')
    render_catalog(state, filters)
    render_footer(state)


if __name__ == "__main__":
    main()
