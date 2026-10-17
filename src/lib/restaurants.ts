export type Restaurant = {
  id: string;
  name: string;
  area: "campus" | "nearby";
  category: string;
  price: number | null;
  distance: number | null;
  address: string;
  note: string;
};

export type Filters = {
  area: "all" | "campus" | "nearby";
  category: string;
  maxPrice: number | null;
  query: string;
};

type Column =
  | "name"
  | "area"
  | "category"
  | "price"
  | "distance"
  | "address"
  | "note";

const MAX_DATA_ROWS = 5_000;
const normalise = (value: string) =>
  value.normalize("NFKC").trim().toLocaleLowerCase();
const normaliseHeader = (value: string) =>
  normalise(value).replace(/[\s_\-()/]/g, "");

const COLUMN_NAMES: Record<Column, string> = {
  name: "餐廳名稱",
  area: "區域",
  category: "類型",
  price: "均消",
  distance: "距離（公里）",
  address: "地址",
  note: "備註",
};

const COLUMN_ALIASES: Record<Column, string[]> = {
  name: [
    "餐廳名稱",
    "店家名稱",
    "餐廳",
    "店名",
    "名稱",
    "name",
    "restaurant name",
  ],
  area: [
    "區域",
    "地區",
    "區別",
    "校內/校外",
    "區域（校內/校外）",
    "area",
    "region",
  ],
  category: ["類型", "分類", "餐點類型", "料理類型", "category", "type"],
  price: [
    "均消",
    "均消（元）",
    "平均消費",
    "平均價格",
    "價格",
    "預算",
    "price",
  ],
  distance: [
    "距離（公里）",
    "距離（km）",
    "距離",
    "公里",
    "distance",
    "distance km",
  ],
  address: ["地址", "住址", "address"],
  note: ["備註", "說明", "note", "notes"],
};

const HEADER_COLUMNS = new Map(
  Object.entries(COLUMN_ALIASES).flatMap(([column, aliases]) =>
    aliases.map((alias) => [normaliseHeader(alias), column as Column] as const),
  ),
);

function isBlank(value: unknown): boolean {
  return (
    value === null ||
    value === undefined ||
    (typeof value === "string" && value.trim() === "")
  );
}

function textCell(value: unknown, column: Column): string {
  if (isBlank(value)) return "";
  if (typeof value !== "string" && typeof value !== "number") {
    throw new Error(
      `「${COLUMN_NAMES[column]}」格式無法辨識，請填入純文字，已略過`,
    );
  }
  if (typeof value === "number" && !Number.isFinite(value)) {
    throw new Error(`「${COLUMN_NAMES[column]}」格式無法辨識，已略過`);
  }
  return String(value).trim();
}

function numericCell(
  value: unknown,
  column: "price" | "distance",
): number | null {
  if (isBlank(value)) return null;
  let numericValue: number;
  if (typeof value === "number") {
    numericValue = value;
  } else if (typeof value === "string") {
    let cleaned = value.normalize("NFKC").trim();
    if (column === "price") {
      cleaned = cleaned
        .replace(/^(?:NT\$|NTD|TWD|\$)\s*/i, "")
        .replace(/\s*(?:元|NTD|TWD)$/i, "")
        .trim();
    } else {
      cleaned = cleaned.replace(/\s*(?:公里|km)$/i, "").trim();
    }
    // Grouping commas must be complete; ranges, formulas, and mixed units are not numbers.
    if (!/^(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)$/.test(cleaned)) {
      throw new Error(
        `「${COLUMN_NAMES[column]}」必須是非負數字，請勿填入範圍、公式或不明單位，已略過`,
      );
    }
    numericValue = Number(cleaned.replace(/,/g, ""));
  } else {
    throw new Error(
      `「${COLUMN_NAMES[column]}」必須是非負數字，請將公式轉為數值，已略過`,
    );
  }
  if (!Number.isFinite(numericValue) || numericValue < 0) {
    throw new Error(`「${COLUMN_NAMES[column]}」必須是有效的非負數字，已略過`);
  }
  return numericValue;
}

