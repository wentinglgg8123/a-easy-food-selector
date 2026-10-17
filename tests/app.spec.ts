import { test as base, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import writeXlsxFile from "write-excel-file/node";
import { readSheet } from "read-excel-file/node";

const HEADERS = [
  "餐廳名稱",
  "區域",
  "類型",
  "均消",
  "距離（公里）",
  "地址",
  "備註",
];
const IMPORT_ROWS = [
  HEADERS,
  ["測試校內麵食", "清大校內", "中式", 80, 0, "新竹市測試路一號", "測試資料"],
  [
    "測試巷口水餃",
    "校園周邊",
    "中式",
    140,
    1.2,
    "新竹市測試路二號",
    "測試資料",
  ],
  ["測試遠方餐廳", "校園周邊", "日式", 200, 3, "新竹市測試路三號", "超出範圍"],
  [
    "測試待查餐廳",
    "校園周邊",
    "輕食",
    90,
    null,
    "新竹市測試路四號",
    "距離待查",
  ],
];

const test = base.extend<{ pageErrors: string[] }>({
  pageErrors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await use(errors);
      expect.soft(errors, "頁面不應產生未處理的 JavaScript 錯誤").toEqual([]);
    },
    { auto: true },
  ],
});

async function openImport(page: Page) {
  await page
    .getByRole("button", { name: "匯入 Excel 名單", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "帶上你的美食名單" }),
  ).toBeVisible();
}

async function expectNoHorizontalOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 1);
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("可以隨機推薦，連續抽選不會重複上一間", async ({ page }) => {
  const recommendation = page.getByRole("region", { name: "隨機餐廳推薦" });
  await expect(page.getByRole("heading", { level: 1 })).toContainText("今天，");
  await expect(page.locator(".filter-count")).toContainText("8 間餐廳");
  await recommendation.getByRole("button", { name: "幫我決定這一餐" }).click();
  const result = recommendation.locator(".restaurant-result h2");
  await expect(result).toBeVisible();
  const previousName = await result.textContent();
  await expect(
    recommendation.getByText("虛構示範", { exact: true }),
  ).toBeVisible();
  await recommendation
    .getByRole("button", { name: "再抽一間，換個靈感" })
    .click();
  await expect(result).toBeVisible();
  await expect(result).not.toHaveText(previousName || "");
});

test("區域、類型、預算與搜尋篩選可以顯示空結果並重設", async ({ page }) => {
  const filters = page.getByRole("complementary");
  await filters.getByRole("button", { name: "清大校內", exact: true }).click();
  await expect(page.locator(".filter-count")).toContainText("4 間餐廳");
  await filters.getByRole("button", { name: "輕食", exact: true }).click();
  await expect(page.locator(".filter-count")).toContainText("1 間餐廳");
  await page.getByLabel("每人預算上限").selectOption("100");
  await expect(page.locator(".restaurant-grid")).toContainText(
    "示範・校園輕食",
  );
  await page.getByLabel("搜尋一點靈感").fill("不會存在的餐廳關鍵字");
  await expect(
    page.getByRole("heading", { name: "這次條件有點挑嘴" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "幫我決定這一餐" }),
  ).toBeDisabled();
  await expect(page.locator(".filter-count")).toContainText("0 間餐廳");
  await filters.getByRole("button", { name: "重設", exact: true }).click();
  await expect(page.locator(".filter-count")).toContainText("8 間餐廳");
  await expect(page.getByLabel("搜尋一點靈感")).toHaveValue("");
  await expect(page.getByLabel("每人預算上限")).toHaveValue("all");
});

