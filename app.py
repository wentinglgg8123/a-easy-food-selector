"""Streamlit entry point: the restaurant website is implemented in Python."""

from html import escape
from pathlib import Path

import streamlit as st

from food_picker.excel import build_template, export_restaurants, parse_excel
from food_picker.models import Filters, ValidationError
from food_picker.presentation import (
    area_label,
    distance_label,
    map_url,
    price_label,
    restaurant_card,
    table_rows,
)
from food_picker.session import PickerSession

ROOT = Path(__file__).parent
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
AREA_OPTIONS = {"都可以": "all", "清大校內": "campus", "校園周邊": "nearby"}
BUDGET_OPTIONS = {
    "不限預算": None,
    "NT$ 100 以內": 100.0,
    "NT$ 150 以內": 150.0,
    "NT$ 200 以內": 200.0,
    "NT$ 300 以內": 300.0,
}
FILTER_DEFAULTS = {
    "area_choice": "都可以",
    "category_choice": "不挑食",
    "budget_choice": "不限預算",
    "query_choice": "",
}


def picker() -> PickerSession:
    if "picker" not in st.session_state:
        st.session_state["picker"] = PickerSession()
    return st.session_state["picker"]


def reset_filters() -> None:
    for key, value in FILTER_DEFAULTS.items():
        st.session_state[key] = value


def read_filters() -> Filters:
    category = st.session_state.get("category_choice", "不挑食")
    return Filters(
        area=AREA_OPTIONS[st.session_state.get("area_choice", "都可以")],
        category="all" if category == "不挑食" else category,
        max_price=BUDGET_OPTIONS[st.session_state.get("budget_choice", "不限預算")],
        query=st.session_state.get("query_choice", ""),
    )


def pick_meal() -> None:
    picker().choose(read_filters())


def clear_import() -> None:
    picker().reset()
    reset_filters()
    st.session_state["upload_generation"] = st.session_state.get("upload_generation", 0) + 1
    st.session_state["notice"] = "已清除匯入資料，切回示範名單。"


@st.cache_data(show_spinner=False)
def template_bytes() -> bytes:
    # Only the shared fictional template is cached, never a visitor's uploaded catalog.
    return build_template()


