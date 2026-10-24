"""Real Chromium checks for shared restaurant data on desktop and mobile screens."""

from io import BytesIO
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from openpyxl import Workbook, load_workbook
from playwright.sync_api import expect, sync_playwright
import pytest

from food_picker.excel import EXCEL_HEADERS

pytestmark = pytest.mark.browser
ROOT = Path(__file__).resolve().parents[1]
APP_URL = "http://127.0.0.1:8501"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
RESULT = 'section[aria-label="餐廳推薦結果"]'


def _server_ready() -> bool:
    try:
        with urlopen(f"{APP_URL}/_stcore/health", timeout=1) as response:
            return response.status == 200 and response.read() == b"ok"
    except (OSError, URLError):
        return False


@pytest.fixture(scope="module")
def app_url(tmp_path_factory):
    """Reuse a running local app, or start and clean up this fixture's own server."""
    if _server_ready():
        yield APP_URL
        return
    log_path = tmp_path_factory.mktemp("streamlit") / "server.log"
    with log_path.open("w+") as log:
        process = subprocess.Popen(
            [
                sys.executable, "-m", "streamlit", "run", "app.py",
                "--server.port", "8501", "--server.headless", "true",
                "--browser.gatherUsageStats", "false",
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while not _server_ready():
                if process.poll() is not None or time.monotonic() >= deadline:
                    log.seek(0)
                    pytest.fail(f"Streamlit did not become ready:\n{log.read()}")
                time.sleep(0.2)
            yield APP_URL
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        options = {"headless": True, "args": ["--no-sandbox"]}
        if executable := os.environ.get("CHROMIUM_PATH"):
            options["executable_path"] = executable
        instance = playwright.chromium.launch(**options)
        yield instance
        instance.close()


@pytest.fixture(params=[{"width": 1440, "height": 1000}, {"width": 390, "height": 844}], ids=["desktop", "mobile"])
def page(browser, app_url, request):
    context = browser.new_context(viewport=request.param, accept_downloads=True)
    page = context.new_page()
    page.set_default_timeout(15_000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(app_url)
    expect(page.get_by_role("button", name="幫我決定這一餐", exact=True)).to_be_visible()
    _wait_idle(page)
    try:
        yield page
        assert errors == [], f"Uncaught browser errors: {errors}"
        widths = page.evaluate("""() => ({
            viewport: window.innerWidth,
            document: document.documentElement.scrollWidth,
            main: document.querySelector('[data-testid="stMain"]').scrollWidth,
            mainClient: document.querySelector('[data-testid="stMain"]').clientWidth
        })""")
        assert widths["document"] <= widths["viewport"] + 1, widths
        assert widths["main"] <= widths["mainClient"] + 1, widths
    finally:
        context.close()


def _workbook(rows, *, extra_sheet=False) -> bytes:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    if extra_sheet:
        second = workbook.create_sheet("第二張不應載入")
        second.append(EXCEL_HEADERS)
        second.append(["第二張不應載入", "Gongguan", "Bento", 1])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _catalog_bytes() -> bytes:
    return _workbook([
        EXCEL_HEADERS,
        ["測試旗標完整店", "Gongguan", "Bento", 2, "O", "O", "O", "O", "O", "25.01826359388706, 121.5310917601049", "測試學生優惠"],
        ["測試缺少節奏店", "Gongguan", "Bento", 2, "O", "O", "O", "", "O", "25.04, 121.55", "第二間測試店家"],
        ["測試別區店", "Shida", "Steak", 4, "", "O", "O", "", "O", "25.05, 121.56", ""],
    ], extra_sheet=True)


def _upload(page, content: bytes, filename="測試餐廳.xlsx"):
    page.get_by_role("button", name="匯入 Excel 名單", exact=True).click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    dialog.locator('input[type="file"]').set_input_files(
        {"name": filename, "mimeType": MIME_XLSX, "buffer": content}
    )
    confirm = dialog.get_by_role("button", name="確認匯入", exact=True)
    expect(confirm).to_be_enabled()
    confirm.click()
    return dialog


def _import_catalog(page):
    dialog = _upload(page, _catalog_bytes())
    expect(dialog).not_to_be_visible()
    expect(page.get_by_text("已匯入 3 間餐廳，開始你的美食探索。", exact=True)).to_be_visible()
    _expect_count(page, 3)


def _select_pills(page, label, values):
    for value in values:
        _wait_idle(page)
        button = page.get_by_role("toolbar", name=label, exact=True).get_by_role(
            "button", name=value, exact=True
        )
        expect(button).to_have_attribute("aria-pressed", "false")
        button.click()
        expect(button).to_have_attribute("aria-pressed", "true")
        _wait_idle(page)


def _toggle_pill_off(page, label, value):
    _wait_idle(page)
    button = page.get_by_role("toolbar", name=label, exact=True).get_by_role(
        "button", name=value, exact=True
    )
    expect(button).to_have_attribute("aria-pressed", "true")
    button.click()
    expect(button).to_have_attribute("aria-pressed", "false")
    _wait_idle(page)


def _wait_idle(page):
    expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")


def _query(page, value):
    query = page.get_by_role("textbox", name="搜尋店家", exact=True)
    query.fill(value)
    query.press("Enter")
    return query


def _expect_count(page, count, available=None):
    available = count if available is None else available
    expect(page.get_by_text(f"{count} 間符合條件 · {available} 間可抽選", exact=True)).to_be_visible()


def _download_rows(page, button_name, destination):
    with page.expect_download() as event:
        page.get_by_role("button", name=button_name, exact=True).click()
    event.value.save_as(destination)
    workbook = load_workbook(destination, read_only=True)
    rows = list(workbook.active.values)
    workbook.close()
    return rows


def test_default_catalog_is_shared_and_random_recommendations_do_not_repeat(page):
    expect(page.get_by_text("FOODFLIX", exact=True)).to_have_count(0)
    expect(page.get_by_role("combobox")).to_have_count(0)
    expect(page.get_by_role("toolbar")).to_have_count(5)
    expect(page.get_by_role("toolbar", name="食物種類", exact=True).get_by_role("button")).to_have_count(25)
    search_bounds = page.get_by_role("textbox", name="搜尋店家", exact=True).bounding_box()
    filter_bounds = page.locator(".st-key-filters_panel").bounding_box()
    assert search_bounds is not None and filter_bounds is not None
    assert 0 <= search_bounds["y"] < filter_bounds["y"] < page.viewport_size["height"]
    for label in ("地點", "食物種類"):
        bounds = page.get_by_role("toolbar", name=label, exact=True).get_by_role("button").first.bounding_box()
        assert bounds is not None and 0 <= bounds["y"] < page.viewport_size["height"], bounds
    _expect_count(page, 175)
    expect(page.get_by_role("button", name="下載完整名單", exact=True)).to_be_visible()
    page.get_by_role("button", name="幫我決定這一餐", exact=True).click()
    result = page.locator(f"{RESULT} h2")
    expect(result).not_to_have_text(re.compile(r"^示範・"))
    previous = result.inner_text()
    assert previous != "郭董麻辣牛肉麵"
    for _ in range(3):
        page.get_by_role("button", name="再推薦一家", exact=True).click()
        expect(result).not_to_have_text(previous)
        previous = result.inner_text()
        assert previous != "郭董麻辣牛肉麵"
    page.locator("summary").filter(has_text="最近推薦").click()
    expect(page.get_by_role("heading", name="最近推薦", exact=True)).to_be_visible()


def test_actual_location_genre_price_and_occasion_filters_then_reset(page):
    _select_pills(page, "地點", ["公館"])
    _expect_count(page, 75)
    _select_pills(page, "食物種類", ["牛排"])
    _expect_count(page, 4)
    _select_pills(page, "價格等級", ["🪙"])
    _select_pills(page, "用餐情境", ["約會", "聚餐"])
    _expect_count(page, 1)
    page.get_by_role("button", name="幫我決定這一餐", exact=True).click()
    expect(page.locator(f"{RESULT} h2")).to_have_text("孫東寶牛排")
    expect(page.locator(RESULT)).to_contain_text("🪙 · NT$0–100")
    query = _query(page, "不存在的餐廳")
    _expect_count(page, 0)
    expect(page.get_by_role("button", name="幫我決定這一餐", exact=True)).to_be_disabled()
    page.get_by_role("button", name="全部取消", exact=True).click()
    _expect_count(page, 175)
    expect(query).to_have_value("")
    expect(page.get_by_role("toolbar", name="食物種類", exact=True).get_by_role("button", pressed=True)).to_have_count(0)
    expect(page.get_by_role("toolbar", name="價格等級", exact=True).get_by_role("button", pressed=True)).to_have_count(0)
    for label in ("地點", "用餐情境", "用餐節奏"):
        expect(page.get_by_role("toolbar", name=label, exact=True).get_by_role("button", pressed=True)).to_have_count(0)


def test_rich_import_requires_all_features_uses_named_maps_and_restores_defaults(page):
    _import_catalog(page)
    _select_pills(page, "地點", ["公館"])
    _select_pills(page, "食物種類", ["便當"])
    _select_pills(page, "價格等級", ["🪙🪙"])
    _select_pills(page, "用餐情境", ["一個人吃", "約會", "聚餐"])
    _select_pills(page, "用餐節奏", ["快速上菜", "慢慢享用"])
    _expect_count(page, 1)
    page.get_by_role("button", name="幫我決定這一餐", exact=True).click()
    expect(page.locator(f"{RESULT} h2")).to_have_text("測試旗標完整店")
    expect(page.locator(RESULT)).to_contain_text("測試學生優惠")
    link = page.get_by_role("link", name="在 Google 地圖查看", exact=True)
    expect(link).to_be_visible()
    query = parse_qs(urlparse(link.get_attribute("href")).query)["query"][0]
    assert "測試旗標完整店" in query and "公館" in query
    page.get_by_role("button", name="再推薦一家", exact=True).click()
    expect(page.locator(f"{RESULT} h2")).to_have_text("測試旗標完整店")
    page.get_by_role("button", name="恢復內建名單", exact=True).click()
    _expect_count(page, 175)
    expect(page.get_by_role("button", name="恢復內建名單", exact=True)).not_to_be_visible()
    expect(page.locator(RESULT)).not_to_be_visible()
    expect(page.get_by_role("toolbar", name="食物種類", exact=True).get_by_role("button", pressed=True)).to_have_count(0)


def test_invalid_import_preserves_the_current_custom_catalog(page):
    _import_catalog(page)
    dialog = _upload(page, _workbook([["錯誤欄位"], ["沒有必要表頭"]]), "錯誤欄位.xlsx")
    expect(dialog.get_by_text(re.compile("缺少必要欄位"))).to_be_visible()
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    _expect_count(page, 3)
    expect(page.get_by_text(re.compile(r"目前名單：.*測試餐廳\.xlsx"))).to_be_visible()


def test_page_reload_returns_to_original_bundled_catalog(page):
    _import_catalog(page)
    page.reload()
    _expect_count(page, 175)
    expect(page.get_by_role("button", name="恢復內建名單", exact=True)).not_to_be_visible()
    expect(page.get_by_role("button", name="下載完整名單", exact=True)).to_be_visible()


def test_full_source_template_and_filtered_downloads_are_real_workbooks(page, tmp_path):
    original_path = tmp_path / "food.xlsx"
    _download_rows(page, "下載完整名單", original_path)
    assert original_path.read_bytes() == (ROOT / "data" / "food.xlsx").read_bytes()
    workbook = load_workbook(original_path, read_only=True)
    source_rows = [row for row in workbook.active.values if row[0]]
    workbook.close()
    assert source_rows[0] == EXCEL_HEADERS
    assert len(source_rows) == 177

    page.get_by_role("button", name="匯入 Excel 名單", exact=True).click()
    expect(page.get_by_role("dialog")).to_be_visible()
    template = _download_rows(page, "下載 Excel 範本", tmp_path / "template.xlsx")
    assert template[0] == EXCEL_HEADERS
    assert len(template) == 3
    assert all(row[0].startswith("示範・") for row in template[1:])
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).not_to_be_visible()

    _select_pills(page, "地點", ["公館"])
    _expect_count(page, 75)
    page.get_by_text("查看全部符合條件的餐廳（75 間）", exact=True).click()
    rows = _download_rows(page, "匯出篩選名單", tmp_path / "filtered.xlsx")
    assert rows[0] == EXCEL_HEADERS
    assert len(rows) == 76
    assert all(row[1] == "Gongguan" for row in rows[1:])
    assert all(row[0] != "郭董麻辣牛肉麵" for row in rows[1:])
    assert all(row[3] is None or 1 <= row[3] <= 5 for row in rows[1:])


def test_closed_restaurant_is_visible_only_on_request_and_never_recommended(page):
    _query(page, "郭董麻辣牛肉麵")
    _expect_count(page, 0)
    page.get_by_text("更多選項", exact=True).click()
    checkbox = page.get_by_role("checkbox", name="包含已註記歇業店家", exact=True)
    page.get_by_text("包含已註記歇業店家", exact=True).click()
    expect(checkbox).to_be_checked()
    _expect_count(page, 1, available=0)
    expect(page.get_by_role("button", name="幫我決定這一餐", exact=True)).to_be_disabled()
    expect(page.get_by_text(re.compile("關門了")).first).to_be_visible()
    expect(page.locator(RESULT)).not_to_be_visible()
    page.get_by_role("button", name="全部取消", exact=True).click()
    _expect_count(page, 175)
    if not checkbox.is_visible():
        page.get_by_text("更多選項", exact=True).click()
    expect(checkbox).not_to_be_checked()


def test_multiple_pills_union_within_groups_and_toggle_off_without_dropdowns(page):
    content = _workbook([
        EXCEL_HEADERS,
        ["甲店", "Gongguan", "Bento", 1],
        ["乙店", "Shida", "Steak", 3],
        ["丙店", "Gongguan", "Steak", 2],
        ["丁店", "Liuzhangli", "Bento", 3],
        ["戊店", "Shida", "Cafe", 1],
        ["己店", "Gongguan", "Steak", 3],
    ])
    dialog = _upload(page, content, "多選名單.xlsx")
    expect(dialog).not_to_be_visible()
    _expect_count(page, 6)
    expect(page.get_by_role("combobox")).to_have_count(0)
    _select_pills(page, "地點", ["公館", "師大"])
    _expect_count(page, 5)
    _select_pills(page, "食物種類", ["便當", "牛排"])
    _expect_count(page, 4)
    _select_pills(page, "價格等級", ["🪙", "🪙🪙🪙"])
    _expect_count(page, 3)
    catalog = page.locator(".st-key-catalog_grid")
    for name in ("甲店", "乙店", "己店"):
        expect(catalog.get_by_role("heading", name=name, exact=True)).to_be_visible()
    for name in ("丙店", "丁店", "戊店"):
        expect(catalog.get_by_role("heading", name=name, exact=True)).to_have_count(0)

    _toggle_pill_off(page, "價格等級", "🪙")
    _expect_count(page, 2)
    _toggle_pill_off(page, "價格等級", "🪙🪙🪙")
    _expect_count(page, 4)
    page.get_by_role("button", name="全部取消", exact=True).click()
    _expect_count(page, 6)
    for label in ("地點", "食物種類", "價格等級", "用餐情境", "用餐節奏"):
        expect(page.get_by_role("toolbar", name=label, exact=True).get_by_role("button", pressed=True)).to_have_count(0)


def test_each_filter_group_has_select_all_and_cancel_buttons(page):
    groups = {
        "location_choices": ("地點", 8),
        "category_choices": ("食物種類", 25),
        "price_choices": ("價格等級", 5),
        "occasion_choice": ("用餐情境", 3),
        "pace_choice": ("用餐節奏", 2),
    }
    for key, (label, option_count) in groups.items():
        group = page.locator(f".st-key-group_{key}")
        group.get_by_role("button", name="全選", exact=True).click()
        selected = page.get_by_role("toolbar", name=label, exact=True).get_by_role("button", pressed=True)
        expect(selected).to_have_count(option_count)
        _wait_idle(page)
        group.get_by_role("button", name="取消", exact=True).click()
        expect(selected).to_have_count(0)
        _expect_count(page, 175)
    legend = page.get_by_role("list", name="金幣價格範圍說明", exact=True)
    for price_range in ("NT$0–100", "NT$100–200", "NT$200–300", "NT$300–500", "NT$500以上"):
        expect(legend).to_contain_text(price_range)


def test_all_catalog_pages_have_per_restaurant_comment_forms(page):
    previous = page.get_by_role("button", name="上一頁", exact=True)
    next_page = page.get_by_role("button", name="下一頁", exact=True)
    expect(previous).to_be_disabled()
    expect(page.get_by_role("heading", name="孫東寶牛排", exact=True)).to_be_visible()
    expect(page.get_by_test_id("stForm")).to_have_count(6)
    expect(page.get_by_role("textbox", name="評論內容", exact=True)).to_have_count(6)
    publish = page.get_by_role("button", name="發布評論", exact=True)
    expect(publish).to_have_count(6)
    for button in publish.all():
        expect(button).to_be_disabled()

    next_page.click()
    expect(page.get_by_role("heading", name="泰好吃泰國船麵", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="孫東寶牛排", exact=True)).to_have_count(0)
    expect(page.get_by_test_id("stForm")).to_have_count(6)
    expect(page.get_by_role("textbox", name="評論內容", exact=True)).to_have_count(6)
    expect(previous).to_be_enabled()
    previous.click()
    expect(page.get_by_role("heading", name="孫東寶牛排", exact=True)).to_be_visible()
    expect(previous).to_be_disabled()


def test_top_search_finds_names_outside_filters_and_closed_stores_before_the_catalog(page):
    _select_pills(page, "地點", ["師大"])
    _expect_count(page, 3)
    _query(page, "孫東寶牛排")
    results = page.locator(".st-key-search_results")
    expect(results.get_by_role("heading", name="孫東寶牛排", exact=True)).to_be_visible()
    expect(results.get_by_role("textbox", name="您的暱稱", exact=True)).to_be_visible()
    expect(results.get_by_role("textbox", name="評論內容", exact=True)).to_be_visible()
    expect(results.get_by_role("button", name="發布評論", exact=True)).to_be_disabled()
    _expect_count(page, 0)
    results_bounds = results.bounding_box()
    filter_bounds = page.locator(".st-key-filters_panel").bounding_box()
    assert results_bounds is not None and filter_bounds is not None
    assert results_bounds["y"] < filter_bounds["y"]

    _query(page, "郭董麻辣牛肉麵")
    expect(results.get_by_role("heading", name="郭董麻辣牛肉麵", exact=True)).to_be_visible()
    expect(results).to_contain_text("關門了")
    expect(results.get_by_role("textbox", name="評論內容", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="幫我決定這一餐", exact=True)).to_be_disabled()
    _query(page, "")
    expect(results).to_have_count(0)
    _expect_count(page, 3)
    page.get_by_role("button", name="全部取消", exact=True).click()
    _expect_count(page, 175)


def test_one_business_can_have_independent_search_recommendation_and_catalog_half_star_forms(page):
    _query(page, "孫東寶牛排")
    _expect_count(page, 1)
    results = page.locator(".st-key-search_results")
    expect(results.get_by_role("heading", name="孫東寶牛排", exact=True)).to_be_visible()
    page.get_by_role("button", name="幫我決定這一餐", exact=True).click()
    recommendation = page.locator(".st-key-pick_panel")
    expect(page.locator(f"{RESULT} h2")).to_have_text("孫東寶牛排")
    expect(page.get_by_test_id("stForm")).to_have_count(3)
    for context in (results, recommendation, page.locator(".st-key-catalog_grid")):
        expect(context.get_by_role("textbox", name="您的暱稱", exact=True)).to_be_visible()
        expect(context.get_by_role("textbox", name="評論內容", exact=True)).to_be_visible()
        expect(context.get_by_role("button", name="發布評論", exact=True)).to_be_disabled()
    rating = recommendation.get_by_role("slider")
    expect(rating).to_have_value("3")
    expect(rating).to_have_attribute("step", "0.5")
    rating.press("Home")
    rating.press("ArrowRight")
    expect(rating).to_have_value("1.5")
    expect(results.get_by_role("slider")).to_have_value("3")
    recommendation.get_by_role("textbox", name="評論內容", exact=True).fill("測試草稿，不會發布")
    expect(results.get_by_role("textbox", name="評論內容", exact=True)).to_have_value("")


def test_top_search_pages_expose_comment_forms_for_every_matching_store(page):
    _query(page, "牛排")
    results = page.locator(".st-key-search_results")
    expect(results.get_by_test_id("stForm")).to_have_count(3)
    expect(results.get_by_role("heading", name="孫東寶牛排", exact=True)).to_be_visible()
    previous = results.get_by_role("button", name="上一頁搜尋結果", exact=True)
    next_page = results.get_by_role("button", name="下一頁搜尋結果", exact=True)
    expect(previous).to_be_disabled()
    next_page.click()
    expect(results.get_by_role("heading", name="孫東寶牛排", exact=True)).to_have_count(0)
    expect(results.get_by_test_id("stForm")).to_have_count(3)
    expect(previous).to_be_enabled()
    previous.click()
    expect(results.get_by_role("heading", name="孫東寶牛排", exact=True)).to_be_visible()
    _query(page, "孫東寶牛排")
    expect(results.get_by_test_id("stForm")).to_have_count(1)
