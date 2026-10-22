"""Verify spreadsheet data is represented accurately and safely in the interface."""

from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

from food_picker.defaults import load_default_catalog
from food_picker.presentation import (
    area_label, feature_labels, map_url, price_label, restaurant_card, table_rows,
)


def test_supplied_prices_stay_levels_and_maps_use_precise_coordinates():
    restaurant = load_default_catalog().restaurants[0]
    assert price_label(restaurant) == "價格等級 1 / 5"
    assert "NT$" not in price_label(restaurant)
    assert area_label(restaurant) == "公館"
    query = parse_qs(urlsplit(map_url(restaurant)).query)
    latitude, longitude = map(float, query["query"][0].split(","))
    assert (latitude, longitude) == (restaurant.latitude, restaurant.longitude)
    assert feature_labels(restaurant) == ["約會", "聚餐"]


def test_restaurant_cards_escape_untrusted_spreadsheet_text():
    restaurant = replace(
        load_default_catalog().restaurants[0],
        name='<img src=x onerror="alert(1)">',
        category='<script>alert("category")</script>',
        note='<script>alert("note")</script>',
    )
    html = restaurant_card(restaurant)
    assert '<img src=x' not in html and '<script>' not in html
    assert '&lt;img' in html and '&lt;script&gt;' in html
    assert 'rel="noopener noreferrer"' in html
    assert 'https://www.google.com/maps/search/' in html


def test_missing_levels_and_unverified_school_are_not_fabricated():
    restaurants = load_default_catalog().restaurants
    restaurant = next(r for r in restaurants if r.price_level is None)
    assert price_label(restaurant) == "價格未分級"
    school = next(r for r in restaurants if r.location == "School")
    assert "清大" not in area_label(school)
    assert "原名單" in area_label(school)


def test_detail_table_preserves_comments_flags_and_closed_record():
    restaurants = load_default_catalog().restaurants
    closed = next(r for r in restaurants if r.is_closed)
    row = table_rows([closed])[0]
    assert row["餐廳名稱"] == "郭董麻辣牛肉麵"
    assert row["備註"] == "關門了" and row["原表註記歇業"] is True
    assert (row["緯度"], row["經度"]) == (closed.latitude, closed.longitude)
    assert all(key in row for key in ["一個人吃", "約會", "聚餐", "快速上菜", "慢慢享用"])


def test_rich_catalog_optional_legacy_details_remain_visible():
    restaurant = replace(load_default_catalog().restaurants[0], price=150, distance=3, address="測試地址")
    row = table_rows([restaurant])[0]
    assert row["均消（元）"] == 150 and row["距離（公里）"] == 3
    assert row["地址"] == "測試地址"
