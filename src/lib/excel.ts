import { parseRestaurantRows, type Restaurant } from "./restaurants";

export const EXCEL_HEADERS = [
  "餐廳名稱",
  "區域",
  "類型",
  "均消",
  "距離（公里）",
  "地址",
  "備註",
];

export function restaurantRows(restaurants: Restaurant[]): unknown[][] {
  return [
    EXCEL_HEADERS,
    ...restaurants.map((r) => [
      r.name,
      r.area === "campus" ? "清大校內" : "校園周邊",
      r.category,
      r.price,
      r.distance,
      r.address,
      r.note,
    ]),
  ];
}

export async function importExcel(file: File) {
  if (!file.name.toLowerCase().endsWith(".xlsx"))
    throw new Error("請選擇 .xlsx 格式；舊版 .xls 請先以 Excel 另存為 .xlsx。");
  if (file.size > 5 * 1024 * 1024)
    throw new Error("檔案超過 5 MB，請刪除不需要的工作表或圖片後重試。");
  if (!file.size) throw new Error("檔案是空的，請重新選擇。");
  const { readSheet } = await import("read-excel-file/browser");
  let rows: unknown[][];
  try {
    rows = await readSheet(file, 1);
  } catch {
    throw new Error(
      "無法讀取 Excel，請確認檔案未加密，並另存為有效的 .xlsx 格式。",
    );
  }
  return parseRestaurantRows(rows);
}

export async function downloadTemplate(restaurants: Restaurant[]) {
  const { default: writeXlsxFile } = await import("write-excel-file/browser");
  const data = restaurantRows(restaurants).map((row, i) =>
    row.map((value) => ({
      value: value as string | number | undefined,
      ...(i === 0
        ? { fontWeight: "bold" as const, backgroundColor: "#E5EBDD" }
        : {}),
    })),
  );
  await writeXlsxFile(data, {
    columns: [
      { width: 25 },
      { width: 16 },
      { width: 12 },
      { width: 12 },
      { width: 16 },
      { width: 36 },
      { width: 52 },
    ],
  }).toFile("食刻決定_餐廳名單範本.xlsx");
}
