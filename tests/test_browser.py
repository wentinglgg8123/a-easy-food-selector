"""Real Chromium checks for the Python website on desktop and mobile screens."""

from io import BytesIO
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from openpyxl import Workbook, load_workbook
from playwright.sync_api import expect, sync_playwright
import pytest

from food_picker.excel import EXCEL_HEADERS

pytestmark = pytest.mark.browser
ROOT = Path(__file__).resolve().parents[1]
APP_URL = "http://127.0.0.1:8501"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


def _workbook(rows) -> bytes:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _catalog_bytes() -> bytes:
    return _workbook([
        EXCEL_HEADERS,
        ["測試校園便當", "校內", "中式", 85, None, "校內測試地址", "測試用店家"],
        ["測試巷口麵店", "校外", "中式", 95, 1.2, "清大周邊測試地址", "測試用店家"],
        ["測試未填距離", "校外", "早餐", 60, None, "測試街 3 號", "待確認距離"],
        ["不應收錄的遠店", "校外", "日式", 150, 2.5, "遠方", "已超出範圍"],
    ])


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
    expect(page.get_by_text("已匯入 3 間餐廳，開飯囉！", exact=True)).to_be_visible()
    expect(page.get_by_text("3 間餐廳符合你的心情", exact=True)).to_be_visible()


def _select(page, label, value):
    combo = page.get_by_role("combobox", name=label, exact=True)
    combo.click()
    combo.press("ArrowDown")
    page.get_by_role("option", name=value, exact=True).click()


def test_random_recommendations_do_not_repeat_consecutively(page):
    expect(page.get_by_text("8 間虛構餐廳 · 匯入你的 Excel，換成真實美食", exact=True)).to_be_visible()
    page.get_by_role("button", name="幫我決定這一餐", exact=True).click()
    result = page.locator("section.recommendation h2")
    expect(result).to_have_text(re.compile(r"^示範・"))
    previous = result.inner_text()
    for _ in range(3):
        page.get_by_role("button", name="再抽一間，換個靈感", exact=True).click()
        expect(result).not_to_have_text(previous)
        previous = result.inner_text()
    expect(page.get_by_role("heading", name="剛剛的美食靈感", exact=True)).to_be_visible()
    assert 2 <= page.locator(".food-grid .food-card").count() <= 3


def test_filters_empty_search_and_reset(page):
    page.get_by_role("radiogroup", name="用餐範圍", exact=True).get_by_text("清大校內", exact=True).click()
    expect(page.get_by_text("4 間餐廳符合你的心情", exact=True)).to_be_visible()
    _select(page, "每人預算上限", "NT$ 100 以內")
    expect(page.get_by_text("3 間餐廳符合你的心情", exact=True)).to_be_visible()
    _select(page, "今天的口味", "日式")
    expect(page.get_by_text("0 間餐廳符合你的心情", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="幫我決定這一餐", exact=True)).to_be_disabled()
    expect(page.get_by_role("heading", name="這次條件有點挑嘴", exact=True)).to_be_visible()
    page.get_by_role("button", name="重設篩選", exact=True).click()
    expect(page.get_by_text("8 間餐廳符合你的心情", exact=True)).to_be_visible()
    query = page.get_by_role("textbox", name="搜尋一點靈感", exact=True)
    query.fill("不存在的餐廳")
    query.press("Enter")
    expect(page.get_by_text("0 間餐廳符合你的心情", exact=True)).to_be_visible()
    page.get_by_role("button", name="重設篩選", exact=True).click()
    expect(page.get_by_text("8 間餐廳符合你的心情", exact=True)).to_be_visible()
    expect(query).to_have_value("")
    expect(page.get_by_role("combobox", name="今天的口味", exact=True)).to_have_value("不挑食")
    expect(page.get_by_role("combobox", name="每人預算上限", exact=True)).to_have_value("不限預算")


