"""Shared data types for restaurant imports and recommendations."""

from dataclasses import asdict, dataclass
from typing import Literal

Area = Literal["campus", "nearby"]


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

    def to_dict(self) -> dict[str, object]:
        """Return plain values suitable for JSON and spreadsheet exports."""
        return asdict(self)


@dataclass(frozen=True)
class Filters:
    area: Literal["all", "campus", "nearby"] = "all"
    category: str = "all"
    max_price: float | None = None
    query: str = ""


@dataclass(frozen=True)
class ParseResult:
    restaurants: list[Restaurant]
    warnings: list[str]
