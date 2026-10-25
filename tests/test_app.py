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
    assert state.filename is None and len(state.restaurants) == 10
    assert len(names(app)) == 10
    assert "包子商行" in names(app)
    assert "孫東寶牛排" not in names(app)
    assert not app.button(key="pick_meal").disabled
    assert app.pills(key="location_choices").value == []
    assert len(app.pills(key="location_choices").options) == 2
    assert len(app.pills(key="category_choices").options) == 18
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
    app.pills(key="location_choices").set_value(["小吃部"])
    app.pills(key="category_choices").set_value(["速食"])
    app.pills(key="price_choices").set_value([2])
    app.pills(key="occasion_choice").set_value(["一個人吃", "聚餐"])
    app.run()
    assert not app.exception
    assert names(app) == ["麥當勞"]
    app.button(key="pick_meal").click().run()
    selected = app.session_state["picker"].selected
    assert selected.name == "麥當勞"
    assert selected.price is None and selected.price_level == 2


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
    result = parse_rows([
        EXCEL_HEADERS,
        ["測試歇業店", "小吃部", "便當", 1, "O", "", "", "O", "", "", "關門了"],
        ["測試營業店", "清夜", "麵食", 2],
    ])
    app.session_state["picker"].import_catalog(result, "歇業測試名單.xlsx")
    app.run()
    app.text_input(key="query_choice").set_value("測試歇業店").run()
    assert not app.exception
    assert names(app) == []
    app.checkbox(key="include_closed").check().run()
    assert not app.exception
    assert names(app) == ["測試歇業店"]
    assert any("關門了" in str(value) for value in app.dataframe[0].value.iloc[0])
    assert app.button(key="pick_meal").disabled
    assert app.session_state["picker"].selected is None


def test_changing_location_hides_selection_and_preserves_history(app):
    app.pills(key="location_choices").set_value(["小吃部"]).run()
    app.button(key="pick_meal").click().run()
    chosen = app.session_state["picker"].selected
    assert chosen.location == "小吃部"
    app.pills(key="location_choices").set_value(["清夜"]).run()
    assert not app.exception
    assert not any('aria-label="餐廳推薦結果"' in element.value for element in app.get("html"))
    assert app.session_state["picker"].history == [chosen]
    assert names(app) == ["杜蘭小麥 - 義大利麵.披薩"]


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
    assert len(state.restaurants) == 10 and len(names(app)) == 10
    assert state.selected is None and state.history == []
    assert state.warnings == [] and len(app.warning) == 0
    assert "我的餐廳.xlsx" not in " ".join(text.value for text in app.get("html"))


def test_empty_search_disables_pick_and_reset_clears_every_filter(app):
    app.pills(key="location_choices").set_value(["小吃部"])
    app.pills(key="category_choices").set_value(["速食"])
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
    assert len(names(app)) == 10
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
    app.pills(key="location_choices").set_value(["小吃部", "清夜"]).run()
    assert not app.exception and len(names(app)) == 10
    app.pills(key="location_choices").set_value(["清夜"]).run()
    assert not app.exception and len(names(app)) == 1
    app.pills(key="location_choices").set_value([]).run()
    assert not app.exception and len(names(app)) == 10


def test_complete_table_provides_named_google_maps_links(app):
    first_row = app.dataframe[0].value.iloc[0]
    url = urlparse(first_row["Google 地圖"])
    assert url.scheme == "https" and url.hostname == "www.google.com"
    query = parse_qs(url.query)["query"][0]
    assert "包子商行" in query and "小吃部" in query
    config = json.loads(app.dataframe[0].proto.columns)
    assert config["Google 地圖"]["type_config"]["type"] == "link"


