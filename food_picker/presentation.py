"""Small, escaped display helpers shared by the Python interface and exports."""

from html import escape
from urllib.parse import urlencode

from .models import Restaurant


def area_label(restaurant: Restaurant) -> str:
    return "清大校內" if restaurant.area == "campus" else "校園周邊"


def number_label(value: float) -> str:
    return f"{value:,.0f}" if value.is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")


def price_label(restaurant: Restaurant) -> str:
    return "均消未提供" if restaurant.price is None else f"NT$ {number_label(float(restaurant.price))}"


def distance_label(restaurant: Restaurant) -> str:
    if restaurant.area == "campus":
        return "校內用餐"
    if restaurant.distance is None:
        return "距離未驗證"
    return f"距離 {number_label(float(restaurant.distance))} 公里"


def map_url(restaurant: Restaurant) -> str:
    query = f"{restaurant.name} {restaurant.address or '新竹 清華大學'}"
    return "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": query})


def restaurant_card(restaurant: Restaurant) -> str:
    """Untrusted spreadsheet text is always escaped before insertion into markup."""
    icon = "🥗" if restaurant.category == "輕食" else "☕" if restaurant.category == "早餐" else "🍚"
    return (
        '<article class="food-card">'
        f'<span class="food-card-icon" aria-hidden="true">{icon}</span>'
        '<div class="food-card-copy">'
        f'<span class="muted">{escape(area_label(restaurant))} · {escape(restaurant.category)}</span>'
        f'<h3>{escape(restaurant.name)}</h3>'
        f'<p>{escape(price_label(restaurant))} / 人 · {escape(distance_label(restaurant))}</p>'
        '</div></article>'
    )


def table_rows(restaurants: list[Restaurant]) -> list[dict[str, object]]:
    return [
        {
            "餐廳名稱": r.name,
            "區域": area_label(r),
            "類型": r.category,
            "均消（元）": r.price,
            "距離（公里）": r.distance,
            "地址": r.address,
            "備註": r.note,
        }
        for r in restaurants
    ]
