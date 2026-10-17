"""Exercise the Python website's rendered controls and session callbacks."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from food_picker.catalog import parse_rows

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def app():
    result = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    assert not result.exception
    return result


def test_initial_page_displays_eight_demo_restaurants_without_a_selection(app):
    state = app.session_state["picker"]
    assert state.is_demo and state.selected is None
    assert len(app.dataframe[0].value) == 8
    assert not app.button(key="pick_meal").disabled
    assert app.radio(key="area_choice").value == "都可以"
    assert any("8 筆虛構示範資料" in caption.value for caption in app.caption)


def test_pick_button_renders_a_recommendation_and_avoids_the_previous_one(app):
    app.button(key="pick_meal").click().run()
    assert not app.exception
    first_id = app.session_state["picker"].selected.id
    assert any('aria-label="餐廳推薦結果"' in element.value for element in app.get("html"))

    app.button(key="pick_meal").click().run()
    assert not app.exception
    state = app.session_state["picker"]
    assert state.selected.id != first_id
    assert state.history[0] == state.selected
    assert len(state.history) == 2


def test_filter_controls_combine_show_empty_results_and_reset(app):
    app.radio(key="area_choice").set_value("校園周邊")
    app.selectbox(key="category_choice").set_value("早餐")
    app.selectbox(key="budget_choice").set_value("NT$ 100 以內")
    app.text_input(key="query_choice").set_value("晨光")
    app.run()
    assert not app.exception
    assert app.dataframe[0].value["餐廳名稱"].tolist() == ["示範・晨光早餐"]
    app.button(key="pick_meal").click().run()
    assert app.session_state["picker"].selected.name == "示範・晨光早餐"

    app.text_input(key="query_choice").set_value("不存在的餐廳").run()
    assert not app.exception
    assert app.button(key="pick_meal").disabled
    assert len(app.dataframe) == 0
    assert any("目前沒有符合條件的餐廳" in element.value for element in app.get("html"))

    next(button for button in app.button if button.label == "重設篩選").click().run()
    assert not app.exception
    assert app.radio(key="area_choice").value == "都可以"
    assert app.selectbox(key="category_choice").value == "不挑食"
    assert app.selectbox(key="budget_choice").value == "不限預算"
    assert app.text_input(key="query_choice").value == ""
    assert len(app.dataframe[0].value) == 8
    assert not app.button(key="pick_meal").disabled


def test_adjusting_area_hides_the_current_result_but_preserves_history(app):
    app.radio(key="area_choice").set_value("清大校內").run()
    app.button(key="pick_meal").click().run()
    chosen = app.session_state["picker"].selected
    assert chosen.area == "campus"

    app.radio(key="area_choice").set_value("校園周邊").run()

    assert not app.exception
    assert not any('aria-label="餐廳推薦結果"' in element.value for element in app.get("html"))
    assert app.session_state["picker"].history == [chosen]
    assert set(app.dataframe[0].value["區域"]) == {"校園周邊"}


def test_imported_catalog_source_and_warnings_render_then_clear(app):
    result = parse_rows([["name", "area", "category"], ["測試餐廳", "nearby", "素食"]])
    app.session_state["picker"].import_catalog(result, "我的餐廳.xlsx")
    app.run()

    assert not app.exception
    assert any("我的餐廳.xlsx" in text.value for text in app.markdown)
    assert app.dataframe[0].value["餐廳名稱"].tolist() == ["測試餐廳"]
    assert any("未填距離" in warning.value for warning in app.warning)
    assert "素食" in app.selectbox(key="category_choice").options
    app.button(key="pick_meal").click().run()
    assert app.session_state["picker"].selected.name == "測試餐廳"

    next(button for button in app.button if button.label == "清除並回到示範").click().run()

    assert not app.exception
    state = app.session_state["picker"]
    assert state.is_demo and state.filename is None
    assert state.selected is None and state.history == []
    assert state.warnings == [] and len(app.warning) == 0
    assert len(app.dataframe[0].value) == 8
    assert any("已清除匯入資料" in message.value for message in app.success)