def test_import_warnings_survive_widget_reruns_and_clear_restores_demo(page):
    _import_catalog(page)
    page.get_by_text("匯入提醒（2 項）", exact=True).click()
    expect(page.get_by_text(re.compile("校外餐廳超過 2 公里範圍"))).to_be_visible()
    expect(page.get_by_text(re.compile("校外餐廳未填距離，已匯入"))).to_be_visible()
    page.get_by_role("radiogroup", name="用餐範圍", exact=True).get_by_text("清大校內", exact=True).click()
    expect(page.get_by_text("1 間餐廳符合你的心情", exact=True)).to_be_visible()
    page.get_by_role("button", name="幫我決定這一餐", exact=True).click()
    expect(page.locator("section.recommendation h2")).to_have_text("測試校園便當")
    expect(page.get_by_role("link", name="在 Google 地圖查看", exact=True)).to_have_attribute(
        "href", re.compile(r"^https://www\.google\.com/maps/search/\?api=1&query=")
    )
    expect(page.get_by_text(re.compile(r"目前名單：.*測試餐廳\.xlsx"))).to_be_visible()
    page.get_by_role("button", name="清除並回到示範", exact=True).click()
    expect(page.get_by_text("8 間餐廳符合你的心情", exact=True)).to_be_visible()
    expect(page.get_by_text("已清除匯入資料，切回示範名單。", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="清除並回到示範", exact=True)).not_to_be_visible()
    expect(page.locator("section.recommendation")).not_to_be_visible()


def test_invalid_import_shows_error_and_preserves_existing_catalog(page):
    _import_catalog(page)
    dialog = _upload(page, _workbook([["錯誤欄位"], ["沒有必要表頭"]]), "錯誤欄位.xlsx")
    expect(dialog.get_by_text(re.compile("缺少必要欄位"))).to_be_visible()
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    expect(page.get_by_text("3 間餐廳符合你的心情", exact=True)).to_be_visible()
    expect(page.get_by_text(re.compile(r"目前名單：.*測試餐廳\.xlsx"))).to_be_visible()


def test_page_reload_starts_new_session_with_demo_catalog(page):
    _import_catalog(page)
    page.reload()
    expect(page.get_by_text("8 間虛構餐廳 · 匯入你的 Excel，換成真實美食", exact=True)).to_be_visible()
    expect(page.get_by_text("8 間餐廳符合你的心情", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="清除並回到示範", exact=True)).not_to_be_visible()


def test_template_and_filtered_catalog_download_are_real_workbooks(page, tmp_path):
    with page.expect_download() as event:
        page.get_by_role("button", name="下載 Excel 範本", exact=True).click()
    download = event.value
    assert download.suggested_filename == "食刻決定_餐廳名單範本.xlsx"
    template_path = tmp_path / "template.xlsx"
    download.save_as(template_path)
    workbook = load_workbook(template_path, read_only=True)
    rows = list(workbook.active.values)
    workbook.close()
    assert rows[0] == EXCEL_HEADERS
    assert len(rows) == 9
    assert all(row[0].startswith("示範・") for row in rows[1:])

    page.get_by_role("radiogroup", name="用餐範圍", exact=True).get_by_text("清大校內", exact=True).click()
    expect(page.get_by_text("4 間餐廳符合你的心情", exact=True)).to_be_visible()
    page.get_by_text("查看全部符合條件的餐廳（4 間）", exact=True).click()
    with page.expect_download() as event:
        page.get_by_role("button", name="匯出篩選名單", exact=True).click()
    export_path = tmp_path / "filtered.xlsx"
    event.value.save_as(export_path)
    workbook = load_workbook(export_path, read_only=True)
    rows = list(workbook.active.values)
    workbook.close()
    assert rows[0] == EXCEL_HEADERS
    assert len(rows) == 5
    assert all(row[1] == "清大校內" for row in rows[1:])


def test_single_candidate_remains_recommendable(page):
    dialog = _upload(page, _workbook([EXCEL_HEADERS, ["唯一測試店家", "校內", "中式", 80]]))
    expect(dialog).not_to_be_visible()
    expect(page.get_by_text("1 間餐廳符合你的心情", exact=True)).to_be_visible()
    page.get_by_role("button", name="幫我決定這一餐", exact=True).click()
    expect(page.locator("section.recommendation h2")).to_have_text("唯一測試店家")
    expect(page.get_by_text("目前只有 1 間符合條件，會推薦同一家", exact=True)).to_be_visible()
    page.get_by_role("button", name="再抽一間，換個靈感", exact=True).click()
    expect(page.locator("section.recommendation h2")).to_have_text("唯一測試店家")
