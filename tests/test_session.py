"""Check visitor isolation and state transitions around the bundled real catalog."""

from dataclasses import replace
import random

from food_picker.catalog import parse_rows
from food_picker.defaults import load_default_catalog
from food_picker.models import Filters
from food_picker.session import PickerSession


def test_visitors_have_independent_catalogs_and_recommendation_history():
    first, second = PickerSession(), PickerSession()
    first.choose(Filters(), random.Random(3))
    result = parse_rows([["name", "area"], ["我的店家", "校外"]])
    first.import_catalog(result, "我的名單.xlsx")

    assert first.filename == "我的名單.xlsx"
    assert second.is_default and not second.is_demo and len(second.restaurants) == 10
    assert second.selected is None and second.history == []
    assert first.restaurants is not second.restaurants
    result.restaurants.clear()
    result.warnings.clear()
    assert len(first.restaurants) == 1
    assert first.warnings


def test_import_replaces_catalog_and_clears_previous_recommendations():
    session = PickerSession()
    session.choose(Filters(), random.Random(10))
    result = parse_rows([["餐廳名稱", "區域"], ["匯入店家", "校內"]])
    session.import_catalog(result, "餐廳.xlsx")

    assert not session.is_default and not session.is_demo
    assert session.restaurants == result.restaurants
    assert session.selected is None
    assert session.history == []
    assert [restaurant.name for restaurant in session.candidates(Filters())] == ["匯入店家"]


def test_selection_handles_empty_results_and_a_single_matching_restaurant():
    session = PickerSession()
    assert session.choose(Filters(query="沒有這間餐廳")) is None
    assert session.history == []

    only_restaurant = session.restaurants[0]
    filters = Filters(query=only_restaurant.name)
    assert session.choose(filters) == only_restaurant
    assert session.choose(filters) == only_restaurant
    assert session.history == [only_restaurant]

    assert session.choose(Filters(query="沒有這間餐廳")) is None
    assert session.selected is None
    assert session.history == [only_restaurant]


def test_history_contains_the_three_most_recent_distinct_recommendations():
    session = PickerSession()
    first, second, third, fourth = session.restaurants[:4]
    for restaurant in (first, second, third, first, fourth):
        session.choose(Filters(query=restaurant.name))

    assert session.selected == fourth
    assert session.history == [fourth, first, third]


def test_current_recommendation_is_hidden_when_location_filter_excludes_it():
    session = PickerSession()
    selected = session.choose(Filters(location="小吃部"), random.Random(0))

    assert session.current(Filters(location="清夜")) is None
    assert session.current(Filters(location="小吃部")) == selected
    assert session.selected == selected
    assert session.history == [selected]


def test_reset_restores_real_catalog_and_discards_imported_catalog_state():
    session = PickerSession()
    original = load_default_catalog()
    result = parse_rows([["name", "area"], ["匯入店家", "nearby"]])
    session.import_catalog(result, "餐廳.xlsx")
    session.choose(Filters())

    session.reset()

    assert session.is_default and not session.is_demo and session.filename is None
    assert len(session.restaurants) == 10
    assert session.restaurants == original.restaurants
    assert session.warnings == original.warnings
    assert session.selected is None and session.history == []
    assert all(not restaurant.name.startswith("示範・") for restaurant in session.restaurants)
    assert len(session.candidates(Filters())) == 10


def test_closed_restaurants_can_be_listed_but_are_never_recommended():
    base = load_default_catalog().restaurants[0]
    closed = replace(base, id="closed", name="已歇業的測試店", is_closed=True)
    opened = replace(base, id="open", name="營業中的測試店")
    session = PickerSession(restaurants=[closed, opened])
    filters = Filters(include_closed=True)
    assert session.candidates(filters) == [closed, opened]
    for seed in range(5):
        assert session.choose(filters, random.Random(seed)) == opened
    session.selected = closed
    assert session.current(filters) is None
    only_closed = PickerSession(restaurants=[closed])
    assert only_closed.candidates(filters) == [closed]
    assert only_closed.choose(filters) is None
    assert only_closed.history == []


def test_explicit_empty_session_does_not_load_another_catalog():
    session = PickerSession(restaurants=[])
    assert session.restaurants == []
    assert session.choose(Filters()) is None


def test_existing_catalog_list_is_copied_when_creating_session():
    restaurants = load_default_catalog().restaurants
    session = PickerSession(restaurants=restaurants)
    restaurants.clear()
    assert len(session.restaurants) == 10
