"""Validate, filter, and select restaurants without a web framework dependency."""

from collections.abc import Sequence
from hashlib import sha256
import json
import math
import random
import re
import unicodedata

from .models import Area, Filters, ParseResult, Restaurant, ValidationError

MAX_DATA_ROWS = 5_000
LOCATION_LABELS = {
    "Gongguan": "公館",
    "Heping118": "和平 118 巷",
    "Liuzhangli": "六張犁",
    "NTUMed": "臺大醫學院",
    "NTUST": "臺灣科技大學",
    "School": "校內（原名單）",
    "Shida": "師大",
    "XinshengSouth": "新生南路",
}
GENRE_LABELS = {
    "Bento": "便當",
    "Chinese": "中式料理",
    "Japanese": "日式料理",
    "Noodles": "麵食",
    "Ramen": "拉麵",
    "SouthEastAsian": "東南亞料理",
    "Dessert": "甜點",
    "Steak": "牛排",
    "Light": "輕食",
    "Italian": "義式料理",
    "Cafe": "咖啡廳",
    "HotPot": "火鍋",
    "FastFood": "速食",
    "HongKong": "港式料理",
    "Buffet": "自助餐",
    "Korean": "韓式料理",
    "American": "美式料理",
    "Vegetarian": "蔬食",
    "BreakfastBrunch": "早午餐",
    "French": "法式料理",
    "LouMei": "滷味",
    "Exotic": "異國料理",
    "Bar": "酒吧",
    "Breakfast": "早餐",
    "Indian": "印度料理",
}
FLAG_COLUMNS = ("one_person", "dating", "gathering", "fast_serve", "slow_eat")
COLUMN_NAMES = {
    "name": "餐廳名稱",
    "area": "區域",
    "category": "類型",
    "price": "均消",
    "distance": "距離（公里）",
    "address": "地址",
    "note": "備註",
    "location": "Location（地點）",
    "genre": "Genre（料理類型）",
    "price_level": "Price（價位等級）",
    "one_person": "OnePerson（一人用餐）",
    "dating": "Dating（約會）",
    "gathering": "Gathering（聚餐）",
    "fast_serve": "FastServe（快速用餐）",
    "slow_eat": "SlowEat（慢慢享用）",
    "coordinates": "Coordinates（座標）",
    "opening_hours": "Available time（營業時間）",
    "special_opening_hours": "special available time（特殊營業時間）",
}
COLUMN_ALIASES = {
    "name": ("餐廳名稱", "店家名稱", "餐廳", "店名", "名稱", "name", "restaurant name"),
    "area": ("區域", "地區", "區別", "校內/校外", "區域（校內/校外）", "area", "region"),
    "category": ("類型", "分類", "餐點類型", "料理類型", "category", "type"),
    "price": ("均消", "均消（元）", "平均消費", "平均價格", "價格", "預算", "price"),
    "distance": ("距離（公里）", "距離（km）", "距離", "公里", "distance", "distance km"),
    "address": ("地址", "住址", "address"),
    "note": ("備註", "說明", "note", "notes"),
}
TEXT_LIMITS = {
    "name": 200, "area": 80, "category": 80, "address": 500, "note": 2_000,
    "location": 80, "genre": 80,
    "opening_hours": 500, "special_opening_hours": 500,
}
_NUMBER = re.compile(r"(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)", re.ASCII)


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _header_key(value: str) -> str:
    return re.sub(r"[\s_\-()/]", "", _normalise(value))


def _label(code: str, labels: dict[str, str], fallback: str) -> str:
    key = _normalise(code)
    return next((label for original, label in labels.items() if _normalise(original) == key), code.strip() or fallback)


def location_label(code: str) -> str:
    """Localize known source codes while preserving unrecognized locations."""
    return _label(code, LOCATION_LABELS, "未提供地點")


def genre_label(code: str) -> str:
    """Localize known source codes without guessing unfamiliar cuisines."""
    return _label(code, GENRE_LABELS, "未分類")


def _genre_categories(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        genre_label(part.strip()) for part in re.split(r"[,，、]", value) if part.strip()
    ))