@st.dialog("帶上你的美食名單", width="medium")
def import_dialog() -> None:
    st.write("一份 Excel，就能讓「吃什麼」簡單一點。")
    uploaded = st.file_uploader(
        "選擇 Excel 餐廳名單",
        type=["xlsx"],
        max_upload_size=5,
        key=f"upload_{st.session_state.get('upload_generation', 0)}",
        help="第一張工作表、最大 5 MB，最多 5,000 筆餐廳。",
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
            st.session_state["notice"] = f"已匯入 {len(result.restaurants)} 間餐廳，開飯囉！"
            st.session_state["upload_generation"] = st.session_state.get("upload_generation", 0) + 1
            st.rerun()
    st.markdown("**第一列欄位：** `餐廳名稱 *`、`區域 *`、`類型`、`均消`、`距離（公里）`、`地址`、`備註`。")
    st.caption("* 必填。區域填「清大校內」或「校園周邊」；均消填新台幣數字，距離以公里填寫。")
    st.caption("請以一致的基準點（例如清大校門）核對周邊 2 公里範圍；未提供距離的店家將標示「距離未驗證」。")
    st.download_button(
        "下載含示範資料的 Excel 範本",
        template_bytes(),
        file_name="食刻決定_餐廳名單範本.xlsx",
        mime=MIME_XLSX,
        on_click="ignore",
        key="dialog_template",
        icon=":material/download:",
        width="stretch",
    )
    st.info("Excel 會傳送至本站 Python 伺服器解析，僅保留於本次工作階段的記憶體。重新整理或關閉分頁後可能需要重新匯入。")


def render_header() -> None:
    brand, upload = st.columns([3, 1], vertical_alignment="center")
    with brand:
        st.html('<header class="brand">🍴 食刻決定<span>.</span><small>給清大人的美食靈感</small></header>')
    with upload:
        if st.button("匯入 Excel 名單", icon=":material/upload:", width="stretch"):
            import_dialog()
    st.html(
        '<section class="hero">'
        '<div><p class="eyebrow">● NTHU FOOD PICKER</p>'
        '<h1>今天，吃點<span>什麼？</span></h1>'
        '<p>把選擇困難交給我們，把好胃口留給美食。<br>'
        '從清大校內到周邊 2 公里，下一餐交給一點驚喜。</p>'
        '<p class="hero-tags">⌖ 清大生活圈　♡ 每一餐，都有新靈感</p></div>'
        '<img src="app/static/meal.svg" alt="一碗有蔬菜、雞蛋與配菜的飯">'
        '</section>'
    )


def render_source(state: PickerSession) -> None:
    if notice := st.session_state.pop("notice", None):
        st.success(notice)
    with st.container(key="source_strip"):
        info, actions = st.columns([3, 1], vertical_alignment="center")
        with info:
            if state.is_demo:
                st.markdown("**先用示範名單，試試手氣**")
                st.caption("8 間虛構餐廳 · 匯入你的 Excel，換成真實美食")
            else:
                st.markdown(f"**目前名單：** {state.filename}")
                st.caption(f"{len(state.restaurants)} 間餐廳 · 僅保留於目前工作階段")
        with actions:
            if state.is_demo:
                st.html('<span class="source-badge">示範資料</span>')
            else:
                st.button("清除並回到示範", on_click=clear_import, width="stretch")
    if state.warnings:
        with st.expander(f"匯入提醒（{len(state.warnings)} 項）"):
            for warning in state.warnings:
                st.warning(warning)


def render_filters(state: PickerSession) -> Filters:
    st.subheader("這餐，想吃什麼", anchor=False)
    st.radio("用餐範圍", list(AREA_OPTIONS), horizontal=True, key="area_choice")
    categories = sorted({r.category for r in state.restaurants})
    st.selectbox("今天的口味", ["不挑食", *categories], key="category_choice")
    st.selectbox("每人預算上限", list(BUDGET_OPTIONS), key="budget_choice")
    st.text_input("搜尋一點靈感", placeholder="餐廳、地址或餐點類型", key="query_choice", max_chars=200)
    filters = read_filters()
    st.caption(f"{len(state.candidates(filters))} 間餐廳符合你的心情")
    st.button("重設篩選", on_click=reset_filters, type="tertiary")
    return filters


def render_recommendation(state: PickerSession, filters: Filters) -> None:
    candidates = state.candidates(filters)
    current = state.current(filters)
    st.html('<div class="pick-topline">✧ LET FATE DECIDE</div>')
    if not candidates:
        st.html('<div class="empty-result"><div>⌕</div><h2>這次條件有點挑嘴</h2><p>目前沒有符合條件的餐廳。<br>放寬預算或口味，讓選擇多一點吧。</p></div>')
    elif current is None:
        st.html('<div class="empty-result"><div class="dice">⚄</div><h2>下一餐，交給一點驚喜</h2><p>不用再問「隨便吃什麼」。<br>按一下，讓命運幫你選一家。</p></div>')
    else:
        st.html(
            '<section class="recommendation" aria-label="餐廳推薦結果">'
            '<p class="result-eyebrow">就是這間，出發吧！</p>'
            f'<h2>{escape(current.name)}</h2>'
            f'<p><span class="tag">{escape(area_label(current))}</span>'
            f'<span class="tag">{escape(current.category)}</span></p>'
            f'<p class="result-details">{escape(price_label(current))}　⌖ {escape(distance_label(current))}</p>'
            f'<p>{escape(current.address or "名單未提供地址")}</p>'
            f'<p class="result-note">{escape(current.note)}</p>'
            '</section>'
        )
        if not state.is_demo and not current.name.startswith("示範・"):
            st.link_button("在 Google 地圖查看", map_url(current), icon=":material/map:")
    st.button(
        "再抽一間，換個靈感" if current else "幫我決定這一餐",
        on_click=pick_meal,
        type="primary",
        icon=":material/shuffle:",
        disabled=not candidates,
        width="stretch",
        key="pick_meal",
    )
    st.caption("目前只有 1 間符合條件，會推薦同一家" if len(candidates) == 1 else "符合條件的餐廳隨機抽選，連續推薦不重複上一間")
    st.html('<p class="pick-footer">♡ 每天最幸福的煩惱，就是下一餐吃什麼。</p>')


def render_catalog(state: PickerSession, filters: Filters) -> None:
    candidates = state.candidates(filters)
    st.subheader("剛剛的美食靈感" if state.history else "美食口袋名單", anchor=False)
    st.caption("最近 3 間不同的推薦，調整篩選不會清除紀錄。" if state.history else "先看一眼，也許心裡已經有了答案。")
    cards = state.history if state.history else candidates[:3]
    if cards:
        st.html('<div class="food-grid">' + ''.join(restaurant_card(r) for r in cards) + '</div>')
    else:
        st.info("沒有符合條件的餐廳，試著調整上方篩選。")
    with st.expander(f"查看全部符合條件的餐廳（{len(candidates)} 間）"):
        if candidates:
            st.dataframe(table_rows(candidates), hide_index=True, width="stretch")
            st.download_button(
                "匯出篩選名單",
                export_restaurants(candidates),
                file_name="食刻決定_篩選餐廳.xlsx",
                mime=MIME_XLSX,
                on_click="ignore",
                icon=":material/download:",
            )
        else:
            st.write("目前沒有符合條件的餐廳。")


def render_footer(state: PickerSession) -> None:
    with st.container(key="template_callout"):
        text, download = st.columns([2, 1], vertical_alignment="center")
        with text:
            st.markdown("**把你的美食口袋，變成下一餐的靈感。**")
            st.caption("整理好 Excel 名單，匯入就能開始。")
        with download:
            st.download_button(
                "下載 Excel 範本",
                template_bytes(),
                file_name="食刻決定_餐廳名單範本.xlsx",
                mime=MIME_XLSX,
                on_click="ignore",
                icon=":material/download:",
                width="stretch",
            )
    if state.is_demo:
        st.caption("目前為 8 筆虛構示範資料，並非清大真實或完整店家名單。請匯入經確認的名單後使用。")
    st.caption("區域與距離依 Excel 提供，未自動定位或核實；校外已知超過 2 公里的店家會略過。店家、價格與營業資訊請於出發前確認。")
    st.caption("名單由本站 Python 伺服器暫存於本次工作階段；不會存入檔案或跨瀏覽器同步，重新整理後可能需要再次匯入。")
    st.html('<footer class="site-footer"><span>食刻決定.</span><span>好好吃飯，好好生活 ♡</span></footer>')


def main() -> None:
    st.set_page_config(page_title="食刻決定｜清大美食隨機選", page_icon="🍴", layout="wide")
    st.html(ROOT / "static" / "styles.css")
    state = picker()
    render_header()
    render_source(state)
    left, right = st.columns([1, 2], gap="large")
    with left:
        with st.container(border=True, key="filters_panel"):
            filters = render_filters(state)
    with right:
        with st.container(border=True, key="pick_panel"):
            render_recommendation(state, filters)
    render_catalog(state, filters)
    render_footer(state)


if __name__ == "__main__":
    main()