function parseArea(value: unknown): Restaurant["area"] {
  const raw = textCell(value, "area");
  const area = normalise(raw).replace(/[\s_\-()/]/g, "");
  const campus = [
    "校內",
    "學餐",
    "校內學餐",
    "清大校內",
    "清華校內",
    "清華大學校內",
    "國立清華大學校內",
    "campus",
    "oncampus",
  ];
  const nearby = [
    "校外",
    "周邊",
    "周圍",
    "附近",
    "校園周邊",
    "清大周邊",
    "清華周邊",
    "清華大學周邊",
    "校外2公里內",
    "周邊2公里內",
    "nearby",
    "offcampus",
  ];
  if (campus.includes(area)) return "campus";
  if (nearby.includes(area)) return "nearby";
  throw new Error("「區域」請填寫「校內」或「校外」，已略過");
}

function restaurantId(key: string): string {
  let hash = 2_166_136_261;
  for (let index = 0; index < key.length; index += 1) {
    hash = Math.imul(hash ^ key.charCodeAt(index), 16_777_619);
  }
  return `restaurant-${(hash >>> 0).toString(36)}`;
}

/** Read the first nonempty row as headers; warning row numbers match the Excel sheet. */
export function parseRestaurantRows(rows: unknown[][]): {
  restaurants: Restaurant[];
  warnings: string[];
} {
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error(
      "Excel 沒有資料。請在第一列加入「餐廳名稱」與「區域」，並至少填寫一間餐廳。",
    );
  }
  const headerIndex = rows.findIndex(
    (row) => Array.isArray(row) && row.some((cell) => !isBlank(cell)),
  );
  if (headerIndex < 0)
    throw new Error(
      "Excel 沒有資料。請加入「餐廳名稱」與「區域」欄位，以及至少一間餐廳。",
    );
  const dataRowCount = rows
    .slice(headerIndex + 1)
    .filter(
      (row) => !Array.isArray(row) || row.some((cell) => !isBlank(cell)),
    ).length;
  if (dataRowCount > MAX_DATA_ROWS) {
    throw new Error(
      `Excel 最多支援 ${MAX_DATA_ROWS.toLocaleString("en-US")} 筆餐廳資料，請分割檔案後重新匯入。`,
    );
  }

  const columns = new Map<Column, number>();
  rows[headerIndex].forEach((value, index) => {
    if (typeof value !== "string") return;
    const column = HEADER_COLUMNS.get(normaliseHeader(value));
    if (!column) return;
    if (columns.has(column))
      throw new Error(
        `欄位「${COLUMN_NAMES[column]}」出現多次，請保留一欄後重新匯入。`,
      );
    columns.set(column, index);
  });
  const missing = (["name", "area"] as const).filter(
    (column) => !columns.has(column),
  );
  if (missing.length) {
    throw new Error(
      `缺少必要欄位：${missing.map((column) => `「${COLUMN_NAMES[column]}」`).join("、")}。請將欄位名稱放在第一個有資料的列。`,
    );
  }

  const restaurants: Restaurant[] = [];
  const seen = new Set<string>();
  const warningRows = new Map<string, number[]>();
  const warn = (message: string, rowNumber: number) => {
    const matchingRows = warningRows.get(message) ?? [];
    matchingRows.push(rowNumber);
    warningRows.set(message, matchingRows);
  };

  for (let index = headerIndex + 1; index < rows.length; index += 1) {
    const row = rows[index];
    const rowNumber = index + 1;
    if (!Array.isArray(row)) {
      warn("資料列格式無法辨識，已略過", rowNumber);
      continue;
    }
    if (row.every(isBlank)) continue;
    const cell = (column: Column) => {
      const columnIndex = columns.get(column);
      return columnIndex === undefined ? undefined : row[columnIndex];
    };

    try {
      const name = textCell(cell("name"), "name");
      if (!name) throw new Error("缺少餐廳名稱，請補上名稱，已略過");
      const area = parseArea(cell("area"));
      const price = numericCell(cell("price"), "price");
      const distance = numericCell(cell("distance"), "distance");
      if (area === "nearby" && distance !== null && distance > 2) {
        throw new Error(
          "校外餐廳超過 2 公里範圍，請確認距離單位為公里，已略過",
        );
      }
      const address = textCell(cell("address"), "address");
      const category = textCell(cell("category"), "category") || "未分類";
      const note = textCell(cell("note"), "note");
      const key = JSON.stringify([normalise(name), normalise(address), area]);
      if (seen.has(key)) {
        warn("相同名稱、地址與區域的餐廳重複，已保留第一筆", rowNumber);
        continue;
      }
      seen.add(key);
      restaurants.push({
        id: restaurantId(key),
        name,
        area,
        category,
        price,
        distance,
        address,
        note,
      });
      if (area === "nearby" && distance === null) {
        warn(
          "校外餐廳未填距離，已匯入但尚未確認是否在 2 公里內；請補上「距離（公里）」",
          rowNumber,
        );
      }
    } catch (error) {
      warn(
        error instanceof Error ? error.message : "資料格式無法辨識，已略過",
        rowNumber,
      );
    }
  }

  const warnings = [...warningRows].map(([message, rowNumbers]) => {
    const refs = rowNumbers.slice(0, 12).join("、");
    const overflow =
      rowNumbers.length > 12 ? ` 等 ${rowNumbers.length} 列` : " 列";
    return `第 ${refs}${overflow}：${message}。`;
  });
  if (restaurants.length === 0) {
    throw new Error(
      `沒有可使用的餐廳資料。請至少填寫一間名稱與區域正確的餐廳。${warnings.slice(0, 3).join(" ")}`,
    );
  }
  return { restaurants, warnings };
}