def restaurant_categories(restaurant: Restaurant) -> tuple[str, ...]:
    """Expose each cuisine tag while preserving the original spreadsheet genre."""
    return _genre_categories(restaurant.genre or restaurant.category) or ("未分類",)


_HEADER_COLUMNS = {
    _header_key(alias): column
    for column, aliases in COLUMN_ALIASES.items()
    for alias in aliases
}
_RICH_COLUMN_ALIASES = {
    "name": ("Restaurant",),
    "location": ("Location",),
    "genre": ("Genre", "Gener"),
    "price_level": ("Price", "PriceLevel"),
    "one_person": ("OnePerson",),
    "dating": ("Dating",),
    "gathering": ("Gathering",),
    "fast_serve": ("FastServe",),
    "slow_eat": ("SlowEat",),
    "coordinates": ("Coordinates",),
    "note": ("Comments",),
    "opening_hours": ("Available time", "營業時間"),
    "special_opening_hours": ("special available time", "特殊營業時間"),
}
_RICH_HEADER_COLUMNS = {
    **_HEADER_COLUMNS,
    **{
        _header_key(alias): column
        for column, aliases in _RICH_COLUMN_ALIASES.items()
        for alias in aliases
    },
}
_RICH_MARKERS = {"restaurant", "location", "genre", "gener", "oneperson", "dating", "gathering", "fastserve", "sloweat", "coordinates", "comments", "pricelevel", "availabletime", "specialavailabletime"}
_CAMPUS = {
    "校內", "學餐", "校內學餐", "清大校內", "清華校內", "清華大學校內",
    "國立清華大學校內", "campus", "oncampus",
}
_NEARBY = {
    "校外", "周邊", "周圍", "附近", "校園周邊", "清大周邊", "清華周邊",
    "清華大學周邊", "校外2公里內", "周邊2公里內", "nearby", "offcampus",
}


def _blank(value: object) -> bool:
    return value is None or isinstance(value, str) and not value.strip()


