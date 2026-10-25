"""Verify spreadsheet data is represented accurately and safely in the interface."""

from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest

from food_picker.defaults import load_default_catalog
from food_picker.presentation import (
    PRICE_RANGES, area_label, coin_label, feature_labels, map_url, price_label,
    price_html, price_legend_html, restaurant_card, table_rows,
)


def test_supplied_prices_display_coins_and_maps_search_exact_restaurant_name():
    restaurant = load_default_catalog().restaurants[0]
    assert price_label(restaurant) == "🪙 · NT$0–100"
    assert restaurant.price_level == 1
    assert restaurant.price is None
    assert area_label(restaurant) == "小吃部"
    query = parse_qs(urlsplit(map_url(restaurant)).query)
    assert query == {"api": ["1"], "query": [f"{restaurant.name} 國立清華大學 小吃部 新竹市 台灣"]}
    assert feature_labels(restaurant) == ["一個人吃", "快速上菜"]


@pytest.mark.parametrize("level, expected", [
    (1, "🪙 · NT$0–100"),
    (2, "🪙🪙 · NT$100–200"),
    (3, "🪙🪙🪙 · NT$200–300"),
    (4, "🪙🪙🪙🪙 · NT$300–500"),
    (5, "🪙🪙🪙🪙🪙 · NT$500以上"),
])
def test_each_price_level_has_the_requested_coin_count_and_range(level, expected):
    restaurant = replace(load_default_catalog().restaurants[0], price_level=level)
    assert price_label(restaurant) == expected
    assert coin_label(level) == "🪙" * level
    assert restaurant.price_level == level and restaurant.price is None


@pytest.mark.parametrize("level", [None, 0, -1, 6, True])
def test_unknown_coin_levels_do_not_fabricate_a_budget(level):
    assert coin_label(level) == "價格未提供"


def test_coin_legend_explains_all_requested_ranges():
    assert PRICE_RANGES == {
        1: "NT$0–100", 2: "NT$100–200", 3: "NT$200–300",
        4: "NT$300–500", 5: "NT$500以上",
    }
    html = price_legend_html()
    assert 'aria-label="金幣價格範圍說明"' in html
    assert html.count('role="listitem"') == 5
    for level, price_range in PRICE_RANGES.items():
        assert f'aria-label="{level} 枚金幣"' in html
        assert price_range in html


def test_legacy_prices_remain_amounts_instead_of_becoming_coin_levels():
    restaurant = replace(load_default_catalog().restaurants[0], price_level=None, price=150)
    assert price_label(restaurant) == "NT$ 150"
    assert table_rows([restaurant])[0]["價格"] == "NT$ 150"
    assert restaurant.price == 150 and restaurant.price_level is None


def test_maps_use_legacy_address_instead_of_coordinates_or_assumed_location():
    restaurant = replace(
        load_default_catalog().restaurants[0],
        name="測試店名（分店）", address=" 新竹市光復路二段 101 號 ", latitude=24.8,
    )
    assert restaurant.latitude is not None
    query = parse_qs(urlsplit(map_url(restaurant)).query)
    assert query == {"api": ["1"], "query": ["測試店名（分店） 新竹市光復路二段 101 號"]}


def test_map_queries_encode_name_and_address_as_one_search_parameter():
    restaurant = replace(
        load_default_catalog().restaurants[0],
        name='A & B + C / "店"? #1', address="測試路 1 號 & query=別間店",
    )
    url = map_url(restaurant)
    query = parse_qs(urlsplit(url).query)
    assert urlsplit(url).scheme == "https"
    assert urlsplit(url).netloc == "www.google.com"
    assert query == {"api": ["1"], "query": [f"{restaurant.name} {restaurant.address}"]}
    assert not urlsplit(url).fragment


def test_maps_preserve_unknown_location_without_fabricating_an_address_or_place_id():
    restaurant = replace(load_default_catalog().restaurants[0], location="OtherTown", address="")
    query = parse_qs(urlsplit(map_url(restaurant)).query)
    assert query == {"api": ["1"], "query": [f"{restaurant.name} OtherTown 台灣"]}
    school = replace(restaurant, location="School")
    assert "清大" not in parse_qs(urlsplit(map_url(school)).query)["query"][0]


