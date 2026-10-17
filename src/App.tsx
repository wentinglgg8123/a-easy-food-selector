import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronDown,
  Coffee,
  Dice5,
  FileSpreadsheet,
  Heart,
  Info,
  Leaf,
  ListFilter,
  MapPin,
  RotateCcw,
  Search,
  ShieldCheck,
  Shuffle,
  SlidersHorizontal,
  Sparkles,
  Upload,
  Utensils,
  UtensilsCrossed,
  Wallet,
  X,
} from "lucide-react";
import FoodIllustration from "./FoodIllustration";
import {
  DEMO_RESTAURANTS,
  filterRestaurants,
  parseRestaurantRows,
  pickRestaurant,
  type Filters,
  type Restaurant,
} from "./lib/restaurants";
import { downloadTemplate, importExcel, restaurantRows } from "./lib/excel";

const STORAGE_KEY = "nthu-food-picker-v1";
const DEFAULT_FILTERS: Filters = {
  area: "all",
  category: "all",
  maxPrice: null,
  query: "",
};
type Dataset = { restaurants: Restaurant[]; filename: string | null };

function loadDataset(): Dataset {
  try {
    const saved = JSON.parse(
      localStorage.getItem(STORAGE_KEY) || "null",
    ) as Dataset | null;
    if (
      saved &&
      Array.isArray(saved.restaurants) &&
      saved.restaurants.length <= 5000 &&
      typeof saved.filename === "string"
    ) {
      return {
        restaurants: parseRestaurantRows(restaurantRows(saved.restaurants))
          .restaurants,
        filename: saved.filename,
      };
    }
  } catch {
    /* A damaged or unavailable browser cache falls back to the demo. */
  }
  return { restaurants: DEMO_RESTAURANTS, filename: null };
}

function priceLabel(value: number | null) {
  return value === null ? "均消未提供" : `NT$ ${value}`;
}
function areaLabel(r: Restaurant) {
  return r.area === "campus" ? "清大校內" : "校園周邊";
}
function mapUrl(r: Restaurant) {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${r.name} ${r.address || "新竹 清華大學"}`)}`;
}

