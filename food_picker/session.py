"""Keep each visitor's current catalog and recommendations in their own session."""

from dataclasses import dataclass, field
from random import Random

from .catalog import choose_restaurant, filter_restaurants
from .defaults import load_default_catalog
from .models import Filters, ParseResult, Restaurant


@dataclass
class PickerSession:
    """Framework-independent state; uploaded spreadsheets are never written to disk."""

    restaurants: list[Restaurant] | None = None
    filename: str | None = None
    warnings: list[str] = field(default_factory=list)
    selected: Restaurant | None = None
    history: list[Restaurant] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.restaurants is None:
            result = load_default_catalog()
            self.restaurants = list(result.restaurants)
            self.warnings = list(result.warnings)
        else:
            self.restaurants = list(self.restaurants)

    @property
    def is_default(self) -> bool:
        return self.filename is None

    @property
    def is_demo(self) -> bool:
        """Compatibility property: the built-in catalog now contains the supplied real data."""
        return False

    def import_catalog(self, result: ParseResult, filename: str) -> None:
        self.restaurants = list(result.restaurants)
        self.filename = filename
        self.warnings = list(result.warnings)
        self.selected = None
        self.history = []

    def reset(self) -> None:
        result = load_default_catalog()
        self.restaurants = list(result.restaurants)
        self.filename = None
        self.warnings = list(result.warnings)
        self.selected = None
        self.history = []

    def candidates(self, filters: Filters) -> list[Restaurant]:
        assert self.restaurants is not None
        return filter_restaurants(self.restaurants, filters)

    def current(self, filters: Filters) -> Restaurant | None:
        if self.selected and not self.selected.is_closed and any(r.id == self.selected.id for r in self.candidates(filters)):
            return self.selected
        return None

    def choose(self, filters: Filters, rng: Random | None = None) -> Restaurant | None:
        previous_id = self.selected.id if self.selected else None
        eligible = [restaurant for restaurant in self.candidates(filters) if not restaurant.is_closed]
        self.selected = choose_restaurant(eligible, previous_id, rng)
        if self.selected:
            self.history = [self.selected, *[r for r in self.history if r.id != self.selected.id]][:3]
        return self.selected
