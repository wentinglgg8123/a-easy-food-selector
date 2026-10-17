import { describe, expect, it, vi } from "vitest";
import {
  DEMO_RESTAURANTS,
  filterRestaurants,
  parseRestaurantRows,
  pickRestaurant,
  type Filters,
} from "./restaurants";

const HEADERS = [
  "餐廳名稱",
  "區域",
  "類型",
  "均消",
  "距離（公里）",
  "地址",
  "備註",
];
const ALL: Filters = {
  area: "all",
  category: "all",
  maxPrice: null,
  query: "",
};

describe("parseRestaurantRows", () => {
  it("reads Excel rows, accepted currency formats, and preserves zero", () => {
    const { restaurants, warnings } = parseRestaurantRows([
      HEADERS,
      ["校園麵店", "校內", "中式", "$120", "", "校內", ""],
      ["周邊食堂", "校外", "日式", "NT$120", "2 公里", "門口", "測試"],
      ["早餐店", "附近", "早餐", "120 元", "0.5 km", "", ""],
      ["活動餐點", "campus", "", 0, 0, "", ""],
    ]);
    expect(restaurants).toHaveLength(4);
    expect(restaurants.map(({ price }) => price)).toEqual([120, 120, 120, 0]);
    expect(restaurants.map(({ distance }) => distance)).toEqual([
      null,
      2,
      0.5,
      0,
    ]);
    expect(restaurants[3].category).toBe("未分類");
    expect(warnings).toEqual([]);
  });

  it("supports aliases, reordered columns, blank leading rows, and case-insensitive English headers", () => {
    const result = parseRestaurantRows([
      [],
      ["備註", "均消（元）", "區域（校內／校外）", "店名", "DISTANCE_KM"],
      ["測試", "NT$1,200", "校外（2 公里內）", "測試餐廳", "1.8"],
    ]);
    expect(result.restaurants[0]).toMatchObject({
      name: "測試餐廳",
      area: "nearby",
      price: 1200,
      distance: 1.8,
      note: "測試",
    });
  });

  it("rejects missing and duplicated required headers with actionable errors", () => {
    expect(() => parseRestaurantRows([["店名"], ["測試"]])).toThrow(
      "缺少必要欄位：「區域」",
    );
    expect(() =>
      parseRestaurantRows([
        ["店名", "餐廳名稱", "區域"],
        ["一", "二", "校內"],
      ]),
    ).toThrow("出現多次");
    expect(() => parseRestaurantRows([])).toThrow("Excel 沒有資料");
    expect(() => parseRestaurantRows([[], ["  "]])).toThrow("Excel 沒有資料");
  });

  it("skips invalid rows, aggregates equivalent warnings, and includes Excel row numbers", () => {
    const { restaurants, warnings } = parseRestaurantRows([
      HEADERS,
      ["有效資料", "校內", "", 80],
      ["", "校內"],
      ["", "校外"],
      ["無效地區", "台北"],
      ["負數價格", "校內", "", -1],
      ["負數距離", "校外", "", "", "-0.5"],
      ["太遠", "校外", "", 80, 2.01],
    ]);
    expect(restaurants.map(({ name }) => name)).toEqual(["有效資料"]);
    expect(warnings).toHaveLength(5);
    expect(
      warnings.some(
        (warning) =>
          warning.includes("第 3、4 列") && warning.includes("缺少餐廳名稱"),
      ),
    ).toBe(true);
    expect(
      warnings.some(
        (warning) =>
          warning.includes("第 8 列") && warning.includes("超過 2 公里"),
      ),
    ).toBe(true);
  });

  it("does not silently convert ranges, malformed grouping, formulas, booleans, or objects", () => {
    const invalidValues = [
      "120–150",
      "約 100",
      "12,00",
      ".5.5",
      "=1+1",
      true,
      { f: "1+1", v: 2 },
      Infinity,
      NaN,
    ];
    const { restaurants, warnings } = parseRestaurantRows([
      HEADERS,
      ["有效資料", "校內", "", 100],
      ...invalidValues.map((value, index) => [
        `無效 ${index}`,
        "校內",
        "",
        value,
      ]),
    ]);
    expect(restaurants).toHaveLength(1);
    expect(warnings.join(" ")).toContain("均消");
    expect(warnings.join(" ")).toContain("公式");
  });

  it("rejects invalid text cell objects without converting them to object strings", () => {
    const { restaurants, warnings } = parseRestaurantRows([
      HEADERS,
      ["有效資料", "校內"],
      [{ f: "A1" }, "校內"],
      ["錯誤地址", "校內", "", "", "", { value: "地址" }],
    ]);
    expect(restaurants).toHaveLength(1);
    expect(warnings.join(" ")).toContain("純文字");
  });

  it("retains nearby restaurants with unknown distances and warns that the range is unverified", () => {
    const { restaurants, warnings } = parseRestaurantRows([
      HEADERS,
      ["距離未知", "校外", "中式", "", ""],
    ]);
    expect(restaurants[0].distance).toBeNull();
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain("尚未確認是否在 2 公里內");
  });

  it("deduplicates matching names, addresses, and areas while preserving separate branches", () => {
    const { restaurants, warnings } = parseRestaurantRows([
      HEADERS,
      [" Example ", "校內", "", "", "", "地址 A"],
      ["example", "校內", "", "", "", "地址 A"],
      ["Example", "校內", "", "", "", "地址 B"],
      ["Example", "校外", "", "", 1, "地址 A"],
    ]);
    expect(restaurants).toHaveLength(3);
    expect(new Set(restaurants.map(({ id }) => id)).size).toBe(3);
    expect(warnings.join(" ")).toContain("已保留第一筆");
  });

  it("fails clearly when no valid rows remain or the file exceeds 5,000 data rows", () => {
    expect(() => parseRestaurantRows([HEADERS, ["", "校內"]])).toThrow(
      "沒有可使用的餐廳資料",
    );
    expect(() => parseRestaurantRows([HEADERS])).toThrow("至少填寫一間");
    expect(() =>
      parseRestaurantRows([
        HEADERS,
        ...Array.from({ length: 5001 }, () => ["測試", "校內"]),
      ]),
    ).toThrow("5,000");
  });

  it("counts actual data rows toward the limit and permits blank rows around 5,000 records", () => {
    const rows = [
      [],
      [],
      HEADERS,
      ...Array.from({ length: 5000 }, (_, index) => [`餐廳 ${index}`, "校內"]),
      [],
      [],
    ];
    expect(parseRestaurantRows(rows).restaurants).toHaveLength(5000);
  });
});