export function filterRestaurants(
  restaurants: Restaurant[],
  filters: Filters,
): Restaurant[] {
  const query = normalise(filters.query);
  return restaurants.filter((restaurant) => {
    if (
      restaurant.area === "nearby" &&
      restaurant.distance !== null &&
      (restaurant.distance < 0 || restaurant.distance > 2)
    )
      return false;
    if (filters.area !== "all" && restaurant.area !== filters.area)
      return false;
    if (filters.category !== "all" && restaurant.category !== filters.category)
      return false;
    if (
      filters.maxPrice !== null &&
      (restaurant.price === null || restaurant.price > filters.maxPrice)
    )
      return false;
    return (
      !query ||
      [restaurant.name, restaurant.address, restaurant.category].some((value) =>
        normalise(value).includes(query),
      )
    );
  });
}

export function pickRestaurant(
  candidates: Restaurant[],
  previousId?: string,
  random: () => number = Math.random,
): Restaurant | null {
  if (candidates.length === 0) return null;
  const alternatives =
    candidates.length >= 2
      ? candidates.filter((restaurant) => restaurant.id !== previousId)
      : candidates;
  const pool = alternatives.length ? alternatives : candidates;
  const value = random();
  const index = Number.isFinite(value)
    ? Math.max(0, Math.min(pool.length - 1, Math.floor(value * pool.length)))
    : 0;
  return pool[index];
}

const DEMO_NOTE = "此為示範資料，非真實店家名單";

export const DEMO_RESTAURANTS: Restaurant[] = [
  {
    id: "demo-campus-noodles",
    name: "示範・校園麵食",
    area: "campus",
    category: "中式",
    price: 85,
    distance: null,
    address: "清華大學校內（示範位置）",
    note: DEMO_NOTE,
  },
  {
    id: "demo-campus-rice",
    name: "示範・校園日式食堂",
    area: "campus",
    category: "日式",
    price: 120,
    distance: null,
    address: "清華大學校內（示範位置）",
    note: DEMO_NOTE,
  },
  {
    id: "demo-campus-breakfast",
    name: "示範・校園早午餐",
    area: "campus",
    category: "早餐",
    price: 60,
    distance: null,
    address: "清華大學校內（示範位置）",
    note: DEMO_NOTE,
  },
  {
    id: "demo-campus-salad",
    name: "示範・校園輕食",
    area: "campus",
    category: "輕食",
    price: 95,
    distance: null,
    address: "清華大學校內（示範位置）",
    note: DEMO_NOTE,
  },
  {
    id: "demo-nearby-dumplings",
    name: "示範・巷口水餃",
    area: "nearby",
    category: "中式",
    price: 100,
    distance: 0.6,
    address: "清華大學周邊（示範位置）",
    note: DEMO_NOTE,
  },
  {
    id: "demo-nearby-japanese",
    name: "示範・街角日式小館",
    area: "nearby",
    category: "日式",
    price: 180,
    distance: 1.2,
    address: "清華大學周邊（示範位置）",
    note: DEMO_NOTE,
  },
  {
    id: "demo-nearby-breakfast",
    name: "示範・晨光早餐",
    area: "nearby",
    category: "早餐",
    price: 70,
    distance: 0.8,
    address: "清華大學周邊（示範位置）",
    note: DEMO_NOTE,
  },
  {
    id: "demo-nearby-salad",
    name: "示範・午後輕食",
    area: "nearby",
    category: "輕食",
    price: 150,
    distance: 1.6,
    address: "清華大學周邊（示範位置）",
    note: DEMO_NOTE,
  },
];