def test_restaurant_cards_escape_untrusted_spreadsheet_text():
    restaurant = replace(
        load_default_catalog().restaurants[0],
        name='<img src=x onerror="alert(1)">',
        category='<script>alert("category")</script>',
        note='<script>alert("note")</script>',
        address='<script>alert("address")</script>',
    )
    html = restaurant_card(restaurant)
    assert '<img src=x' not in html and '<script>' not in html
    assert '&lt;img' in html and '&lt;script&gt;' in html
    assert 'rel="noopener noreferrer"' in html
    assert 'https://www.google.com/maps/search/' in html
    assert 'class="card-location"' in html
    assert '地址：&lt;script&gt;' in html
    assert 'Google 地圖搜尋 ↗' in html
    assert html.count('<a ') == 1 and html.count('</a>') == 1


def test_card_shows_supplied_location_as_part_of_its_named_map_search_link():
    restaurant = load_default_catalog().restaurants[0]
    html = restaurant_card(restaurant)
    assert '<p class="card-location">地點：小吃部 ' in html
    assert 'aria-label="在 Google 地圖搜尋 ' in html
    assert html.index('<a ') < html.index('class="card-location"') < html.index('</a>')


def test_missing_levels_and_unverified_school_are_not_fabricated():
    restaurant = replace(load_default_catalog().restaurants[0], price_level=None)
    assert price_label(restaurant) == "價格未提供"
    school = replace(restaurant, location="School")
    assert "清大" not in area_label(school)
    assert "原名單" in area_label(school)


def test_detail_table_preserves_comments_flags_and_closed_record():
    closed = replace(load_default_catalog().restaurants[0], name="測試已歇業店", note="關門了", is_closed=True)
    row = table_rows([closed])[0]
    assert row["餐廳名稱"] == "測試已歇業店"
    assert row["備註"] == "關門了" and row["原表註記歇業"] is True
    assert (row["緯度"], row["經度"]) == (closed.latitude, closed.longitude)
    assert row["Google 地圖"] == map_url(closed)
    assert row["價格"] == price_label(closed)
    assert "價格等級" not in row
    assert all(key in row for key in ["一個人吃", "約會", "聚餐", "快速上菜", "慢慢享用"])


def test_rich_catalog_optional_legacy_details_remain_visible():
    restaurant = replace(load_default_catalog().restaurants[0], price=150, distance=3, address="測試地址")
    row = table_rows([restaurant])[0]
    assert row["均消（元）"] == 150 and row["距離（公里）"] == 3
    assert row["地址"] == "測試地址"
    assert parse_qs(urlsplit(row["Google 地圖"]).query)["query"] == [f"{restaurant.name} 測試地址"]


def test_source_half_coin_price_is_drawn_without_an_invented_currency_range():
    restaurant = next(r for r in load_default_catalog().restaurants if r.name == "7-ELEVEN")
    assert restaurant.price_level == 1.5
    assert coin_label(1.5) == price_label(restaurant) == "🪙 × 1.5"
    markup = price_html(restaurant)
    assert 'aria-label="1.5 枚金幣"' in markup
    assert markup.count('🪙') == 2 and 'class="price-half-coin"' in markup
    assert "NT$" not in markup and "未定義" not in markup
    assert markup in restaurant_card(restaurant)
    assert table_rows([restaurant])[0]["價格"] == "🪙 × 1.5"


def test_source_hours_and_special_hours_are_visible_and_escaped():
    restaurant = load_default_catalog().restaurants[0]
    card = restaurant_card(restaurant)
    assert "營業時間：7:30~19:30" in card
    assert "特殊營業時間：假日8:30~14:30" in card
    row = table_rows([restaurant])[0]
    assert row["營業時間"] == "7:30~19:30"
    assert row["特殊營業時間"] == "假日8:30~14:30"
    unsafe = replace(restaurant, opening_hours='<script>alert(1)</script>', special_opening_hours='<img src=x>')
    markup = restaurant_card(unsafe)
    assert '<script>' not in markup and '<img src=x>' not in markup
    assert '&lt;script&gt;' in markup and '&lt;img' in markup
