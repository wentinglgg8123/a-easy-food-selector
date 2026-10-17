"""Keep each visitor's current catalog and recommendations in their own session."""

from dataclasses import dataclass, field
from random import Random

from .catalog import choose_restaurant, demo_restaurants, filter_restaurants
from .models import Filters, ParseResult, Restaurant


@dataclass
class PickerSession:
    """Framework-independent state; uploaded spreadsheets are never written to disk."""

    restaurants: list[Restaurant] = field(default_factory=demo_restaurants)
    filename: str | None = None
    warnings: list[str] = field(default_factory=list)
    selected: Restaurant | None = None
    history: list[Restaurant] = field(default_factory=list)

    @property
    def is_demo(self) -> bool:
        return self.filename is None

    def import_catalog(self, result: ParseResult, filename: str) -> None:
        self.restaurants = list(result.restaurants)
        self.filename = filename
        self.warnings = list(result.warnings)
        self.selected = None
        self.history = []

    def reset(self) -> None:
        self.restaurants = demo_restaurants()
        self.filename = None
        self.warnings = []
        self.selected = None
        self.history = []

    def candidates(self, filters: Filters) -> list[Restaurant]:
        return filter_restaurants(self.restaurants, filters)

    def current(self, filters: Filters) -> Restaurant | None:
        if self.selected and any(r.id == self.selected.id for r in self.candidates(filters)):
            return self.selected
        return None

    def choose(self, filters: Filters, rng: Random | None = None) -> Restaurant | None:
        previous_id = self.selected.id if self.selected else None
        self.selected = choose_restaurant(self.candidates(filters), previous_id, rng)
        if self.selected:
            self.history = [self.selected, *[r for r in self.history if r.id != self.selected.id]][:3]
        return self.selected
