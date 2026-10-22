"""Load the user-provided bundled catalog, with explicit errors on deployment issues."""

from pathlib import Path

from .excel import parse_excel
from .models import ParseResult, ValidationError

DEFAULT_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "food.xlsx"


def load_default_catalog() -> ParseResult:
    """Return fresh catalog objects; a missing or broken real list never becomes demo data."""
    try:
        content = DEFAULT_DATA_PATH.read_bytes()
    except OSError as error:
        raise ValidationError("無法讀取內建餐廳名單 data/food.xlsx，請確認檔案存在且可讀。") from error
    try:
        return parse_excel(content, DEFAULT_DATA_PATH.name)
    except ValidationError as error:
        raise ValidationError(f"內建餐廳名單 data/food.xlsx 無法載入：{error}") from error