def test_each_filter_group_can_select_all_and_clear_without_affecting_other_groups(app):
    groups = {
        "location_choices": 2,
        "category_choices": 18,
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
        assert len(names(app)) == 10


def test_coin_prices_have_the_range_legend_and_readable_table_values(app):
    displayed = [" ".join(part for part in (option.content_icon, option.content) if part)
                 for option in app.pills(key="price_choices").proto.options]
    assert displayed == ["🪙" * level for level in range(1, 6)]
    legend = next(html.value for html in app.get("html") if "price-legend" in html.value)
    for price_range in ("0–100", "100–200", "200–300", "300–500", "500以上"):
        assert price_range in legend
    table = app.dataframe[0].value
    assert table.iloc[0]["價格"] == "🪙 · NT$0–100"
    assert "價格等級" not in table.columns
    half_price_names = {"7-ELEVEN", "漢城異國美食", "蘇記牛肉麵", "一番快餐", "好富熟成黑咖哩.台式蓋飯"}
    for level, count, excluded in ((1, 8, {"麥當勞", "杜蘭小麥 - 義大利麵.披薩"}),
                                   (2, 7, {"包子商行", "比司多早午餐", "珈名鮮茶"})):
        app.pills(key="price_choices").set_value([level]).run()
        assert not app.exception and len(names(app)) == count
        assert half_price_names <= set(names(app))
        assert excluded.isdisjoint(names(app))
    app.pills(key="price_choices").set_value([1, 2]).run()
    assert not app.exception and len(names(app)) == len(set(names(app))) == 10
    app.pills(key="price_choices").set_value([2])
    app.text_input(key="query_choice").set_value("7-ELEVEN").run()
    app.button(key="pick_meal").click().run()
    assert not app.exception
    assert app.session_state["picker"].selected.name == "7-ELEVEN"
    assert app.session_state["picker"].selected.price_level == 1.5
    assert any('aria-label="1.5 枚金幣"' in item.value for item in app.get("html"))


def test_catalog_pagination_exposes_six_comment_forms_per_page(app):
    assert app.session_state["catalog_page"] == 0
    assert app.button(key="catalog_previous").disabled
    first_cards = [html.value for html in app.get("html") if '<article class="food-card' in html.value]
    assert len(first_cards) == 6 and "包子商行" in first_cards[0]
    assert len([field for field in app.text_area if field.key.startswith("review_body_")]) == 6
    submit_buttons = [button for button in app.button if (button.key or "").startswith("review_submit_")]
    assert len(submit_buttons) == 6 and all(button.disabled for button in submit_buttons)

    app.button(key="catalog_next").click().run()
    assert not app.exception
    assert app.session_state["catalog_page"] == 1
    second_cards = [html.value for html in app.get("html") if '<article class="food-card' in html.value]
    assert len(second_cards) == 4 and "蘇記牛肉麵" in second_cards[0]
    assert "包子商行" not in " ".join(second_cards)
    assert len([field for field in app.text_area if field.key.startswith("review_body_")]) == 4
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
    app.pills(key="location_choices").set_value(["清夜"]).run()
    assert not app.exception and len(names(app)) == 1
    assert not app.button(key="pick_meal").disabled


def test_top_name_search_ignores_location_filters_and_finds_closed_restaurants(app):
    state = app.session_state["picker"]
    restaurant = next(r for r in state.restaurants if r.name == "麥當勞")
    app.pills(key="location_choices").set_value(["清夜"]).run()
    app.text_input(key="query_choice").set_value("麥當勞").run()
    assert not app.exception and names(app) == []
    assert app.text_area(key=f"review_body_search_{restaurant.id}").value == ""
    assert app.text_input(key=f"review_author_search_{restaurant.id}").label == "您的暱稱"
    assert app.button(key=f"review_submit_search_{restaurant.id}").disabled

    result = parse_rows([
        EXCEL_HEADERS,
        ["測試歇業店", "小吃部", "便當", 1, "O", "", "", "O", "", "", "關門了"],
        ["測試營業店", "清夜", "麵食", 2],
    ])
    state.import_catalog(result, "歇業測試名單.xlsx")
    app.text_input(key="query_choice").set_value("測試歇業店").run()
    closed = next(r for r in state.restaurants if r.is_closed)
    assert not app.exception and names(app) == []
    assert app.text_area(key=f"review_body_search_{closed.id}").value == ""
    assert app.checkbox(key="include_closed").value is False
    assert app.button(key="pick_meal").disabled
    app.button(key="clear_all_filters").click().run()
    assert not app.exception and names(app) == ["測試營業店"]
    assert not any(field.key.startswith("review_body_search_") for field in app.text_area)


def test_search_recommendation_and_catalog_have_separate_half_star_rating_controls(app):
    app.text_input(key="query_choice").set_value("麥當勞").run()
    app.button(key="pick_meal").click().run()
    assert not app.exception
    restaurant = app.session_state["picker"].selected
    assert restaurant.name == "麥當勞"
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
    result = parse_rows([EXCEL_HEADERS, *[
        [f"搜尋測試{index}店", "小吃部", "便當", 1] for index in range(6)
    ]])
    app.session_state["picker"].import_catalog(result, "搜尋分頁名單.xlsx")
    app.text_input(key="query_choice").set_value("搜尋測試").run()
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
    app.text_input(key="query_choice").set_value("搜尋測試0店").run()
    assert not app.exception
    assert len([field for field in app.text_area if field.key.startswith("review_body_search_")]) == 1


def test_clear_search_only_clears_query_and_search_pagination(app):
    result = parse_rows([EXCEL_HEADERS, *[
        [f"搜尋測試{index}店", "小吃部", "便當", 1] for index in range(6)
    ]])
    app.session_state["picker"].import_catalog(result, "搜尋分頁名單.xlsx")
    app.run()
    app.pills(key="location_choices").set_value(["小吃部"])
    app.pills(key="category_choices").set_value(["便當"])
    app.text_input(key="query_choice").set_value("搜尋測試").run()
    app.button(key="pick_meal").click().run()
    chosen = app.session_state["picker"].selected
    history = list(app.session_state["picker"].history)
    app.button(key="search_next").click().run()
    app.text_input(key="query_choice").set_value("尚未送出的文字")
    app.button(key="clear_search_query").click().run()
    assert not app.exception
    assert app.text_input(key="query_choice").value == ""
    assert app.pills(key="location_choices").value == ["小吃部"]
    assert app.pills(key="category_choices").value == ["便當"]
    assert app.session_state["search_page"] == 0
    assert "search_signature" not in app.session_state
    assert app.session_state["picker"].selected == chosen
    assert app.session_state["picker"].history == history
    assert len(names(app)) == 6
    assert not any(field.key.startswith("review_body_search_") for field in app.text_area)


def test_homophone_typo_directly_shows_a_real_store_and_review_form_in_search_results(app):
    restaurant = next(r for r in app.session_state["picker"].restaurants if r.name == "麥當勞")
    app.pills(key="location_choices").set_value(["清夜"]).run()
    app.text_input(key="query_choice").set_value("麥當牢").run()
    assert not app.exception
    assert app.text_input(key="query_choice").value == "麥當牢"
    assert app.pills(key="location_choices").value == ["清夜"]
    assert names(app) == []
    assert app.text_area(key=f"review_body_search_{restaurant.id}").value == ""
    assert app.text_input(key=f"review_author_search_{restaurant.id}").label == "您的暱稱"
    assert app.slider(key=f"review_rating_search_{restaurant.id}").proto.step == 0.5
    assert [caption.value for caption in app.caption if "讀音或字詞相近" in caption.value] == [
        "找到 1 間讀音或字詞相近的店家"
    ]
    assert sum(heading.value == "搜尋結果" for heading in app.subheader) == 1
    assert not any("你是不是想找" in heading.value for heading in app.subheader)
    assert not any("找到 0 間" in caption.value for caption in app.caption)
    assert not any("找不到完全符合" in info.value for info in app.info)
    assert not any((button.key or "").startswith("search_suggestion_") for button in app.button)


def test_unrelated_query_shows_empty_search_message_and_clearing_hides_results(app):
    app.text_input(key="query_choice").set_value("ZXQ987654321外太空不存在的店").run()
    assert not app.exception
    assert not any(field.key.startswith("review_body_search_") for field in app.text_area)
    assert any("找不到相近的店家" in info.value for info in app.info)
    assert sum(heading.value == "搜尋結果" for heading in app.subheader) == 1
    app.button(key="clear_search_query").click().run()
    assert not app.exception and app.text_input(key="query_choice").value == ""
    assert not any(field.key.startswith("review_body_search_") for field in app.text_area)
    assert not any("找不到相近的店家" in info.value for info in app.info)
    assert not any(heading.value == "搜尋結果" for heading in app.subheader)
    assert len(names(app)) == 10


def test_top_search_is_configured_to_update_after_a_short_typing_pause(app):
    query = app.text_input(key="query_choice")
    assert query.proto.HasField("live_debounce_ms")
    assert query.proto.live_debounce_ms == 350
    assert "即時搜尋" in query.proto.placeholder
