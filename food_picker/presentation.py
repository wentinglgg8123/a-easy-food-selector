"""Escaped display helpers for the food catalog and compact restaurant cards."""

from html import escape
import math
from urllib.parse import urlencode

from .catalog import location_label
from .models import Restaurant

PRICE_RANGES = {
    1: "NT$0–100",
    2: "NT$100–200",
    3: "NT$200–300",
    4: "NT$300–500",
    5: "NT$500以上",
}

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


def coin_label(level: float | None) -> str:
    """Display the existing source level without changing its stored value."""
    if isinstance(level, (int, float)) and not isinstance(level, bool) and 1 <= level <= 5 and level * 2 == int(level * 2):
        return "🪙" * int(level) if float(level).is_integer() else f"🪙 × {number_label(level)}"
    return "價格未提供"


def price_label(restaurant: Restaurant) -> str:
    if restaurant.price_level in PRICE_RANGES:
        return f"{coin_label(restaurant.price_level)} · {PRICE_RANGES[restaurant.price_level]}"
    if restaurant.price_level is not None and coin_label(restaurant.price_level) != "價格未提供":
        return coin_label(restaurant.price_level)
    return f"NT$ {number_label(restaurant.price)}" if restaurant.price is not None else "價格未提供"


def price_html(restaurant: Restaurant) -> str:
    """Draw fractional source levels as actual half coins without inventing a budget."""
    level = restaurant.price_level
    if level is None or coin_label(level) == "價格未提供" or float(level).is_integer():
        return escape(price_label(restaurant))
    coins = '<span aria-hidden="true">🪙</span>' * math.floor(level)
    coins += '<span class="price-half-coin" aria-hidden="true"><span>🪙</span></span>'
    return f'<span class="price-coins" role="img" aria-label="{number_label(level)} 枚金幣">{coins}</span>'


def hours_html(restaurant: Restaurant) -> str:
    """Show the supplied schedule as text; it is not a live opening-status check."""
    return ''.join(
        f'<p class="card-hours">{label}：{escape(value)}</p>'
        for label, value in (("營業時間", restaurant.opening_hours), ("特殊營業時間", restaurant.special_opening_hours))
        if value
    )


def price_legend_html() -> str:
    """Explain the requested coin ranges without suggesting a precise meal price."""
    items = ''.join(
        '<span class="price-legend-item" role="listitem">'
        f'<span class="price-legend-coins" aria-label="{level} 枚金幣">{coin_label(level)}</span>'
        f'<span>{escape(price_range)}</span></span>'
        for level, price_range in PRICE_RANGES.items()
    )
    return f'<div class="price-legend" role="list" aria-label="金幣價格範圍說明">{items}</div>'


def distance_label(restaurant: Restaurant) -> str:
    if restaurant.location:
        return location_label(restaurant.location)
    if restaurant.area == "campus":
        return "校內用餐"
    return "距離未驗證" if restaurant.distance is None else f"距離 {number_label(restaurant.distance)} 公里"


def map_url(restaurant: Restaurant) -> str:
    """Search the supplied restaurant name instead of opening a generic coordinate pin.

    The source catalog has no verified postal addresses or Google Place IDs. Its
    location label and Taiwan provide search context without inventing either.
    Explicit legacy addresses take precedence over the broader location label.
    """
    if restaurant.address.strip():
        query = f"{restaurant.name} {restaurant.address.strip()}"
    else:
        location = area_label(restaurant)
        context = {
            "小吃部": "國立清華大學 小吃部 新竹市",
            "清夜": "清大夜市 新竹市",
        }.get(location, location if location != "未提供地點" else "")
        query = " ".join(part for part in (restaurant.name, context, "台灣") if part)
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
    location = (
        f'地址：{restaurant.address.strip()}' if restaurant.address.strip()
        else f'地點：{area_label(restaurant)}'
    )
    return (
        f'<article class="food-card tone-{poster_tone(restaurant)}">'
        f'<a class="poster-link" href="{escape(map_url(restaurant), quote=True)}" '
        f'target="_blank" rel="noopener noreferrer" '
        f'aria-label="在 Google 地圖搜尋 {escape(restaurant.name, quote=True)}（在新分頁開啟）">'
        '<div class="poster-art">'
        f'{closed}<span class="poster-icon" aria-hidden="true">{food_icon(restaurant)}</span>'
        '<span class="poster-play" aria-hidden="true">↗</span></div>'
        f'<div class="card-body"><div class="card-meta"><span>{escape(area_label(restaurant))}</span>'
        f'<span>{escape(restaurant.category)}</span></div><h3>{escape(restaurant.name)}</h3>'
        f'<p class="card-price">{price_html(restaurant)}</p>'
        f'<p class="card-location">{escape(location)} '
        '<span class="card-map-label">Google 地圖搜尋 ↗</span></p>'
        f'{hours_html(restaurant)}<div class="card-tags">{tags}</div>{note}</div></a></article>'
    )


def table_rows(restaurants: list[Restaurant]) -> list[dict[str, object]]:
    return [
        {"餐廳名稱": r.name, "地點": area_label(r), "食物種類": r.category,
         "價格": price_label(r), "一個人吃": r.one_person, "約會": r.dating,
         "聚餐": r.gathering, "快速上菜": r.fast_serve, "慢慢享用": r.slow_eat,
         "緯度": r.latitude, "經度": r.longitude, "Google 地圖": map_url(r),
         "營業時間": r.opening_hours, "特殊營業時間": r.special_opening_hours,
         "備註": r.note, "原表註記歇業": r.is_closed,
         **({"均消（元）": r.price, "距離（公里）": r.distance, "地址": r.address}
            if r.area != "other" or r.price is not None or r.distance is not None or r.address else {})}
        for r in restaurants
    ]
