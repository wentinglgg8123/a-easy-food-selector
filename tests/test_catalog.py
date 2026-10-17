"""Behavioral checks for import rules and recommendation boundaries."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
import random

import pytest

from food_picker.catalog import choose_restaurant, demo_restaurants, filter_restaurants, parse_rows
from food_picker.models import Filters, ValidationError


def test_chinese_and_english_headers_with_optional_columns():
    result = parse_rows([
        [],
        ["Ｒｅｓｔａｕｒａｎｔ＿Ｎａｍｅ", "區域（校內/校外）", "Type", "均消（元）", "distance-km", "住址", "notes", "ignored"],
        [" 午餐店 ", "On Campus", "中式", "ＮＴ＄１，０００元", None, " 新竹市 ", "營業時間依現場為準", "自訂欄位"],
        ["早餐店", "off-campus", "", "$ 60", "２ km", "光復路", "", None],
    ])
    first, second = result.restaurants
    assert (first.name, first.area, first.category, first.price, first.address) == ("午餐店", "campus", "中式", 1_000, "新竹市")
    assert (second.area, second.category, second.distance) == ("nearby", "未分類", 2)
    assert result.warnings == []
    assert first.to_dict()["note"] == "營業時間依現場為準"
    with pytest.raises(FrozenInstanceError):
        first.name = "不能修改"


@pytest.mark.parametrize("value, expected", [(0, 0), (".5", .5), ("TWD 1,250.50", 1_250.5), ("80 NTD", 80), (None, None)])
def test_supported_price_formats(value, expected):
    result = parse_rows([["name", "area", "price"], ["店家", "campus", value]])
    assert result.restaurants[0].price == expected


@pytest.mark.parametrize("value", ["80-100", "1,00", "100人", "1e3", "-1", -1, float("inf"), float("nan"), True, date(2026, 10, 17), "=SUM(A1)", "\u3000＝1+2"])
def test_invalid_numeric_rows_are_skipped_without_losing_valid_rows(value):
    result = parse_rows([["name", "area", "price"], ["無效店家", "campus", value], ["有效店家", "campus", 80]])
    assert [restaurant.name for restaurant in result.restaurants] == ["有效店家"]
    assert len(result.warnings) == 1
    assert "第 2 列" in result.warnings[0]


def test_two_kilometre_boundary_and_missing_distance_warning():
    result = parse_rows([
        ["名稱", "地區", "距離"],
        ["範圍邊界", "校外", "2 公里"],
        ["範圍之外", "校外", 2.001],
        ["未填距離", "校外", ""],
        ["校內店家", "校內", 2.5],
    ])
    assert [restaurant.name for restaurant in result.restaurants] == ["範圍邊界", "未填距離", "校內店家"]
    assert any("第 3 列" in warning and "超過 2 公里" in warning for warning in result.warnings)
    assert any("第 4 列" in warning and "未填距離" in warning for warning in result.warnings)


def test_deduplication_uses_normalised_name_address_and_area():
    result = parse_rows([
        ["name", "area", "address"],
        ["Ｃａｆé", "campus", "Ａ路"],
        [" café ", "校內", "a路"],
        ["Café", "campus", "B路"],
        ["Café", "nearby", "Ａ路"],
    ])
    assert len(result.restaurants) == 3
    assert "第 3 列" in result.warnings[0] and "重複" in result.warnings[0]
    repeated = parse_rows([["name", "area", "address"], ["café", "campus", "a路"]])
    assert repeated.restaurants[0].id == result.restaurants[0].id


@pytest.mark.parametrize("rows, match", [
    ([], "沒有資料"),
    ([[None], [" "]], "沒有資料"),
    ([["name"], ["店家"]], "缺少必要欄位"),
    ([["name", "area", "店名"], ["店家", "campus", "店家"]], "出現多次"),
    ([["name", "area"], ["", "campus"]], "沒有可使用"),
])
def test_fatal_catalog_errors(rows, match):
    with pytest.raises(ValidationError, match=match):
        parse_rows(rows)


def test_limit_counts_nonempty_data_rows_and_aggregates_large_warning_groups():
    with pytest.raises(ValidationError, match="5,000"):
        parse_rows([["name", "area"]] + [["店家", "campus"]] * 5_001)
    result = parse_rows([["name", "area"]] + [["", "校內"]] * 14 + [[]] * 20 + [["店家", "校內"]])
    assert len(result.restaurants) == 1
    assert len(result.warnings) == 1
    assert "第 2、3、4、5、6、7、8、9、10、11、12、13 等 14 列" in result.warnings[0]


@pytest.mark.parametrize("column, size", [("name", 201), ("category", 81), ("address", 501), ("note", 2_001)])
def test_long_text_has_actionable_warning(column, size):
    headers = ["name", "area", "category", "address", "note"]
    invalid = ["店家", "campus", "中式", "地址", "備註"]
    invalid[headers.index(column)] = "文" * size
    result = parse_rows([headers, invalid, ["有效店家", "campus"]])
    assert len(result.restaurants) == 1
    assert "超過" in result.warnings[0] and "請縮短" in result.warnings[0]


@pytest.mark.parametrize("cell", ["=HYPERLINK(\"https://example.com\")", False, datetime(2026, 10, 17)])
def test_unsafe_cells_in_unknown_columns_are_rejected(cell):
    result = parse_rows([["name", "area", "extra"], ["無效店家", "campus", cell], ["有效店家", "campus", "自訂欄位"]])
    assert [restaurant.name for restaurant in result.restaurants] == ["有效店家"]


def test_filters_combine_and_unknown_price_is_not_within_budget():
    restaurants = demo_restaurants()
    filtered = filter_restaurants(restaurants, Filters(area="nearby", category="中式", max_price=100, query="巷口"))
    assert [restaurant.id for restaurant in filtered] == ["demo-nearby-dumplings"]
    assert filter_restaurants([replace(restaurants[0], price=None)], Filters(max_price=200)) == []
    assert filter_restaurants(restaurants, Filters(query="清華大學")) == restaurants
    normalised = replace(restaurants[0], name="ＣＡＦÉ", category="ＪＡＰＡＮＥＳＥ")
    assert filter_restaurants([normalised], Filters(query="café", category="japanese")) == [normalised]


def test_filter_defends_two_kilometre_rule_for_directly_created_records():
    restaurant = demo_restaurants()[4]
    assert filter_restaurants([replace(restaurant, distance=2)], Filters())
    for distance in (-.1, 2.01, float("nan"), float("inf")):
        assert filter_restaurants([replace(restaurant, distance=distance)], Filters()) == []


def test_selection_handles_empty_singleton_and_never_repeats_with_alternatives():
    restaurants = demo_restaurants()
    assert choose_restaurant([]) is None
    assert choose_restaurant(restaurants[:1], restaurants[0].id) == restaurants[0]
    rng = random.Random(2026)
    chosen_ids = {choose_restaurant(restaurants, restaurants[0].id, rng).id for _ in range(100)}
    assert restaurants[0].id not in chosen_ids
    assert chosen_ids == {restaurant.id for restaurant in restaurants[1:]}
    assert choose_restaurant(restaurants, rng=random.Random(1)) == choose_restaurant(restaurants, rng=random.Random(1))


def test_demo_catalog_is_fresh_and_explicitly_fictional():
    restaurants = demo_restaurants()
    assert len(restaurants) == 8
    assert len({restaurant.id for restaurant in restaurants}) == 8
    assert all("示範" in restaurant.name and "非真實店家名單" in restaurant.note for restaurant in restaurants)
    restaurants.clear()
    assert len(demo_restaurants()) == 8