def _is_row(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _validate_cell(value: object, *, allow_bool: bool = False) -> None:
    """Reject executable formulas and unsupported Excel cell types in any column."""
    if _blank(value):
        return
    if allow_bool and isinstance(value, bool):
        return
    if isinstance(value, str):
        if _normalise(value).startswith("="):
            raise ValidationError("含有 Excel 公式，請貼上為純文字或數值後重新匯入，已略過")
        if len(value) > 2_000:
            raise ValidationError("儲存格文字超過 2,000 字，請縮短內容，已略過")
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("含有日期、布林值或其他不支援的格式，請改為文字或數值，已略過")
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValidationError("含有無效數字，請填入有限數值，已略過")


def _text(value: object, column: str) -> str:
    if _blank(value):
        return ""
    result = str(value).strip()
    limit = TEXT_LIMITS[column]
    if len(result) > limit:
        raise ValidationError(f"「{COLUMN_NAMES[column]}」超過 {limit:,} 字，請縮短內容，已略過")
    return result


def _number(value: object, column: str) -> float | None:
    if _blank(value):
        return None
    message = f"「{COLUMN_NAMES[column]}」必須是有效的非負數字，請勿填入範圍或不明單位，已略過"
    if isinstance(value, str):
        cleaned = unicodedata.normalize("NFKC", value).strip()
        if column == "price":
            cleaned = re.sub(r"^(?:NT\$|NTD|TWD|\$)\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*(?:元|NTD|TWD)$", "", cleaned, flags=re.IGNORECASE).strip()
        else:
            cleaned = re.sub(r"\s*(?:公里|km)$", "", cleaned, flags=re.IGNORECASE).strip()
        if not _NUMBER.fullmatch(cleaned):
            raise ValidationError(message)
        cleaned = cleaned.replace(",", "")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        cleaned = value
    else:
        raise ValidationError(message)
    try:
        result = float(cleaned)
    except (ValueError, OverflowError):
        raise ValidationError(message) from None
    if not math.isfinite(result) or result < 0:
        raise ValidationError(message)
    return result


def _area(value: object) -> Area:
    key = _header_key(_text(value, "area"))
    if key in _CAMPUS:
        return "campus"
    if key in _NEARBY:
        return "nearby"
    if key in {"other", "其他", "一般名單"}:
        return "other"
    raise ValidationError("「區域」請填寫「校內」或「校外」，已略過")


def _price_level(value: object) -> float | None:
    if _blank(value):
        return None
    message = "「Price」必須是 1 到 5、以 0.5 遞增的價位等級，不代表新台幣金額，已略過"
    if isinstance(value, str):
        value = unicodedata.normalize("NFKC", value).strip()
        if not re.fullmatch(r"\d+(?:\.\d+)?", value, flags=re.ASCII):
            raise ValidationError(message)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        number = math.nan
    if isinstance(value, bool) or not math.isfinite(number) or not 1 <= number <= 5 or not (number * 2).is_integer():
        raise ValidationError(message)
    return int(number) if number.is_integer() else number


def _flag(value: object, column: str) -> bool:
    if _blank(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        key = _normalise(value)
        if key in {"o", "○", "✓", "✔", "yes", "true", "1", "是"}:
            return True
        if key in {"no", "false", "0", "否"}:
            return False
    raise ValidationError(f"「{COLUMN_NAMES[column]}」請填 O、○、✓、yes、true、1，或留白表示否，已略過")


def _coordinates(value: object) -> tuple[float | None, float | None]:
    if _blank(value):
        return None, None
    message = "「Coordinates」格式或範圍無效，請填「緯度, 經度」；已保留餐廳但不提供座標地圖"
    if not isinstance(value, str):
        raise ValidationError(message)
    parts = unicodedata.normalize("NFKC", value).split(",")
    if len(parts) != 2:
        raise ValidationError(message)
    try:
        latitude, longitude = (float(part.strip()) for part in parts)
    except (ValueError, OverflowError):
        raise ValidationError(message) from None
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValidationError(message)
    return latitude, longitude


def _closed(note: str) -> bool:
    text = re.sub(r"\s", "", _normalise(note)).strip("。.!！")
    return text in {"閉店", "已閉店", "關門了", "已關門", "已歇業", "永久歇業"}


def parse_rows(rows: Sequence[Sequence[object]]) -> ParseResult:
    """Read the first nonempty row as headers; warnings use Excel row numbers.

    Invalid rows are skipped without discarding other valid restaurants. A missing
    header, excessive row count, or catalog with no valid entries is a fatal error.
    Unknown columns are allowed, but formulas and unsupported types remain invalid.
    """
    if not _is_row(rows) or not rows:
        raise ValidationError("Excel 沒有資料。請加入「餐廳名稱」與「區域」欄位，以及至少一間餐廳。")
    header_index = next(
        (index for index, row in enumerate(rows) if not _is_row(row) or any(not _blank(cell) for cell in row)),
        None,
    )
    if header_index is None:
        raise ValidationError("Excel 沒有資料。請加入「餐廳名稱」與「區域」欄位，以及至少一間餐廳。")
    header = rows[header_index]
    if not _is_row(header):
        raise ValidationError("欄位列格式無法辨識，請將欄位名稱放在第一個有資料的列。")
    data_rows = rows[header_index + 1:]
    nonempty_count = sum(not _is_row(row) or any(not _blank(cell) for cell in row) for row in data_rows)
    if nonempty_count > MAX_DATA_ROWS:
        raise ValidationError(f"Excel 最多支援 {MAX_DATA_ROWS:,} 筆餐廳資料，請分割檔案後重新匯入。")

    rich_schema = any(isinstance(value, str) and _header_key(value) in _RICH_MARKERS for value in header)
    header_columns = _RICH_HEADER_COLUMNS if rich_schema else _HEADER_COLUMNS
    columns: dict[str, int] = {}
    for index, value in enumerate(header):
        column = header_columns.get(_header_key(value)) if isinstance(value, str) else None
        if column is None:
            continue
        if column in columns:
            raise ValidationError(f"欄位「{COLUMN_NAMES[column]}」出現多次，請保留一欄後重新匯入。")
        columns[column] = index
    required_columns = ("name", "location", "genre") if rich_schema else ("name", "area")
    missing = [f"「{COLUMN_NAMES[column]}」" for column in required_columns if column not in columns]
    if missing:
        raise ValidationError(f"缺少必要欄位：{'、'.join(missing)}。請將欄位名稱放在第一個有資料的列。")

    restaurants: list[Restaurant] = []
    seen: set[str] = set()
    warning_rows: dict[str, list[int]] = {}

    def warn(message: str, row_number: int) -> None:
        warning_rows.setdefault(message, []).append(row_number)

    for row_number, row in enumerate(data_rows, start=header_index + 2):
        if not _is_row(row):
            warn("資料列格式無法辨識，已略過", row_number)
            continue
        if all(_blank(value) for value in row):
            continue

        def cell(column: str) -> object:
            index = columns.get(column)
            return row[index] if index is not None and index < len(row) else None

        try:
            flag_indexes = {columns[column] for column in FLAG_COLUMNS if column in columns} if rich_schema else set()
            for index, value in enumerate(row):
                _validate_cell(value, allow_bool=index in flag_indexes)
            name = _text(cell("name"), "name")
            if not name:
                raise ValidationError("缺少餐廳名稱，請補上名稱，已略過")
            area = _area(cell("area")) if not rich_schema or not _blank(cell("area")) else "other"
            price = _number(cell("price"), "price")
            distance = _number(cell("distance"), "distance")
            if area == "nearby" and distance is not None and distance > 2:
                raise ValidationError("校外餐廳超過 2 公里範圍，請確認距離單位為公里，已略過")
            address = _text(cell("address"), "address")
            location = _text(cell("location"), "location") if rich_schema else ""
            genre = _text(cell("genre"), "genre") if rich_schema else ""
            category = (
                ", ".join(_genre_categories(genre)) or "未分類"
                if rich_schema else _text(cell("category"), "category") or "未分類"
            )
            note = _text(cell("note"), "note")
            opening_hours = _text(cell("opening_hours"), "opening_hours") if rich_schema else ""
            special_opening_hours = _text(cell("special_opening_hours"), "special_opening_hours") if rich_schema else ""
            price_level = _price_level(cell("price_level")) if rich_schema else None
            flags = {column: _flag(cell(column), column) for column in FLAG_COLUMNS} if rich_schema else {}
            latitude, longitude = None, None
            if rich_schema:
                try:
                    latitude, longitude = _coordinates(cell("coordinates"))
                except ValidationError as error:
                    warn(str(error), row_number)
            identity = [_normalise(name), _normalise(location), latitude, longitude] if rich_schema else [_normalise(name), _normalise(address), area]
            key = json.dumps(identity, ensure_ascii=False)
            if key in seen:
                warn("相同名稱、地點與座標的餐廳重複，已保留第一筆" if rich_schema else "相同名稱、地址與區域的餐廳重複，已保留第一筆", row_number)
                continue
            seen.add(key)
            restaurant_id = f"restaurant-{sha256(key.encode()).hexdigest()[:20]}"
            restaurants.append(Restaurant(
                restaurant_id, name, area, category, price, distance, address, note,
                location=location, genre=genre, price_level=price_level,
                latitude=latitude, longitude=longitude, is_closed=_closed(note), **flags,
                opening_hours=opening_hours, special_opening_hours=special_opening_hours,
            ))
            if area == "nearby" and distance is None:
                warn("校外餐廳未填距離，已匯入但尚未確認是否在 2 公里內；請補上「距離（公里）」", row_number)
        except ValidationError as error:
            warn(str(error), row_number)

    warnings = []
    for message, row_numbers in warning_rows.items():
        references = "、".join(str(number) for number in row_numbers[:12])
        suffix = f" 等 {len(row_numbers)} 列" if len(row_numbers) > 12 else " 列"
        warnings.append(f"第 {references}{suffix}：{message}。")
    if not restaurants:
        raise ValidationError("沒有可使用的餐廳資料。請至少填寫一間名稱與區域正確的餐廳。" + " ".join(warnings[:3]))
    return ParseResult(restaurants, warnings)


def filter_restaurants(restaurants: Sequence[Restaurant], filters: Filters) -> list[Restaurant]:
    """Match any selected value per group and apply all filter groups together.

    Empty multi-select tuples leave that group unrestricted. Legacy singular
    fields remain additional constraints, including their budget semantics.
    """
    query = _normalise(filters.query)
    locations = {_normalise(location) for location in filters.locations}
    categories = {_normalise(category) for category in filters.categories}
    price_levels = set(filters.price_levels)
    result = []
    for restaurant in restaurants:
        if restaurant.is_closed and not filters.include_closed:
            continue
        if restaurant.area == "nearby" and restaurant.distance is not None:
            if not math.isfinite(restaurant.distance) or not 0 <= restaurant.distance <= 2:
                continue
        if filters.area != "all" and restaurant.area != filters.area:
            continue
        category_values = {
            _normalise(restaurant.category), _normalise(restaurant.genre),
            *(_normalise(category) for category in restaurant_categories(restaurant)),
            *(_normalise(category.strip()) for category in re.split(r"[,，、]", restaurant.genre) if category.strip()),
        }
        if filters.category != "all" and _normalise(filters.category) not in category_values:
            continue
        if categories and categories.isdisjoint(category_values):
            continue
        if filters.location != "all" and _normalise(filters.location) != _normalise(restaurant.location):
            continue
        if locations and _normalise(restaurant.location) not in locations:
            continue
        if price_levels:
            level = restaurant.price_level
            if level is None:
                continue
            matching_levels = {level}
            if level % 1 == 0.5:
                matching_levels.update((level - 0.5, level + 0.5))
            if price_levels.isdisjoint(matching_levels):
                continue
        if filters.max_price_level is not None and (restaurant.price_level is None or restaurant.price_level > filters.max_price_level):
            continue
        if any(getattr(filters, column) and not getattr(restaurant, column) for column in FLAG_COLUMNS):
            continue
        if filters.max_price is not None:
            if restaurant.price is None or not math.isfinite(restaurant.price) or restaurant.price > filters.max_price:
                continue
        searchable = (restaurant.name, restaurant.address, restaurant.category, restaurant.genre, restaurant.location, location_label(restaurant.location), restaurant.note)
        if query and not any(query in _normalise(value) for value in searchable):
            continue
        result.append(restaurant)
    return result


def choose_restaurant(
    restaurants: Sequence[Restaurant],
    previous_id: str | None = None,
    rng: random.Random | None = None,
) -> Restaurant | None:
    """Pick uniformly; avoid the previous restaurant whenever an alternative exists."""
    if not restaurants:
        return None
    alternatives = [restaurant for restaurant in restaurants if restaurant.id != previous_id]
    pool = alternatives or list(restaurants)
    return (rng if rng is not None else random.SystemRandom()).choice(pool)


def demo_restaurants() -> list[Restaurant]:
    """Return a fresh catalog of eight explicitly fictional demonstration records."""
    note = "此為示範資料，非真實店家名單"
    campus_address = "清華大學校內（示範位置）"
    nearby_address = "清華大學周邊（示範位置）"
    return [
        Restaurant("demo-campus-noodles", "示範・校園麵食", "campus", "中式", 85, None, campus_address, note),
        Restaurant("demo-campus-rice", "示範・校園日式食堂", "campus", "日式", 120, None, campus_address, note),
        Restaurant("demo-campus-breakfast", "示範・校園早午餐", "campus", "早餐", 60, None, campus_address, note),
        Restaurant("demo-campus-salad", "示範・校園輕食", "campus", "輕食", 95, None, campus_address, note),
        Restaurant("demo-nearby-dumplings", "示範・巷口水餃", "nearby", "中式", 100, 0.6, nearby_address, note),
        Restaurant("demo-nearby-japanese", "示範・街角日式小館", "nearby", "日式", 180, 1.2, nearby_address, note),
        Restaurant("demo-nearby-breakfast", "示範・晨光早餐", "nearby", "早餐", 70, 0.8, nearby_address, note),
        Restaurant("demo-nearby-salad", "示範・午後輕食", "nearby", "輕食", 150, 1.6, nearby_address, note),
    ]
