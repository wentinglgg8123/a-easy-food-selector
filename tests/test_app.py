"""Exercise the public default catalog, rendered filters, and session callbacks."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from food_picker.catalog import parse_rows
from food_picker.excel import EXCEL_HEADERS, LEGACY_HEADERS

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def app():
    result = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    assert not result.exception
    return result


def names(app):
    return app.dataframe[0].value["餐廳名稱"].tolist() if len(app.dataframe) else []


def test_initial_page_loads_real_catalog_for_every_visitor(app):
    state = app.session_state["picker"]
    assert state.is_default and not state.is_demo and state.selected is None
    assert state.filename is None and len(state.restaurants) == 176
    assert len(names(app)) == 175
    assert "孫東寶牛排" in names(app)
    assert "郭董麻辣牛肉麵" not in names(app)
    assert not app.button(key="pick_meal").disabled
    assert app.selectbox(key="location_choice").value == "all"
    assert len(app.selectbox(key="location_choice").options) == 9
    assert len(app.selectbox(key="category_choice").options) == 26
    assert any("FOODFLIX" in element.value for element in app.get("html"))


def test_pick_renders_real_recommendation_without_consecutive_repeats(app):
    app.button(key="pick_meal").click().run()
    assert not app.exception
    first = app.session_state["picker"].selected
    assert first is not None and not first.is_closed
    assert any('aria-label="餐廳推薦結果"' in element.value for element in app.get("html"))

    app.button(key="pick_meal").click().run()
    state = app.session_state["picker"]
    assert not app.exception
    assert state.selected.id != first.id
    assert state.history[0] == state.selected
    assert len(state.history) == 2


def test_location_genre_price_and_occasion_filters_combine_on_actual_data(app):
    app.selectbox(key="location_choice").set_value("Gongguan")
    app.selectbox(key="category_choice").set_value("牛排")
    app.selectbox(key="price_choice").set_value("等級 1 以內")
    app.multiselect(key="occasion_choice").set_value(["約會", "聚餐"])
    app.run()
    assert not app.exception
    assert names(app) == ["孫東寶牛排"]
    app.button(key="pick_meal").click().run()
    selected = app.session_state["picker"].selected
    assert selected.name == "孫東寶牛排"
    assert selected.price is None and selected.price_level == 1


def test_all_five_feature_flags_are_required_when_selected(app):
    result = parse_rows([
        EXCEL_HEADERS,
        ["測試旗標完整店", "Gongguan", "Bento", 2, "O", "O", "O", "O", "O", "25.03, 121.54", "有座位"],
        ["測試缺少節奏店", "Gongguan", "Bento", 2, "O", "O", "O", "", "O", "25.04, 121.55", ""],
        ["測試別區店", "Shida", "Bento", 2, "O", "O", "O", "O", "O", "25.05, 121.56", ""],
    ])
    app.session_state["picker"].import_catalog(result, "情境名單.xlsx")
    app.run()
    app.selectbox(key="location_choice").set_value("Gongguan")
    app.selectbox(key="category_choice").set_value("便當")
    app.selectbox(key="price_choice").set_value("等級 2 以內")
    app.multiselect(key="occasion_choice").set_value(["一個人吃", "約會", "聚餐"])
    app.multiselect(key="pace_choice").set_value(["快速上菜", "慢慢享用"])
    app.text_input(key="query_choice").set_value("測試")
    app.run()
    assert not app.exception
    assert names(app) == ["測試旗標完整店"]
    app.button(key="pick_meal").click().run()
    assert app.session_state["picker"].selected.name == "測試旗標完整店"


def test_closed_restaurant_can_be_browsed_but_cannot_be_recommended(app):
    app.text_input(key="query_choice").set_value("郭董麻辣牛肉麵").run()
    assert not app.exception
    assert names(app) == []
    app.checkbox(key="include_closed").check().run()
    assert not app.exception
    assert names(app) == ["郭董麻辣牛肉麵"]
    assert any("關門了" in str(value) for value in app.dataframe[0].value.iloc[0])
    assert app.button(key="pick_meal").disabled
    assert app.session_state["picker"].selected is None


def test_changing_location_hides_selection_and_preserves_history(app):
    app.selectbox(key="location_choice").set_value("Gongguan").run()
    app.button(key="pick_meal").click().run()
    chosen = app.session_state["picker"].selected
    assert chosen.location == "Gongguan"
    app.selectbox(key="location_choice").set_value("Shida").run()
    assert not app.exception
    assert not any('aria-label="餐廳推薦結果"' in element.value for element in app.get("html"))
    assert app.session_state["picker"].history == [chosen]
    assert len(names(app)) == 3


def test_legacy_custom_catalog_can_be_cleared_back_to_original_public_data(app):
    result = parse_rows([
        LEGACY_HEADERS,
        ["測試舊版餐廳", "校園周邊", "素食", 90, None, "測試街 1 號", "僅供測試"],
    ])
    app.session_state["picker"].import_catalog(result, "我的餐廳.xlsx")
    app.run()
    assert not app.exception
    assert names(app) == ["測試舊版餐廳"]
    assert any("我的餐廳.xlsx" in text.value for text in app.get("html"))
    assert any("未填距離" in warning.value for warning in app.warning)
    assert "素食" in app.selectbox(key="category_choice").options
    app.button(key="pick_meal").click().run()
    assert app.session_state["picker"].selected.name == "測試舊版餐廳"

    next(button for button in app.button if button.label == "恢復內建名單").click().run()
    assert not app.exception
    state = app.session_state["picker"]
    assert state.is_default and state.filename is None
    assert len(state.restaurants) == 176 and len(names(app)) == 175
    assert state.selected is None and state.history == []
    assert state.warnings == [] and len(app.warning) == 0
    assert "我的餐廳.xlsx" not in " ".join(text.value for text in app.get("html"))


def test_empty_search_disables_pick_and_reset_clears_every_filter(app):
    app.selectbox(key="location_choice").set_value("Gongguan")
    app.selectbox(key="category_choice").set_value("牛排")
    app.selectbox(key="price_choice").set_value("等級 2 以內")
    app.multiselect(key="occasion_choice").set_value(["一個人吃"])
    app.multiselect(key="pace_choice").set_value(["快速上菜"])
    app.checkbox(key="include_closed").check()
    app.text_input(key="query_choice").set_value("不存在的餐廳").run()
    assert not app.exception
    assert names(app) == [] and app.button(key="pick_meal").disabled
    next(button for button in app.button if button.label == "重設篩選").click().run()
    assert not app.exception
    assert app.selectbox(key="location_choice").value == "all"
    assert app.selectbox(key="category_choice").value == "所有種類"
    assert app.selectbox(key="price_choice").value == "不限等級"
    assert app.multiselect(key="occasion_choice").value == []
    assert app.multiselect(key="pace_choice").value == []
    assert app.checkbox(key="include_closed").value is False
    assert app.text_input(key="query_choice").value == ""
    assert len(names(app)) == 175
    assert not app.button(key="pick_meal").disabled


def test_custom_filename_is_escaped_before_display(app):
    result = parse_rows([EXCEL_HEADERS, ["測試安全店家", "Gongguan", "Bento", 1]])
    app.session_state["picker"].import_catalog(result, '<script>alert("x")</script>.xlsx')
    app.run()
    assert not app.exception
    source = next(text.value for text in app.get("html") if "source-filename" in text.value)
    assert "&lt;script&gt;" in source
    assert "<script>" not in source
    assert names(app) == ["測試安全店家"]
