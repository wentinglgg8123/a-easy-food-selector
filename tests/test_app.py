"""Exercise the public default catalog, rendered filters, and session callbacks."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
    assert app.pills(key="location_choices").value == []
    assert len(app.pills(key="location_choices").options) == 8
    assert len(app.pills(key="category_choices").options) == 25
    assert len(app.selectbox) == 0 and len(app.multiselect) == 0
    assert len(app.pills) == 5
    assert not any("FOODFLIX" in element.value for element in app.get("html"))
    assert app.text_input[0].key == "query_choice"
    assert app.text_input[0].label == "搜尋店家"


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
    app.pills(key="location_choices").set_value(["Gongguan"])
    app.pills(key="category_choices").set_value(["牛排"])
    app.pills(key="price_choices").set_value([1])
    app.pills(key="occasion_choice").set_value(["約會", "聚餐"])
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
    app.pills(key="location_choices").set_value(["Gongguan"])
    app.pills(key="category_choices").set_value(["便當"])
    app.pills(key="price_choices").set_value([2])
    app.pills(key="occasion_choice").set_value(["一個人吃", "約會", "聚餐"])
    app.pills(key="pace_choice").set_value(["快速上菜", "慢慢享用"])
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
    app.pills(key="location_choices").set_value(["Gongguan"]).run()
    app.button(key="pick_meal").click().run()
    chosen = app.session_state["picker"].selected
    assert chosen.location == "Gongguan"
    app.pills(key="location_choices").set_value(["Shida"]).run()
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
    assert "素食" in app.pills(key="category_choices").options
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
    app.pills(key="location_choices").set_value(["Gongguan"])
    app.pills(key="category_choices").set_value(["牛排"])
    app.pills(key="price_choices").set_value([2])
    app.pills(key="occasion_choice").set_value(["一個人吃"])
    app.pills(key="pace_choice").set_value(["快速上菜"])
    app.checkbox(key="include_closed").check()
    app.text_input(key="query_choice").set_value("不存在的餐廳").run()
    assert not app.exception
    assert names(app) == [] and app.button(key="pick_meal").disabled
    app.button(key="clear_all_filters").click().run()
    assert not app.exception
    assert app.pills(key="location_choices").value == []
    assert app.pills(key="category_choices").value == []
    assert app.pills(key="price_choices").value == []
    assert app.pills(key="occasion_choice").value == []
    assert app.pills(key="pace_choice").value == []
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


def test_multiple_locations_cuisines_and_exact_price_levels_union_within_groups(app):
    result = parse_rows([
        EXCEL_HEADERS,
        ["甲店", "Gongguan", "Bento", 1],
        ["乙店", "Shida", "Steak", 3],
        ["丙店", "Gongguan", "Steak", 2],
        ["丁店", "Liuzhangli", "Bento", 3],
        ["戊店", "Shida", "Cafe", 1],
        ["己店", "Gongguan", "Steak", 3],
    ])
    app.session_state["picker"].import_catalog(result, "多選名單.xlsx")
    app.run()
    app.pills(key="location_choices").set_value(["Gongguan", "Shida"])
    app.pills(key="category_choices").set_value(["便當", "牛排"])
    app.pills(key="price_choices").set_value([1, 3])
    app.run()
    assert not app.exception
    assert names(app) == ["甲店", "乙店", "己店"]
    assert "丙店" not in names(app)  # Level 2 is outside the selected exact levels.


def test_removing_location_pills_broadens_back_to_the_complete_catalog(app):
    app.pills(key="location_choices").set_value(["Gongguan", "Shida"]).run()
    assert not app.exception and len(names(app)) == 78
    app.pills(key="location_choices").set_value(["Shida"]).run()
    assert not app.exception and len(names(app)) == 3
    app.pills(key="location_choices").set_value([]).run()
    assert not app.exception and len(names(app)) == 175


def test_complete_table_provides_named_google_maps_links(app):
    first_row = app.dataframe[0].value.iloc[0]
    url = urlparse(first_row["Google 地圖"])
    assert url.scheme == "https" and url.hostname == "www.google.com"
    query = parse_qs(url.query)["query"][0]
    assert "孫東寶牛排" in query and "公館" in query
    config = json.loads(app.dataframe[0].proto.columns)
    assert config["Google 地圖"]["type_config"]["type"] == "link"


def test_each_filter_group_can_select_all_and_clear_without_affecting_other_groups(app):
    groups = {
        "location_choices": 8,
        "category_choices": 25,
        "price_choices": 5,
        "occasion_choice": 3,
        "pace_choice": 2,
    }
    for key, option_count in groups.items():
        app.button(key=f"select_all_{key}").click().run()
        assert not app.exception
        assert len(app.pills(key=key).value) == option_count
        for other_key in groups.keys() - {key}:
            assert app.pills(key=other_key).value == []
        app.button(key=f"clear_{key}").click().run()
        assert not app.exception
        assert app.pills(key=key).value == []
        assert len(names(app)) == 175


def test_coin_prices_have_the_range_legend_and_readable_table_values(app):
    displayed = [option.content or option.content_icon for option in app.pills(key="price_choices").proto.options]
    assert displayed == ["🪙" * level for level in range(1, 6)]
    legend = next(html.value for html in app.get("html") if "price-legend" in html.value)
    for price_range in ("0–100", "100–200", "200–300", "300–500", "500以上"):
        assert price_range in legend
    table = app.dataframe[0].value
    assert table.iloc[0]["價格"] == "🪙 · NT$0–100"
    assert "價格等級" not in table.columns


def test_catalog_pagination_exposes_six_comment_forms_per_page(app):
    assert app.session_state["catalog_page"] == 0
    assert app.button(key="catalog_previous").disabled
    first_cards = [html.value for html in app.get("html") if '<article class="food-card' in html.value]
    assert len(first_cards) == 6 and "孫東寶牛排" in first_cards[0]
    assert len([field for field in app.text_area if field.key.startswith("review_body_")]) == 6
    submit_buttons = [button for button in app.button if (button.key or "").startswith("review_submit_")]
    assert len(submit_buttons) == 6 and all(button.disabled for button in submit_buttons)

    app.button(key="catalog_next").click().run()
    assert not app.exception
    assert app.session_state["catalog_page"] == 1
    second_cards = [html.value for html in app.get("html") if '<article class="food-card' in html.value]
    assert len(second_cards) == 6 and "泰好吃泰國船麵" in second_cards[0]
    assert "孫東寶牛排" not in " ".join(second_cards)
    assert len([field for field in app.text_area if field.key.startswith("review_body_")]) == 6
    assert not app.button(key="catalog_previous").disabled
    app.button(key="catalog_previous").click().run()
    assert not app.exception and app.session_state["catalog_page"] == 0


def test_invalid_review_configuration_keeps_catalog_and_filters_usable(app):
    app.secrets["reviews"] = "invalid"
    app.run()
    assert not app.exception
    assert any("評論暫時無法載入" in warning.value for warning in app.warning)
    submit_buttons = [button for button in app.button if (button.key or "").startswith("review_submit_")]
    assert len(submit_buttons) == 6 and all(button.disabled for button in submit_buttons)
    app.pills(key="location_choices").set_value(["Shida"]).run()
    assert not app.exception and len(names(app)) == 3
    assert not app.button(key="pick_meal").disabled


def test_top_name_search_ignores_location_filters_and_finds_closed_restaurants(app):
    state = app.session_state["picker"]
    steak = next(restaurant for restaurant in state.restaurants if restaurant.name == "孫東寶牛排")
    closed = next(restaurant for restaurant in state.restaurants if restaurant.name == "郭董麻辣牛肉麵")
    app.pills(key="location_choices").set_value(["Shida"]).run()
    app.text_input(key="query_choice").set_value("孫東寶牛排").run()
    assert not app.exception and names(app) == []
    assert app.text_area(key=f"review_body_search_{steak.id}").value == ""
    assert app.text_input(key=f"review_author_search_{steak.id}").label == "您的暱稱"
    assert app.button(key=f"review_submit_search_{steak.id}").disabled

    app.text_input(key="query_choice").set_value("郭董麻辣牛肉麵").run()
    assert not app.exception and names(app) == []
    assert app.text_area(key=f"review_body_search_{closed.id}").value == ""
    assert app.checkbox(key="include_closed").value is False
    assert app.button(key="pick_meal").disabled
    app.button(key="clear_all_filters").click().run()
    assert not app.exception and len(names(app)) == 175
    assert not any(field.key.startswith("review_body_search_") for field in app.text_area)


def test_search_recommendation_and_catalog_have_separate_half_star_rating_controls(app):
    app.text_input(key="query_choice").set_value("孫東寶牛排").run()
    app.button(key="pick_meal").click().run()
    assert not app.exception
    restaurant = app.session_state["picker"].selected
    assert restaurant.name == "孫東寶牛排"
    bodies = [field for field in app.text_area if restaurant.id in field.key]
    assert len(bodies) == 3 and len({field.key for field in bodies}) == 3
    recommendation_key = f"review_rating_recommendation_{restaurant.id}"
    search_key = f"review_rating_search_{restaurant.id}"
    ratings = [slider for slider in app.slider if restaurant.id in slider.key]
    assert len(ratings) == 3 and len({slider.key for slider in ratings}) == 3
    for slider in ratings:
        assert slider.value == 3.0
        assert slider.proto.min == 1.0 and slider.proto.max == 5.0
        assert slider.proto.step == 0.5
    assert app.slider(key=recommendation_key).value == app.slider(key=search_key).value
    assert app.text_area(key=f"review_body_search_{restaurant.id}").value == ""
    assert app.button(key=f"review_submit_recommendation_{restaurant.id}").disabled


def test_top_search_paginates_results_and_resets_when_query_changes(app):
    app.text_input(key="query_choice").set_value("牛排").run()
    assert not app.exception
    search_bodies = [field.key for field in app.text_area if field.key.startswith("review_body_search_")]
    assert len(search_bodies) == 3
    assert app.button(key="search_previous").disabled
    assert not app.button(key="search_next").disabled
    app.button(key="search_next").click().run()
    assert not app.exception
    next_bodies = [field.key for field in app.text_area if field.key.startswith("review_body_search_")]
    assert len(next_bodies) == 3 and set(next_bodies).isdisjoint(search_bodies)
    assert not app.button(key="search_previous").disabled
    app.text_input(key="query_choice").set_value("孫東寶牛排").run()
    assert not app.exception
    assert len([field for field in app.text_area if field.key.startswith("review_body_search_")]) == 1


def test_clear_search_only_clears_query_and_search_pagination(app):
    app.pills(key="location_choices").set_value(["Gongguan"])
    app.pills(key="category_choices").set_value(["牛排"])
    app.text_input(key="query_choice").set_value("牛排").run()
    app.button(key="pick_meal").click().run()
    chosen = app.session_state["picker"].selected
    history = list(app.session_state["picker"].history)
    app.button(key="search_next").click().run()
    app.text_input(key="query_choice").set_value("尚未送出的文字")
    app.button(key="clear_search_query").click().run()
    assert not app.exception
    assert app.text_input(key="query_choice").value == ""
    assert app.pills(key="location_choices").value == ["Gongguan"]
    assert app.pills(key="category_choices").value == ["牛排"]
    assert app.session_state["search_page"] == 0
    assert "search_signature" not in app.session_state
    assert app.session_state["picker"].selected == chosen
    assert app.session_state["picker"].history == history
    assert len(names(app)) == 4
    assert not any(field.key.startswith("review_body_search_") for field in app.text_area)


def test_homophone_typo_suggests_a_real_store_without_changing_the_query_until_clicked(app):
    restaurant = next(r for r in app.session_state["picker"].restaurants if r.name == "孫東寶牛排")
    app.pills(key="location_choices").set_value(["Shida"]).run()
    app.text_input(key="query_choice").set_value("孫東保牛排").run()
    assert not app.exception
    assert app.text_input(key="query_choice").value == "孫東保牛排"
    suggestion = app.button(key=f"search_suggestion_{restaurant.id}")
    assert suggestion.label == "孫東寶牛排"
    assert not any(field.key.startswith("review_body_search_") for field in app.text_area)
    suggestion.click().run()
    assert not app.exception
    assert app.text_input(key="query_choice").value == "孫東寶牛排"
    assert app.pills(key="location_choices").value == ["Shida"]
    assert names(app) == []
    assert app.text_area(key=f"review_body_search_{restaurant.id}").value == ""
    assert app.slider(key=f"review_rating_search_{restaurant.id}").proto.step == 0.5
    assert not any((button.key or "").startswith("search_suggestion_") for button in app.button)


def test_unrelated_and_empty_queries_do_not_show_store_suggestions(app):
    app.text_input(key="query_choice").set_value("ZXQ987654321外太空不存在的店").run()
    assert not app.exception
    assert not any((button.key or "").startswith("search_suggestion_") for button in app.button)
    app.button(key="clear_search_query").click().run()
    assert not app.exception and app.text_input(key="query_choice").value == ""
    assert not any((button.key or "").startswith("search_suggestion_") for button in app.button)
    assert len(names(app)) == 175