describe("filterRestaurants", () => {
  it("combines area, category, budget, and text filters", () => {
    const results = filterRestaurants(DEMO_RESTAURANTS, {
      area: "campus",
      category: "中式",
      maxPrice: 100,
      query: "麵",
    });
    expect(results.map(({ id }) => id)).toEqual(["demo-campus-noodles"]);
    expect(
      filterRestaurants(DEMO_RESTAURANTS, { ...ALL, query: "清華大學周邊" }),
    ).toHaveLength(4);
    expect(
      filterRestaurants(DEMO_RESTAURANTS, { ...ALL, query: " 日式 " }),
    ).toHaveLength(2);
  });

  it("excludes unknown prices when a budget is set, including a zero budget", () => {
    const restaurants = [
      { ...DEMO_RESTAURANTS[0], id: "unknown", price: null },
      { ...DEMO_RESTAURANTS[0], id: "free", price: 0 },
    ];
    expect(filterRestaurants(restaurants, ALL)).toHaveLength(2);
    expect(
      filterRestaurants(restaurants, { ...ALL, maxPrice: 0 }).map(
        ({ id }) => id,
      ),
    ).toEqual(["free"]);
  });

  it("excludes nearby places beyond 2 km while keeping unknown distances and campus restaurants", () => {
    const restaurants = [
      { ...DEMO_RESTAURANTS[0], id: "campus", distance: 3 },
      { ...DEMO_RESTAURANTS[4], id: "inside", distance: 2 },
      { ...DEMO_RESTAURANTS[4], id: "outside", distance: 2.001 },
      { ...DEMO_RESTAURANTS[4], id: "unknown", distance: null },
      { ...DEMO_RESTAURANTS[4], id: "negative", distance: -1 },
    ];
    expect(filterRestaurants(restaurants, ALL).map(({ id }) => id)).toEqual([
      "campus",
      "inside",
      "unknown",
    ]);
  });
});

describe("pickRestaurant", () => {
  it("returns null for an empty candidate list without calling the random generator", () => {
    const random = vi.fn();
    expect(pickRestaurant([], undefined, random)).toBeNull();
    expect(random).not.toHaveBeenCalled();
  });

  it("avoids the previous restaurant when alternatives exist and permits a single candidate", () => {
    expect(
      pickRestaurant(
        DEMO_RESTAURANTS.slice(0, 2),
        DEMO_RESTAURANTS[0].id,
        () => 0,
      )?.id,
    ).toBe(DEMO_RESTAURANTS[1].id);
    expect(
      pickRestaurant([DEMO_RESTAURANTS[0]], DEMO_RESTAURANTS[0].id, () => 0)
        ?.id,
    ).toBe(DEMO_RESTAURANTS[0].id);
  });

  it("selects both ends of the candidate pool and handles an invalid random result safely", () => {
    expect(pickRestaurant(DEMO_RESTAURANTS, undefined, () => 0)).toBe(
      DEMO_RESTAURANTS[0],
    );
    expect(pickRestaurant(DEMO_RESTAURANTS, undefined, () => 0.999)).toBe(
      DEMO_RESTAURANTS.at(-1),
    );
    expect(pickRestaurant(DEMO_RESTAURANTS, undefined, () => 1)).toBe(
      DEMO_RESTAURANTS.at(-1),
    );
    expect(pickRestaurant(DEMO_RESTAURANTS, undefined, () => NaN)).toBe(
      DEMO_RESTAURANTS[0],
    );
  });
});

describe("demo data", () => {
  it("clearly labels all eight fictional restaurants and limits nearby examples to 2 km", () => {
    expect(DEMO_RESTAURANTS).toHaveLength(8);
    expect(
      DEMO_RESTAURANTS.filter(({ area }) => area === "campus"),
    ).toHaveLength(4);
    expect(
      DEMO_RESTAURANTS.every(
        ({ name, note }) =>
          name.startsWith("示範・") && note === "此為示範資料，非真實店家名單",
      ),
    ).toBe(true);
    expect(
      DEMO_RESTAURANTS.filter(({ area }) => area === "nearby").every(
        ({ distance }) => distance !== null && distance <= 2,
      ),
    ).toBe(true);
  });
});
