"""Check useful homophones and typo suggestions without unrelated filler."""

import pytest

from food_picker.defaults import load_default_catalog
from food_picker.models import Restaurant
from food_picker.search import find_restaurants, suggest_restaurants


def restaurant(name: str, identity: str = "restaurant-test", **fields) -> Restaurant:
    return Restaurant(identity, name, "other", "拉麵", None, None, "不在名稱的地址", "孫東保備註", **fields)


def test_literal_search_uses_only_names_and_normalises_width_case_spaces_and_punctuation():
    closed = restaurant("Café・咖啡（公館店）", is_closed=True)
    other = restaurant("牛排館", "restaurant-other")
    assert find_restaurants([closed, other], "ＣＡＦÉ 咖啡") == [closed]
    assert find_restaurants([closed, other], "公館 店") == [closed]
    assert find_restaurants([closed, other], "孫東保") == []
    assert find_restaurants([closed, other], "地址") == []


@pytest.mark.parametrize("query", ["", " \t\n ", "！……！？", "---"])
def test_empty_or_punctuation_only_search_does_not_match_every_store(query):
    stores = [restaurant("孫東寶牛排")]
    assert find_restaurants(stores, query) == []
    assert suggest_restaurants(stores, query) == []


@pytest.mark.parametrize("query", ["孫東保牛排", "孫冬保", "孫東寶牛扒", "孫東保"])
def test_historical_brand_regression_suggests_real_name_for_homophones_and_typos(query):
    stores = [restaurant("孫東寶牛排")]
    assert find_restaurants(stores, query) == []
    suggestions = suggest_restaurants(stores, query)
    assert suggestions and suggestions[0].name == "孫東寶牛排"
    assert all(item in stores for item in suggestions)


def test_brand_name_homophones_keep_single_character_readings_suppressed_by_phrases():
    stores = [restaurant("頂呱呱")]
    assert find_restaurants(stores, "頂瓜瓜") == []
    suggestions = suggest_restaurants(stores, "頂瓜瓜")
    assert suggestions and suggestions[0].name == "頂呱呱"


def test_current_bundled_catalog_suggests_the_uploaded_store_for_a_homophone():
    stores = load_default_catalog().restaurants
    assert find_restaurants(stores, "麥當牢") == []
    suggestions = suggest_restaurants(stores, "麥當牢")
    assert suggestions and suggestions[0].name == "麥當勞"
    assert all(item in stores for item in suggestions)


def test_partial_homophones_match_a_contiguous_window_in_longer_names():
    store = restaurant("正宗孫東寶牛排公館分店")
    assert suggest_restaurants([store], "孫冬保") == [store]


def test_traditional_simplified_and_polyphonic_names_use_local_dictionary_readings():
    chongqing = restaurant("重慶麵館", "restaurant-chongqing")
    bank = restaurant("銀行咖啡", "restaurant-bank")
    assert suggest_restaurants([chongqing, bank], "崇庆") == [chongqing]
    assert suggest_restaurants([chongqing, bank], "銀杭") == [bank]


def test_near_pronunciation_is_supported_without_requiring_identical_characters():
    store = restaurant("孫東寶牛排")
    assert suggest_restaurants([store], "孫通保") == [store]


def test_syllable_boundaries_do_not_conflate_xi_an_with_xian():
    store = restaurant("西安館")
    assert suggest_restaurants([store], "先館") == []
    assert suggest_restaurants([restaurant("先麵館")], "西安麵館") == []


def test_latin_typos_and_mixed_names_preserve_non_chinese_characters():
    cafe = restaurant("山丘 Cafe", "restaurant-cafe")
    coffee = restaurant("咖啡 Cafe", "restaurant-coffee")
    assert suggest_restaurants([cafe], "cfe") == [cafe]
    assert suggest_restaurants([coffee], "咖啡 caff") == [coffee]
    assert suggest_restaurants([cafe], "zzzz") == []


def test_exact_then_homophone_then_near_sound_then_character_typo_order():
    exact = restaurant("孫東保", "restaurant-exact")
    homophone = restaurant("孫東寶牛排", "restaurant-homophone")
    near = restaurant("孫通寶", "restaurant-near")
    typo = restaurant("孫東館", "restaurant-typo")
    assert suggest_restaurants([typo, near, homophone, exact], "孫東保") == [exact, homophone, near, typo]


def test_equal_scores_keep_source_order_and_results_are_capped_without_duplicates():
    stores = [restaurant(f"孫東寶分店{index}", f"restaurant-{index}") for index in range(8)]
    assert suggest_restaurants([stores[0], stores[0], *stores[1:]], "孫東保", limit=20) == stores[:5]
    assert suggest_restaurants(stores, "孫東保", limit=2) == stores[:2]
    assert suggest_restaurants(stores, "孫東保", limit=0) == []
    assert suggest_restaurants(stores, "孫東保", limit=-1) == []


@pytest.mark.parametrize("query", ["孫", "不存在的餐廳", "火星披薩abc", "zzzz", "<script>alert(1)</script>"])
def test_short_or_unrelated_queries_do_not_fill_suggestions_with_random_stores(query):
    stores = load_default_catalog().restaurants
    assert suggest_restaurants(stores, query) == []


def test_closed_stores_remain_findable_and_suggestible_without_becoming_recommendations():
    store = restaurant("孫東寶牛排", is_closed=True)
    assert find_restaurants([store], "孫東寶") == [store]
    assert suggest_restaurants([store], "孫東保") == [store]


def test_queries_longer_than_the_bounded_suggestion_window_return_no_results():
    store = restaurant("測" * 70)
    assert find_restaurants([store], "測" * 70) == [store]
    assert suggest_restaurants([store], "測" * 70) == []