export default function App() {
  const [dataset, setDataset] = useState(loadDataset);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [selected, setSelected] = useState<Restaurant | null>(null);
  const [history, setHistory] = useState<Restaurant[]>([]);
  const [picking, setPicking] = useState(false);
  const [modal, setModal] = useState(false);
  const [importing, setImporting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [downloading, setDownloading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const candidates = useMemo(
    () => filterRestaurants(dataset.restaurants, filters),
    [dataset, filters],
  );
  const categories = useMemo(
    () => [...new Set(dataset.restaurants.map((r) => r.category))].sort(),
    [dataset],
  );
  const isDemo = dataset.filename === null;
  const activeFilters =
    (filters.area !== "all" ? 1 : 0) +
    (filters.category !== "all" ? 1 : 0) +
    (filters.maxPrice !== null ? 1 : 0) +
    (filters.query ? 1 : 0);
  const current =
    selected && candidates.some((r) => r.id === selected.id) ? selected : null;

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );
  useEffect(() => {
    if (modal && !dialogRef.current?.open) dialogRef.current?.showModal();
    if (!modal && dialogRef.current?.open) dialogRef.current?.close();
  }, [modal]);

  function changeFilter<K extends keyof Filters>(key: K, value: Filters[K]) {
    if (timerRef.current) clearTimeout(timerRef.current);
    setPicking(false);
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  function choose() {
    if (!candidates.length || picking) return;
    setPicking(true);
    timerRef.current = setTimeout(
      () => {
        const result = pickRestaurant(candidates, selected?.id);
        setSelected(result);
        if (result)
          setHistory((prev) =>
            [result, ...prev.filter((r) => r.id !== result.id)].slice(0, 3),
          );
        setPicking(false);
      },
      window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 520,
    );
  }

  function resetFilters() {
    if (timerRef.current) clearTimeout(timerRef.current);
    setPicking(false);
    setFilters(DEFAULT_FILTERS);
  }

  async function handleFile(file?: File) {
    if (!file || importing) return;
    setError("");
    setImporting(true);
    try {
      const result = await importExcel(file);
      const next = { restaurants: result.restaurants, filename: file.name };
      if (timerRef.current) clearTimeout(timerRef.current);
      setDataset(next);
      setSelected(null);
      setHistory([]);
      setPicking(false);
      setFilters(DEFAULT_FILTERS);
      setWarnings(result.warnings);
      setModal(false);
      let message = `已匯入 ${result.restaurants.length} 間餐廳，開飯囉！`;
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        message += " 瀏覽器無法儲存名單，重新整理後請再次匯入。";
      }
      setNotice(message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "匯入失敗，請檢查檔案格式。");
    } finally {
      setImporting(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function template() {
    setDownloading(true);
    try {
      await downloadTemplate(DEMO_RESTAURANTS);
    } catch {
      setNotice("範本下載失敗，請稍後再試。");
    } finally {
      setDownloading(false);
    }
  }

  function restoreDemo() {
    if (timerRef.current) clearTimeout(timerRef.current);
    setPicking(false);
    let message = "已切回示範名單。";
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      message += " 瀏覽器無法清除儲存資料，請至瀏覽器設定清除本站資料。";
    }
    setDataset({ restaurants: DEMO_RESTAURANTS, filename: null });
    setSelected(null);
    setHistory([]);
    setFilters(DEFAULT_FILTERS);
    setWarnings([]);
    setNotice(message);
  }

  return (
    <>
      <header className="site-header">
        <a className="brand" href="#" aria-label="食刻決定首頁">
          <span className="brand-icon">
            <UtensilsCrossed size={23} strokeWidth={1.8} />
          </span>
          <span>
            食刻決定<span className="brand-dot">.</span>
          </span>
        </a>
        <span className="header-tag">給清大人的美食靈感</span>
        <button
          className="button upload-button"
          onClick={() => {
            setError("");
            setModal(true);
          }}
        >
          <Upload size={16} />
          <span>匯入 Excel 名單</span>
        </button>
      </header>

      <main className="page-shell">
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow">
              <span /> NTHU FOOD PICKER
            </div>
            <h1>
              今天，
              <br className="mobile-break" />
              吃點
              <span className="title-accent">
                什麼？
                <svg viewBox="0 0 185 15" aria-hidden="true">
                  <path
                    d="M4 10Q84 0 180 6"
                    stroke="currentColor"
                    strokeWidth="5"
                    fill="none"
                    strokeLinecap="round"
                  />
                </svg>
              </span>
            </h1>
            <p>
              把選擇困難交給我們，把好胃口留給美食。
              <br />
              從清大校內到周邊 2 公里，下一餐交給一點驚喜。
            </p>
            <div className="hero-tags">
              <span>
                <MapPin size={13} />
                清大生活圈
              </span>
              <span>
                <Heart size={13} />
                每一餐，都有新靈感
              </span>
            </div>
          </div>
        <div className="hero-art" aria-hidden="true">
            <span className="art-label top-label">GOOD FOOD, GOOD MOOD</span>
            <FoodIllustration />
            <span className="handwritten">
              好好吃飯，天天開心！
              <svg viewBox="0 0 44 28" aria-hidden="true">
                <path
                  d="M2 5q13 22 37 10m-10-4 11 4-5 10"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  fill="none"
                />
              </svg>
            </span>
          </div>
        </section>

        {notice && (
          <div className="notice" role="status">
            <Check size={17} />
            <span>{notice}</span>
            <button
              className="icon-button"
              aria-label="關閉提示"
              onClick={() => setNotice("")}
            >
              <X size={15} />
            </button>
          </div>
        )}
        <section className="source-strip" aria-label="目前的餐廳名單">
          <div className="source-title">
            <span className="source-icon">
              <FileSpreadsheet size={18} />
            </span>
            <div>
              <strong>
                {isDemo ? "先用示範名單，試試手氣" : dataset.filename}
              </strong>
              <span>
                {isDemo
                  ? "8 間虛構餐廳 · 上傳你的 Excel，換成真實美食"
                  : `${dataset.restaurants.length} 間餐廳 · 名單僅儲存在此瀏覽器`}
              </span>
            </div>
          </div>
          {isDemo ? (
            <span className="demo-badge">示範資料</span>
          ) : (
            <button className="text-button" onClick={restoreDemo}>
              <RotateCcw size={13} />
              清除並回到示範
            </button>
          )}
        </section>
        {!!warnings.length && (
          <details className="import-warnings">
            <summary>
              <Info size={15} />
              匯入提醒（{warnings.length} 項）
            </summary>
            <ul>
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </details>
        )}

        <div className="workspace-grid">
          <aside className="filter-panel">
            <div className="panel-heading">
              <h2>
                <SlidersHorizontal size={18} />
                這餐，想吃什麼
              </h2>
              {activeFilters > 0 && (
                <button className="text-button muted" onClick={resetFilters}>
                  重設
                </button>
              )}
            </div>
            <fieldset>
              <legend>用餐範圍</legend>
              <div className="area-options">
                {(
                  [
                    { key: "all", label: "都可以" },
                    { key: "campus", label: "清大校內" },
                    { key: "nearby", label: "校園周邊" },
                  ] as const
                ).map((area) => (
                  <button
                    key={area.key}
                    aria-pressed={filters.area === area.key}
                    className={filters.area === area.key ? "active" : ""}
                    onClick={() => changeFilter("area", area.key)}
                  >
                    {area.label}
                  </button>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend>今天的口味</legend>
              <div className="category-options">
                <button
                  className={filters.category === "all" ? "active" : ""}
                  aria-pressed={filters.category === "all"}
                  onClick={() => changeFilter("category", "all")}
                >
                  <Utensils size={14} />
                  不挑食
                </button>
                {categories.map((category) => (
                  <button
                    key={category}
                    className={filters.category === category ? "active" : ""}
                    aria-pressed={filters.category === category}
                    onClick={() => changeFilter("category", category)}
                  >
                    {category === "輕食" ? (
                      <Leaf size={14} />
                    ) : category === "早餐" ? (
                      <Coffee size={14} />
                    ) : null}
                    {category}
                  </button>
                ))}
              </div>
            </fieldset>
            <div className="filter-field">
              <label htmlFor="budget">
                每人預算上限<span>新台幣</span>
              </label>
              <div className="select-wrap">
                <Wallet size={16} />
                <select
                  id="budget"
                  value={filters.maxPrice ?? "all"}
                  onChange={(e) =>
                    changeFilter(
                      "maxPrice",
                      e.target.value === "all" ? null : Number(e.target.value),
                    )
                  }
                >
                  <option value="all">吃得開心就好，不限預算</option>
                  <option value="100">NT$ 100 以內</option>
                  <option value="150">NT$ 150 以內</option>
                  <option value="200">NT$ 200 以內</option>
                  <option value="300">NT$ 300 以內</option>
                </select>
                <ChevronDown size={15} />
              </div>
            </div>
            <div className="filter-field">
              <label htmlFor="restaurant-search">搜尋一點靈感</label>
              <div className="search-wrap">
                <Search size={16} />
                <input
                  id="restaurant-search"
                  placeholder="餐廳、地址或餐點類型"
                  value={filters.query}
                  onChange={(e) => changeFilter("query", e.target.value)}
                />
              </div>
            </div>
            <div className="filter-count">
              <span className="status-dot" />
              <strong>{candidates.length}</strong> 間餐廳符合你的心情
            </div>
          </aside>

          <section className="pick-panel" aria-label="隨機餐廳推薦">
            <div className="pick-topline">
              <span>
                <Sparkles size={15} />
                LET FATE DECIDE
              </span>
              <span className="subtle-badge">
                {isDemo ? "示範模式" : "你的專屬名單"}
              </span>
            </div>
            <div
              className={`pick-content ${picking ? "is-picking" : ""}`}
              aria-live="polite"
              aria-atomic="true"
            >
              {!candidates.length ? (
                <div className="empty-result">
                  <div className="dice-wrap empty">
                    <Search size={35} strokeWidth={1.5} />
                  </div>
                  <h2>這次條件有點挑嘴</h2>
                  <p>
                    目前沒有符合條件的餐廳。
                    <br />
                    放寬預算或口味，讓選擇多一點吧。
                  </p>
                  <button className="text-button" onClick={resetFilters}>
                    清除篩選，看看所有餐廳 <ArrowRight size={15} />
                  </button>
                </div>
              ) : picking ? (
                <div className="empty-result">
                  <div className="dice-wrap rolling">
                    <Dice5 size={45} strokeWidth={1.4} />
                  </div>
                  <h2>尋找你的下一口幸福…</h2>
                  <p>好吃的，值得等一下。</p>
                </div>
              ) : current ? (
                <div className="restaurant-result">
                  <span className="result-eyebrow">就是這間，出發吧！</span>
                  <h2>{current.name}</h2>
                  <div className="result-tags">
                    <span>{areaLabel(current)}</span>
                    <span>{current.category}</span>
                    {isDemo && <span className="sample-tag">虛構示範</span>}
                  </div>
                  <div className="result-details">
                    <span>
                      <Wallet size={16} />
                      {priceLabel(current.price)}
                    </span>
                    <span>
                      <MapPin size={16} />
                      {current.area === "campus"
                        ? "校內用餐"
                        : current.distance === null
                          ? "距離未驗證"
                          : `距離 ${current.distance} 公里`}
                    </span>
                  </div>
                  <p className="result-address">
                    {current.address || "名單未提供地址"}
                  </p>
                  {current.note && (
                    <p className="result-note">{current.note}</p>
                  )}
                  {!isDemo && (
                    <a
                      className="map-link"
                      href={mapUrl(current)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      在 Google 地圖查看 <ArrowRight size={14} />
                    </a>
                  )}
                </div>
              ) : (
                <div className="empty-result">
                  <div className="dice-wrap">
                    <Dice5 size={47} strokeWidth={1.4} />
                    <span className="tiny-spark">✧</span>
                  </div>
                  <h2>下一餐，交給一點驚喜</h2>
                  <p>
                    不用再問「隨便吃什麼」。
                    <br />
                    按一下，讓命運幫你選一家。
                  </p>
                </div>
              )}
            </div>
            <div className="pick-actions">
              <button
                className="button primary-button"
                disabled={!candidates.length || picking}
                onClick={choose}
              >
                <Shuffle size={20} />
                {picking
                  ? "美食挑選中…"
                  : current
                    ? "再抽一間，換個靈感"
                    : "幫我決定這一餐"}
                <ArrowRight size={19} />
              </button>
              <p>
                <ShieldCheck size={13} />
                {candidates.length === 1
                  ? "目前只有 1 間符合條件，會推薦同一家"
                  : "每間餐廳機會均等，連續抽選不重複上一間"}
              </p>
            </div>
            <div className="pick-footer">
              <span className="small-heart">♡</span>{" "}
              每天最幸福的煩惱，就是下一餐吃什麼。
            </div>
          </section>
        </div>

        <section className="restaurant-section">
          <div className="section-title">
            <div>
              <h2>
                {history.length ? "剛剛的美食靈感" : "美食口袋名單"}
                <span>
                  {history.length ? history.length : candidates.length}
                </span>
              </h2>
              <p>
                {history.length
                  ? "還在猶豫？這幾間也值得放進心裡。"
                  : "先看一眼，也許心裡已經有了答案。"}
              </p>
            </div>
            <span className="list-caption">
              <ListFilter size={14} />
              {history.length
                ? "最近 3 次不重複推薦"
                : `顯示前 ${Math.min(candidates.length, 3)} 間`}
            </span>
          </div>
          <div className="restaurant-grid">
            {(history.length ? history : candidates.slice(0, 3)).map((r, i) => (
              <article className="restaurant-card" key={r.id}>
                <div className={`restaurant-icon color-${i % 3}`}>
                  {r.category === "輕食" ? (
                    <Leaf size={24} strokeWidth={1.5} />
                  ) : r.category === "早餐" ? (
                    <Coffee size={24} strokeWidth={1.5} />
                  ) : (
                    <Utensils size={24} strokeWidth={1.5} />
                  )}
                </div>
                <div className="card-copy">
                  <span className="card-area">
                    {areaLabel(r)} · {r.category}
                  </span>
                  <h3>{r.name}</h3>
                  <span className="card-price">
                    {priceLabel(r.price)}
                    <span> / 人</span>
                  </span>
                </div>
                <span className="card-number">0{i + 1}</span>
              </article>
            ))}
          </div>
          {!candidates.length && !history.length && (
            <p className="list-empty">沒有符合條件的餐廳，試著調整上方篩選。</p>
          )}
        </section>

        <section className="import-callout">
          <div className="callout-icon">
            <FileSpreadsheet size={26} strokeWidth={1.5} />
          </div>
          <div>
            <h2>把你的美食口袋，變成下一餐的靈感。</h2>
            <p>整理好 Excel 名單，匯入就能開始。你的資料留在自己的瀏覽器。</p>
          </div>
          <button
            className="text-button"
            onClick={template}
            disabled={downloading}
          >
            <ArrowDownToLine size={16} />
            {downloading ? "準備中…" : "下載 Excel 範本"}
            <ArrowRight size={15} />
          </button>
        </section>
        <p className="data-footnote">
          <Info size={13} />
          {isDemo
            ? "目前為虛構示範名單，並非清大真實或完整店家資料。請匯入經確認的名單後使用。"
            : "區域與距離依 Excel 提供，未自動定位或核實；周邊已知距離超過 2 公里的店家會略過。"}
          <br />
          店家、價格與營業資訊請於出發前確認。
        </p>
      </main>
      <footer className="site-footer">
        <span className="footer-brand">
          <UtensilsCrossed size={15} />
          食刻決定.
        </span>
        <span>Made for hungry minds around NTHU.</span>
        <span>
          好好吃飯，好好生活 <Heart size={12} />
        </span>
      </footer>

      <dialog
        ref={dialogRef}
        className="import-dialog"
        onCancel={(e) => {
          if (importing) e.preventDefault();
          else setModal(false);
        }}
        onClose={() => setModal(false)}
        onClick={(e) => {
          if (e.target === e.currentTarget && !importing) setModal(false);
        }}
        aria-labelledby="import-title"
      >
        <div className="dialog-heading">
          <span className="source-icon">
            <FileSpreadsheet size={24} />
          </span>
          <button
            className="icon-button"
            disabled={importing}
            aria-label="關閉匯入視窗"
            onClick={() => setModal(false)}
          >
            <X size={21} />
          </button>
        </div>
        <h2 id="import-title">帶上你的美食名單</h2>
        <p className="dialog-description">
          一份 Excel，就能讓「吃什麼」簡單一點。
        </p>
        <input
          type="file"
          accept=".xlsx"
          ref={inputRef}
          id="excel-file"
          aria-label="選擇 Excel 餐廳名單"
          className="visually-hidden"
          disabled={importing}
          onChange={(e: ChangeEvent<HTMLInputElement>) =>
            void handleFile(e.target.files?.[0])
          }
        />
        <button
          disabled={importing}
          className={`drop-zone ${dragging ? "dragging" : ""}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e: DragEvent) => {
            e.preventDefault();
            setDragging(false);
            void handleFile(e.dataTransfer.files[0]);
          }}
        >
          <Upload size={29} strokeWidth={1.5} />
          <strong>
            {importing ? "正在讀取你的美食名單…" : "點選或拖曳 Excel 檔案至此"}
          </strong>
          <span>支援 .xlsx · 最大 5 MB · 讀取第一張工作表</span>
        </button>
        {error && (
          <p className="import-error" role="alert">
            <Info size={16} />
            {error}
          </p>
        )}
        <div className="format-guide">
          <strong>第一列請使用以下欄位名稱</strong>
          <div>
            <code>餐廳名稱 *</code>
            <code>區域 *</code>
            <code>類型</code>
            <code>均消</code>
            <code>距離（公里）</code>
            <code>地址</code>
            <code>備註</code>
          </div>
          <p>
            *
            必填。區域填「清大校內」或「校園周邊」；均消填新台幣數字，距離以公里填寫。最多
            5,000 筆。
          </p>
          <p>
            請以一致的基準點（例如清大校門）核對周邊 2
            公里範圍；未提供距離的店家將標示「距離未驗證」。
          </p>
        </div>
        <button
          className="text-button template-link"
          onClick={template}
          disabled={downloading}
        >
          <ArrowDownToLine size={15} />
          {downloading
            ? "準備範本中…"
            : "還沒有名單？下載含示範資料的 Excel 範本"}
        </button>
        <p className="privacy-note">
          <ShieldCheck size={14} />
          Excel 內容不會上傳，僅在你的瀏覽器中處理與儲存。
        </p>
      </dialog>
    </>
  );
}
