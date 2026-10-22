"""Escaped display helpers for the food catalog and cinema-inspired cards."""

from html import escape
from urllib.parse import urlencode

from .catalog import location_label
from .models import Restaurant

GENRE_ICONS = {
    "Steak": "🥩", "SouthEastAsian": "🍛", "Ramen": "🍜", "Noodles": "🍜",
    "LouMei": "🥘", "Light": "🥗", "Korean": "🍲", "Japanese": "🍣",
    "Italian": "🍝", "HotPot": "🍲", "FastFood": "🍔", "Dessert": "🍰",
    "Chinese": "🥟", "Bento": "🍱", "American": "🍔", "Vegetarian": "🥬",
    "HongKong": "🥟", "French": "🥐", "Exotic": "🍽️", "Cafe": "☕",
    "BreakfastBrunch": "🥪", "Bar": "🍸", "Buffet": "🍽️", "Breakfast": "🍳",
    "Indian": "🍛",
}
GENRE_TONES = {
    "Steak": "ember", "SouthEastAsian": "gold", "Ramen": "ember", "Noodles": "gold",
    "LouMei": "plum", "Light": "forest", "Korean": "ember", "Japanese": "ocean",
    "Italian": "plum", "HotPot": "ember", "FastFood": "gold", "Dessert": "plum",
    "Chinese": "gold", "Bento": "forest", "American": "ember", "Vegetarian": "forest",
    "HongKong": "gold", "French": "plum", "Exotic": "ocean", "Cafe": "coffee",
    "BreakfastBrunch": "gold", "Bar": "plum", "Buffet": "forest", "Breakfast": "gold",
    "Indian": "gold",
}


def area_label(restaurant: Restaurant) -> str:
    if restaurant.location:
        return location_label(restaurant.location)
    return {"campus": "清大校內", "nearby": "校園周邊"}.get(restaurant.area, "未提供地點")


def number_label(value: float) -> str:
    number = float(value)
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}".rstrip("0").rstrip(".")


def price_label(restaurant: Restaurant) -> str:
    if restaurant.price_level is not None:
        return f"價格等級 {restaurant.price_level} / 5"
    return f"NT$ {number_label(restaurant.price)}" if restaurant.price is not None else "價格未分級"


def distance_label(restaurant: Restaurant) -> str:
    if restaurant.location:
        return location_label(restaurant.location)
    if restaurant.area == "campus":
        return "校內用餐"
    return "距離未驗證" if restaurant.distance is None else f"距離 {number_label(restaurant.distance)} 公里"


def map_url(restaurant: Restaurant) -> str:
    if restaurant.latitude is not None and restaurant.longitude is not None:
        query = f"{restaurant.latitude}, {restaurant.longitude}"
    else:
        query = f"{restaurant.name} {restaurant.address or area_label(restaurant)}"
    return "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": query})


def feature_labels(restaurant: Restaurant) -> list[str]:
    flags = ((restaurant.one_person, "一個人吃"), (restaurant.dating, "約會"),
             (restaurant.gathering, "聚餐"), (restaurant.fast_serve, "快速上菜"),
             (restaurant.slow_eat, "慢慢享用"))
    return [label for enabled, label in flags if enabled]


def poster_tone(restaurant: Restaurant) -> str:
    return GENRE_TONES.get(restaurant.genre, "ember")


def food_icon(restaurant: Restaurant) -> str:
    return GENRE_ICONS.get(restaurant.genre, "🍽️")


def restaurant_card(restaurant: Restaurant, index: int = 0) -> str:
    """Spreadsheet content is escaped before interpolation into presentation markup."""
    closed = '<span class="closed-badge">原表註記已歇業</span>' if restaurant.is_closed else ''
    tags = ''.join(f'<span>{escape(label)}</span>' for label in feature_labels(restaurant)[:2])
    note = f'<p class="card-note">{escape(restaurant.note)}</p>' if restaurant.note else ''
    return (
        f'<article class="food-card tone-{poster_tone(restaurant)}">'
        f'<a class="poster-link" href="{escape(map_url(restaurant), quote=True)}" '
        f'target="_blank" rel="noopener noreferrer" aria-label="在地圖查看 {escape(restaurant.name, quote=True)}">'
        '<div class="poster-art"><span class="poster-mark" aria-hidden="true">F</span>'
        f'{closed}<span class="poster-icon" aria-hidden="true">{food_icon(restaurant)}</span>'
        f'<span class="poster-genre">{escape(restaurant.genre or restaurant.category)}</span>'
        '<span class="poster-play" aria-hidden="true">↗</span></div>'
        f'<div class="card-body"><div class="card-meta"><span>{escape(area_label(restaurant))}</span>'
        f'<span>{escape(restaurant.category)}</span></div><h3>{escape(restaurant.name)}</h3>'
        f'<p class="card-price">{escape(price_label(restaurant))}</p>'
        f'<div class="card-tags">{tags}</div>{note}</div></a></article>'
    )


def table_rows(restaurants: list[Restaurant]) -> list[dict[str, object]]:
    return [
        {"餐廳名稱": r.name, "地點": area_label(r), "食物種類": r.category,
         "價格等級": r.price_level, "一個人吃": r.one_person, "約會": r.dating,
         "聚餐": r.gathering, "快速上菜": r.fast_serve, "慢慢享用": r.slow_eat,
         "緯度": r.latitude, "經度": r.longitude, "備註": r.note, "原表註記歇業": r.is_closed,
         **({"均消（元）": r.price, "距離（公里）": r.distance, "地址": r.address}
            if r.area != "other" or r.price is not None or r.distance is not None or r.address else {})}
        for r in restaurants
    ]
