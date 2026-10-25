"""Shared data types for restaurant imports and recommendations."""

from dataclasses import asdict, dataclass
from typing import Literal

Area = Literal["campus", "nearby", "other"]


class ValidationError(ValueError):
    """A user-supplied restaurant catalog cannot be used safely."""


@dataclass(frozen=True)
class Restaurant:
    id: str
    name: str
    area: Area
    category: str
    price: float | None
    distance: float | None
    address: str
    note: str
    location: str = ""
    genre: str = ""
    price_level: float | None = None
    one_person: bool = False
    dating: bool = False
    gathering: bool = False
    fast_serve: bool = False
    slow_eat: bool = False
    latitude: float | None = None
    longitude: float | None = None
    is_closed: bool = False
    opening_hours: str = ""
    special_opening_hours: str = ""

    def to_dict(self) -> dict[str, object]:
        """Return plain values suitable for JSON and spreadsheet exports."""
        return asdict(self)


@dataclass(frozen=True)
class Filters:
    area: Literal["all", "campus", "nearby", "other"] = "all"
    category: str = "all"
    max_price: float | None = None
    query: str = ""
    location: str = "all"
    max_price_level: float | None = None
    one_person: bool = False
    dating: bool = False
    gathering: bool = False
    fast_serve: bool = False
    slow_eat: bool = False
    include_closed: bool = False
    locations: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    price_levels: tuple[float, ...] = ()


@dataclass(frozen=True)
class ParseResult:
    restaurants: list[Restaurant]
    warnings: list[str]