test("匯入首張工作表、提示距離問題、保存名單並可清除", async ({
  page,
}, testInfo) => {
  const workbookPath = testInfo.outputPath("restaurants.xlsx");
  await writeXlsxFile([
    { sheet: "餐廳名單", data: IMPORT_ROWS },
    {
      sheet: "其他工作表",
      data: [HEADERS, ["第二張不應匯入", "清大校內", "早餐", 50, 0, "", ""]],
    },
  ]).toFile(workbookPath);

  await openImport(page);
  await page.locator("#excel-file").setInputFiles(workbookPath);
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByRole("status")).toContainText("已匯入 3 間餐廳");
  const source = page.getByRole("region", { name: "目前的餐廳名單" });
  await expect(source).toContainText("restaurants.xlsx");
  await expect(page.locator(".filter-count")).toContainText("3 間餐廳");
  await expect(page.locator(".restaurant-grid")).toContainText("測試校內麵食");
  await expect(page.locator(".restaurant-grid")).toContainText("測試巷口水餃");
  await expect(page.locator(".restaurant-grid")).toContainText("測試待查餐廳");
  await expect(page.getByText("測試遠方餐廳", { exact: true })).toHaveCount(0);
  await expect(page.getByText("第二張不應匯入", { exact: true })).toHaveCount(
    0,
  );
  await page.locator(".import-warnings summary").click();
  await expect(page.locator(".import-warnings")).toContainText(
    "超過 2 公里範圍",
  );
  await expect(page.locator(".import-warnings")).toContainText(
    "校外餐廳未填距離",
  );

  await page.getByLabel("搜尋一點靈感").fill("測試待查餐廳");
  await page.getByRole("button", { name: "幫我決定這一餐" }).click();
  const recommendation = page.getByRole("region", { name: "隨機餐廳推薦" });
  await expect(
    recommendation.getByRole("heading", { name: "測試待查餐廳" }),
  ).toBeVisible();
  await expect(
    recommendation.getByText("距離未驗證", { exact: true }),
  ).toBeVisible();
  const mapLink = recommendation.getByRole("link", {
    name: "在 Google 地圖查看",
  });
  await expect(mapLink).toHaveAttribute(
    "href",
    `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent("測試待查餐廳 新竹市測試路四號")}`,
  );
  await expect(mapLink).toHaveAttribute("target", "_blank");

  await page.reload();
  await expect(source).toContainText("restaurants.xlsx");
  await expect(page.locator(".filter-count")).toContainText("3 間餐廳");
  await source.getByRole("button", { name: "清除並回到示範" }).click();
  await expect(source).toContainText("先用示範名單，試試手氣");
  await expect(page.locator(".filter-count")).toContainText("8 間餐廳");
  await page.reload();
  await expect(source).toContainText("先用示範名單，試試手氣");
  await expect(page.locator(".filter-count")).toContainText("8 間餐廳");
});

test("無效 Excel 與缺少必要欄位會顯示錯誤並保留原名單", async ({
  page,
}, testInfo) => {
  await openImport(page);
  await page.locator("#excel-file").setInputFiles({
    name: "invalid.xlsx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: Buffer.from("This is not an Excel workbook."),
  });
  await expect(page.getByRole("alert")).toContainText("無法讀取 Excel");

  const invalidHeadersPath = testInfo.outputPath("missing-headers.xlsx");
  await writeXlsxFile([
    ["錯誤欄位", "區域"],
    ["測試餐廳", "清大校內"],
  ]).toFile(invalidHeadersPath);
  await page.locator("#excel-file").setInputFiles(invalidHeadersPath);
  await expect(page.getByRole("alert")).toContainText("缺少必要欄位");
  await expect(page.getByRole("alert")).toContainText("餐廳名稱");
  await page.getByRole("button", { name: "關閉匯入視窗" }).click();
  await expect(
    page.getByRole("region", { name: "目前的餐廳名單" }),
  ).toContainText("先用示範名單，試試手氣");
  await expect(page.locator(".filter-count")).toContainText("8 間餐廳");
});

test("可以下載含完整欄位與八筆虛構資料的 Excel 範本", async ({
  page,
}, testInfo) => {
  const downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "下載 Excel 範本", exact: true })
    .click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("食刻決定_餐廳名單範本.xlsx");
  const workbookPath = testInfo.outputPath("downloaded-template.xlsx");
  await download.saveAs(workbookPath);
  const rows = await readSheet(workbookPath, 1);
  expect(rows[0]).toEqual(HEADERS);
  expect(rows).toHaveLength(9);
  for (const row of rows.slice(1)) {
    expect(row[0]).toMatch(/^示範・/);
    expect(row[6]).toBe("此為示範資料，非真實店家名單");
  }
});

test("首頁與匯入視窗符合 WCAG A、AA 自動檢查", async ({ page }) => {
  const homepage = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(homepage.violations).toEqual([]);
  await openImport(page);
  const dialog = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(dialog.violations).toEqual([]);
});

test("首頁與匯入視窗沒有水平溢出", async ({ page }) => {
  await expectNoHorizontalOverflow(page);
  await openImport(page);
  await expectNoHorizontalOverflow(page);
});
