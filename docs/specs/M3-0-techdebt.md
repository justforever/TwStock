# M3-0 前置技術債小包 規格

- 里程碑：M3 前置（M3 正式範圍另開規格）
- 作者：Architect（claude-opus-5）｜日期：2026-09-21
- 前一里程碑：`docs/specs/M2-chips.md`、驗收報告 `docs/reports/M2.md`
- 相關決策：沿用 D-001 ～ D-039，本包新增 **D-040 ～ D-042**
- 本包處理 `docs/reports/M2.md` §3.2 的 **U-17、U-15、U-16** 與 `docs/reports/M1.md` 的 **U-13**

## 0. 目標與完成標準

M2 收尾時留下四筆技術債。它們彼此無關，但都小、都會越拖越髒，**而且其中 U-17 是使用者在畫面上看得到的數字矛盾**，必須在有人開始認真看盤之前修掉。本包把它們拆成四個互不重疊的小任務先清乾淨，再開 M3 的功能任務。

| 任務 | 債 | 動到的層 | 為什麼獨立成一單 |
| --- | --- | --- | --- |
| T3-0-1 | U-17 副圖 y 軸單位與標題差 1000 倍 | 前端 `web/src/`（4 個檔） | 唯一使用者看得到的；要新增測試釘住換算 |
| T3-0-2 | U-15 `shareholding.py` upsert 漏 `updated_at` | 後端 `etl/`（2 個檔） | 純後端、要跑 DB 測試 |
| T3-0-3 | U-16 三項風格債 | `etl/`、`api/`、`web/` 各一個檔 | 三處都是「行為等價、只改寫法」，一次做完不互相牽動 |
| T3-0-4 | U-13 npm 弱點升級 | `web/package.json`、`package-lock.json` | **破壞性升級版本，必須獨立任務、獨立審查**（D-027 的精神：風險不同的改動不混在同一輪） |

**完成標準（四條都要成立）**：

1. `TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs` → **313 passed, 1 skipped**（基準線 312 passed / 1 skipped，T3-0-2 新增 1 個測試；唯一的 skip 仍是本機沒有 TimescaleDB 那一筆）。
2. `cd web && npm test` → **9 個檔、60 個測試全過**（基準線 9 檔 57 測，T3-0-1 新增 3 個測試），且 **stderr 不再出現任何 `not configured to support act(...)`**。
3. `scripts/m1_verify.sh` 最後一行 `M1 VERIFY PASSED`、`scripts/m2_verify.sh` 最後一行 `M2 VERIFY PASSED`，離開碼皆 0。
4. `cd web && npm audit` → **只剩 2 個 moderate**（`@vitest/mocker` 與相依它的 `vitest`），`critical` 與 `high` 歸零；`npm run build` 0 個 TypeScript error。

---

## 1. 共用規則（每個任務都適用）

### 1.1 環境事實（與 M2 §1.1 相同，再確認一次）

| 項目 | 值 |
| --- | --- |
| Repo 根目錄 | `/home/claude/TwStock`（以下簡稱「根目錄」） |
| git | branch `main`，最新 commit `6140cb9`。**只 commit，不要 push**；**Coder 不得 commit**（D-027） |
| Python | `.venv` 是 3.11；一律用 `.venv/bin/python -m pytest`，不要用系統 pip |
| Node | 22（npm 10） |
| PostgreSQL | 16，**沒有 TimescaleDB**；臨時叢集用 `scripts/pg_temp.sh start` |
| 網路 | pypi / npm **可用**；TWSE／TPEx／TDCC／MOPS／FinMind **連不到**（一律用 `etl/tests/fixtures/` 測） |
| Docker | 無法 pull／build 映像；只能 `docker compose -f deploy/docker-compose.yml --env-file .env.example config --quiet` |

### 1.2 慣例

- Bash 每次呼叫 cwd 會重置：**所有指令都用 `cd /home/claude/TwStock && ...` 開頭**。
- 文件、註解、log 訊息用繁體中文；識別字用英文。
- 每個 Python 函式要有型別註記；公開函式要有一行繁中 docstring。
- 前端版本一律精確鎖定（`package.json` 不帶 `^`），只有 T3-0-4 可以改版本號。
- **每個任務做完自己跑一次該任務的驗收指令，把逐字輸出貼進回報**；不要只寫「通過」。

### 1.3 本包的共同範圍邊界（四個任務都適用）

**不要做**：

- 不要改資料庫 schema、不要新增 migration。
- 不要改任何 API 的回應格式或欄位（`/api/...` 回的數字單位仍然是**股**，見 D-040）。
- 不要動 `etl/twstock_etl/sources/` 底下任何 parser 的換算邏輯（D-036 的 `SHARES_PER_LOT` 不在本包範圍）。
- 不要順手修 U-8（搜尋模糊比對）、U-10（上櫃除權息）、U-11（斷點續傳）——那些是 M3 正式範圍。
- 不要新增任何 Python 依賴；除 T3-0-4 外不要動 `web/package.json`。
- 不要重構與該任務無關的程式，不要改格式化風格、不要重排 import 以外的東西。

---

## 2. T3-0-1　U-17：副圖資料換算成「張」，與標題和讀數面板一致

### 2.1 問題

`web/src/components/ChartStack.tsx` 三個副圖的 pane 標題分別寫：

- 第 365 行 `成交量（張）`
- 第 371 行 `三大法人買賣超（張）`
- 第 378 行 `融資融券餘額（張）`

但 `setData()` 傳進去的是 API 原值，而 API 與 DB 的單位是**股**（`CLAUDE.md` 慣例、D-036）。因此 y 軸刻度的量級是股，比標題宣稱的張**大 1000 倍**。上方讀數面板同時用 `toLots()` 換算成張，**兩塊畫面的數字對不起來**。

### 2.2 決定：副圖資料也換算成張（D-040）

換算只做在**前端顯示層**（`ChartStack.tsx`），DB 與 API 一律維持「股」。理由與替代方案見 `docs/decisions.md` 的 **D-040**。

### 2.3 要改的檔案

| 檔案 | 動作 |
| --- | --- |
| `web/src/chipMath.ts` | 新增 `lotsValue()`；`toLots()` 改成呼叫它 |
| `web/src/chipMath.test.ts` | 新增 `lotsValue` 的測試 |
| `web/src/components/ChartStack.tsx` | 三個副圖的 `setData` 與對應的 `valueByTime` 都套 `lotsValue()` |
| `web/src/components/ChartStack.test.tsx` | mock 補 `__series`；新增 2 個測試 |

### 2.4 `web/src/chipMath.ts`

在 `toLots` **上面**新增（保留現有的 `consecutiveDays`、`toPercent` 不動）：

```ts
/**
 * 股 → 張的「數值」，四捨五入到整數張；例 20_200_000 → 20200。
 * 副圖序列與讀數面板共用這個換算，兩邊的數字才會完全一樣（D-040）。
 */
export function lotsValue(shares: number): number {
  return Math.round(shares / 1000)
}
```

`toLots` 改成：

```ts
/** 股 → 張的顯示字串（整數、千分位）；例 20_200_000 → "20,200"。 */
export function toLots(shares: number | null | undefined): string {
  if (shares === null || shares === undefined) {
    return '—'
  }
  return lotsValue(shares).toLocaleString('en-US')
}
```

**注意**：`lotsValue` 的參數不接受 `null`／`undefined`（呼叫端已經先過濾），回傳 `number` 不是字串。不要把 `toLots` 的 `'—'` 邏輯搬進去。

### 2.5 `web/src/components/ChartStack.tsx`

第 8 行 import 改成：

```ts
import { lotsValue, toLots, toPercent } from '../chipMath'
```

共 **6 處**要套 `lotsValue()`（行號以目前檔案為準，實際以程式碼內容比對為準）：

| # | 位置 | 原本 | 改成 |
| --- | --- | --- | --- |
| 1 | 約 128 行 `volumeSeries.setData` | `value: bar.volume` | `value: lotsValue(bar.volume)` |
| 2 | 約 137 行 `valueByTimeVolume` | `[bar.time, bar.volume]` | `[bar.time, lotsValue(bar.volume)]` |
| 3 | 約 158 行 `instSeries.setData` | `value: bar.total_net` | `value: lotsValue(bar.total_net)` |
| 4 | 約 165 行 `valueByTimeInst` | `[bar.time, bar.total_net]` | `[bar.time, lotsValue(bar.total_net)]` |
| 5a | 約 192 行 `marginSeriesBalance.setData` | `value: bar.margin_balance` | `value: lotsValue(bar.margin_balance)` |
| 5b | 約 204 行 `marginSeriesShort.setData` | `value: bar.short_balance` | `value: lotsValue(bar.short_balance)` |
| 6 | 約 213 行 `valueByTimeMargin` | `[bar.time, bar.margin_balance]` | `[bar.time, lotsValue(bar.margin_balance)]` |

**`valueByTime` 一定要跟著改**：它是 `chartSync.applyCrosshairToOthers()` 呼叫 `setCrosshairPosition(value, time, series)` 用的 y 座標，跟序列在同一個座標系；只改 `setData` 不改 `valueByTime`，十字線會被畫到圖外面。

**不要改的**：

- 主圖（K 線、MA）：價格不是股數，`valueByTimeMain` 用的是 `bar.close`，**原樣不動**。
- 讀數面板那 9 個 `<span>`：本來就已經用 `toLots()`，**原樣不動**。
- 三個 pane 標題的「（張）」字樣：**原樣不動**，這次就是要讓資料去配合標題。
- `priceFormat: { type: 'volume' }` 不動。
- `web/src/components/ChipTab.tsx`：已經一致（表格用 `toLots`、標題寫張），**不在本任務範圍**。

### 2.6 `web/src/chipMath.test.ts`

新增一個測試（放在既有的 `toLots` 測試旁邊）：

```ts
it('lotsValue 回傳整數張', () => {
  expect(lotsValue(20200000)).toBe(20200)
  expect(lotsValue(0)).toBe(0)
  expect(lotsValue(-5000000)).toBe(-5000)
  expect(lotsValue(1499)).toBe(1)
})
```

記得把 `lotsValue` 加進檔頭的 import。

### 2.7 `web/src/components/ChartStack.test.tsx`

**先改 mock**：目前 `makeSeries()` 產生的 series 沒有被留下來，測不到 `setData` 收到什麼。在 `createChart` 的 `chart` 物件字面值裡加一個 `__series` 陣列，並讓三個 `add*Series` 把產生的 series 推進去：

```ts
      const chart: any = {
        __series: [] as any[],
        addCandlestickSeries: vi.fn(() => { const s = makeSeries(); chart.__series.push(s); return s }),
        addLineSeries: vi.fn(() => { const s = makeSeries(); chart.__series.push(s); return s }),
        addHistogramSeries: vi.fn(() => { const s = makeSeries(); chart.__series.push(s); return s }),
        // 其餘欄位原樣不動
```

（`chart` 在閉包裡是延後求值的，和既有的 `chart.__crosshair = h` 寫法一樣，可以安全引用。）

**再新增 2 個測試**，放在 `describe('ChartStack', ...)` 最後：

```ts
  it('三個副圖的 setData 傳的是張（股 ÷ 1000）', () => {
    render(
      <ChartStack
        bars={testBars}
        institutional={testInstitutional}
        margin={testMargin}
        showInstitutional={true}
        showMargin={true}
      />
    )

    // charts[0] 主圖、charts[1] 成交量、charts[2] 三大法人、charts[3] 融資融券
    const volumeData = charts[1].__series[0].setData.mock.calls[0][0]
    expect(volumeData.map((d: any) => d.value)).toEqual([25000, 28000, 30000])

    const instData = charts[2].__series[0].setData.mock.calls[0][0]
    expect(instData.map((d: any) => d.value)).toEqual([6000, 9600, 13500])

    const marginBalanceData = charts[3].__series[0].setData.mock.calls[0][0]
    expect(marginBalanceData.map((d: any) => d.value)).toEqual([19500, 20000, 20200])

    const shortBalanceData = charts[3].__series[1].setData.mock.calls[0][0]
    expect(shortBalanceData.map((d: any) => d.value)).toEqual([900, 1000, 1090])
  })

  it('同步到副圖的十字線 y 值也是張，與讀數面板同一個數字', () => {
    const { container } = render(
      <ChartStack
        bars={testBars}
        institutional={testInstitutional}
        margin={testMargin}
        showInstitutional={true}
        showMargin={true}
      />
    )

    act(() => {
      charts[0].__crosshair({ time: '2026-09-18' })
    })

    expect(charts[1].setCrosshairPosition).toHaveBeenCalledWith(30000, '2026-09-18', expect.anything())
    expect(charts[2].setCrosshairPosition).toHaveBeenCalledWith(13500, '2026-09-18', expect.anything())
    expect(charts[3].setCrosshairPosition).toHaveBeenCalledWith(20200, '2026-09-18', expect.anything())

    const readout = container.querySelector('[data-testid="chart-readout"]') as HTMLElement
    expect(readout.querySelector('[data-testid="readout-volume"]')).toHaveTextContent('30,000')
    expect(readout.querySelector('[data-testid="readout-margin"]')).toHaveTextContent('20,200')
  })
```

預期數字的來源（`testBars` / `testInstitutional` / `testMargin` 就在同一個檔案裡，不要改它們）：

| 序列 | 原值（股） | 換算後（張） |
| --- | --- | --- |
| `volume` | 25000000 / 28000000 / 30000000 | 25000 / 28000 / 30000 |
| `total_net` | 6000000 / 9600000 / 13500000 | 6000 / 9600 / 13500 |
| `margin_balance` | 19500000 / 20000000 / 20200000 | 19500 / 20000 / 20200 |
| `short_balance` | 900000 / 1000000 / 1090000 | 900 / 1000 / 1090 |

既有的 9 個測試**一個都不能改**、**一個都不能刪**，尤其「讀數面板跟著十字線換日期」那個（它斷言 `5,000` 與 `19,500`，本任務不該影響它）。

### 2.8 驗收指令與預期輸出

```
cd /home/claude/TwStock/web && npm test
```

預期：

```
 ✓ src/components/ChartStack.test.tsx (11 tests)
 ✓ src/chipMath.test.ts (8 tests)
 Test Files  9 passed (9)
      Tests  60 passed (60)
```

```
cd /home/claude/TwStock/web && npm run build
```

預期：`✓ 56 modules transformed.`、0 個 TypeScript error、`✓ built in ...`。

### 2.9 範圍邊界（本任務不要做）

- 不要改 API、不要改後端任何檔案。
- 不要改 `ChipTab.tsx`、`chartSync.ts`、`StockPage.tsx`。
- 不要改 pane 標題文字。
- 不要順手做 T3-0-3 的 `setupTests.ts`（那是另一個任務，`act(...)` 提示這一輪還會出現，屬預期）。
- 不要升級任何 npm 套件。

---

## 3. T3-0-2　U-15：`shareholding` upsert 補 `updated_at`，並掃過所有 loader

### 3.1 問題

`etl/twstock_etl/loaders/shareholding.py` 第 69–76 行的 `on_conflict_do_update` 的 `set_` 只有 `holders`／`shares`／`ratio`，**沒有 `updated_at`**。集保資料被覆蓋重載時 `updated_at` 停在第一次寫入的時間。不影響數值正確性與冪等性，但將來若以 `updated_at` 判斷資料新鮮度會被誤導。

### 3.2 Architect 已掃過全部 upsert，只有這一處

`grep -rn 'on_conflict_do_update' etl/twstock_etl/loaders/*.py` 共 10 處：

| 檔案 | 處數 | `set_` 有 `updated_at` |
| --- | --- | --- |
| `loaders/calendar.py` | 1 | 有 |
| `loaders/chip.py` | 4（institutional／margin／sbl／foreign） | 4 處都有 |
| `loaders/price.py` | 3（daily_price／index_daily／adj_factor） | 3 處都有 |
| `loaders/stock.py` | 1 | 有 |
| **`loaders/shareholding.py`** | **1** | **沒有 ← 就是這一處** |

`db/tests/test_db_chip_tables.py` 也有一處，那是測試自己組的 SQL，**不要動**。

所以本任務只改一個 `set_`；**Coder 仍要自己重跑一次上面的 grep 並把輸出貼進回報**，確認沒有第 11 處。

### 3.3 要改的檔案

**`etl/twstock_etl/loaders/shareholding.py`**

檔頭 import 補 `func`（第 6 行）：

```python
from sqlalchemy import Connection, func
```

第 69–76 行的 `set_` 補一行：

```python
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "week_date", "level"],
            set_={
                "holders": stmt.excluded.holders,
                "shares": stmt.excluded.shares,
                "ratio": stmt.excluded.ratio,
                "updated_at": func.now(),
            },
        )
```

`shareholding_dist` 沒有 `source` 欄位（見 `db/twstock_db/tables.py` 第 173–184 行），**不要多加 `source`**。其餘邏輯（未知代號過濾、去重、分批）一律不動。

### 3.4 要加的測試

**`etl/tests/test_etl_shareholding.py`** 新增一個測試（放在既有的 `test_upsert_寫入_24_筆_未知代號_1` 後面）：

```python
def test_upsert_重載時_updated_at_會更新(clean_db):
    """重複 upsert 同一批集保資料時，updated_at 必須被更新（U-15）。"""
    from twstock_etl.loaders.stock import upsert_stocks
    from twstock_etl.models import StockRecord

    with clean_db.begin() as conn:
        upsert_stocks(
            conn,
            [
                StockRecord(
                    stock_id="2330",
                    name="台積電",
                    market="TWSE",
                    industry=None,
                    listed_date=None,
                    is_etf=False,
                    isin_code=None,
                    cfi_code=None,
                )
            ],
        )

    text_csv = (FIXTURE_DIR / "tdcc_shareholding_20260918.csv").read_text(encoding="utf-8")
    records = [r for r in parse_tdcc_shareholding(text_csv) if r.stock_id == "2330"]
    assert records, "fixture 應該有 2330 的資料"

    with clean_db.begin() as conn:
        upsert_shareholding(conn, records)
        first = conn.execute(
            select(shareholding_dist.c.updated_at)
            .where(shareholding_dist.c.stock_id == "2330")
            .order_by(shareholding_dist.c.level)
            .limit(1)
        ).scalar_one()

    time.sleep(0.01)

    with clean_db.begin() as conn:
        upsert_shareholding(conn, records)
        second = conn.execute(
            select(shareholding_dist.c.updated_at)
            .where(shareholding_dist.c.stock_id == "2330")
            .order_by(shareholding_dist.c.level)
            .limit(1)
        ).scalar_one()

    assert second > first
```

檔頭補 `import time`（放在 `from datetime import date` 上面的標準函式庫區塊）。`select` 與 `shareholding_dist` 檔頭已經有，不要重複 import。

**為什麼一定要 `> `（嚴格大於）而不是 `>=`**：`>=` 在修好之前也會通過（同一個時間戳），那樣測試就抓不到這個 bug。`func.now()` 是 PostgreSQL 的 transaction timestamp，兩次 upsert 在**不同的 transaction**（上面的程式碼刻意分成兩個 `with clean_db.begin()`），所以時間戳一定不同；`time.sleep(0.01)` 只是保險。

**先驗證這個測試真的會抓到 bug**：把 `loaders/shareholding.py` 改回沒有 `updated_at` 的版本跑一次，這個測試必須 FAIL；改回來再跑一次必須 PASS。把兩次輸出都貼進回報。

### 3.5 驗收指令與預期輸出

```
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest etl/tests/test_etl_shareholding.py -v
```

預期：全數 passed，含新的 `test_upsert_重載時_updated_at_會更新`。

```
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
```

預期：**313 passed, 1 skipped**，skip 仍然只有 `test_db_hypertable.py:74`。

```
cd /home/claude/TwStock && scripts/m2_verify.sh | tail -1
```

預期：`M2 VERIFY PASSED`（離開碼 0）。集保重載路徑在這支腳本裡會被走到，是這次改動的端到端回歸。

### 3.6 範圍邊界（本任務不要做）

- 不要改其他 9 處 `on_conflict_do_update`（它們都已經正確）。
- 不要改 `db/tests/test_db_chip_tables.py`。
- 不要改 `jobs.py`（那是 T3-0-3）。
- 不要改 schema、不要加 migration、不要改 `shareholding_dist` 的欄位。
- 不要改 `upsert_shareholding` 的回傳型別或去重邏輯。

---

## 4. T3-0-3　U-16：三項風格債（行為等價，只改寫法）

三處互不相干，一次做完。**每一處都不能改變任何行為**；判準是「改完之後測試數不變、全部照過」。

### 4.1 `etl/twstock_etl/jobs.py`：函式內 import 移到頂層

`load_shareholding()` 第 569–570 行有兩行函式內 import：

```python
    from twstock_etl.loaders.shareholding import upsert_shareholding
    from twstock_etl.sources.tdcc import fetch_tdcc_shareholding, parse_tdcc_shareholding
```

**刪掉這兩行**，改放到模組頂層的 import 區塊，照字母序插入：

- `from twstock_etl.loaders.shareholding import upsert_shareholding` → 放在 `from twstock_etl.loaders.price import (...)` 這個區塊**之後**、`from twstock_etl.loaders.stock import (...)` **之前**。
- `from twstock_etl.sources.tdcc import fetch_tdcc_shareholding, parse_tdcc_shareholding` → 放在 `from twstock_etl.sources.isin import ...` **之後**、`from twstock_etl.sources.tpex_price import ...` **之前**。

**循環 import 風險已由 Architect 查過**：`loaders/shareholding.py` 只 import `twstock_db.tables`、`loaders.price`、`models`；`sources/tdcc.py` 只 import `dates`／`errors`／`http`／`models`／`numbers`／`sources.report`。兩者都沒有 import `jobs`，所以移到頂層安全。Coder 仍要跑一次驗證：

```
cd /home/claude/TwStock && .venv/bin/python -c "import twstock_etl.jobs; import twstock_etl.cli; import twstock_etl.scheduler; print('IMPORT_OK')"
```

必須印出 `IMPORT_OK`。

同時檢查 `jobs.py` 裡還有沒有別的函式內 import：

```
cd /home/claude/TwStock && grep -n '^\s\+\(from\|import\) ' etl/twstock_etl/jobs.py
```

改完之後這行 grep 應該**沒有任何輸出**。把輸出（或沒有輸出這件事）貼進回報。

### 4.2 `web/src/setupTests.ts`：關掉 `act(...)` 提示

前端測試 stderr 會出現 6 次 `The current testing environment is not configured to support act(...)`。原因是 React 19 需要 `IS_REACT_ACT_ENVIRONMENT` 旗標。在檔案最後加：

```ts
// React 19 需要這個旗標才認得測試環境的 act()，否則每次 render 都會印警告
;(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
```

**Architect 已實測過**：加上之後 `npm test` 仍然 9 檔全過、`act(...)` 提示歸零。不要改任何測試檔、不要改 `vite.config.ts`、不要加 `@testing-library` 的設定檔。

（`StockPage.test.tsx` 那筆 `Failed to fetch institutional data: Error: HTTP 500` 的 stderr 是測試**故意**觸發的錯誤路徑，**不是**要清掉的東西。）

### 4.3 `api/twstock_api/chip_repository.py`：`_LATEST_DATE_SQL` 型別註記

第 18 行目前是 `dict[str, str]`，存純字串，每次查詢再 `text(sql_str)`。M2 規格要求的是 `dict[str, TextClause]`（SQL 先編譯好）。改成規格的版本：

檔頭 import 補：

```python
from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause
```

第 18–23 行改成：

```python
_LATEST_DATE_SQL: dict[str, TextClause] = {
    "institutional": text("SELECT MAX(trade_date) FROM institutional_daily WHERE stock_id = :stock_id"),
    "margin":        text("SELECT MAX(trade_date) FROM margin_daily WHERE stock_id = :stock_id"),
    "foreign":       text("SELECT MAX(trade_date) FROM foreign_holding WHERE stock_id = :stock_id"),
    "shareholding":  text("SELECT MAX(week_date) FROM shareholding_dist WHERE stock_id = :stock_id"),
}
```

`latest_chip_date()` 第 31–32 行跟著改（不要再包一次 `text()`）：

```python
    stmt = _LATEST_DATE_SQL[kind]
    row = conn.execute(stmt, {"stock_id": stock_id}).fetchone()
```

第 28–29 行的 `if kind not in _LATEST_DATE_SQL: raise ValueError(...)` **保留不動**，錯誤訊息一個字都不要改（有測試在斷言它）。SQL 字串本身**一個字都不要改**，仍然是參數化的 `:stock_id`。

### 4.4 驗收指令與預期輸出

```
cd /home/claude/TwStock && .venv/bin/python -c "import twstock_etl.jobs; import twstock_etl.cli; import twstock_etl.scheduler; print('IMPORT_OK')"
```
預期：`IMPORT_OK`

```
cd /home/claude/TwStock && grep -n '^\s\+\(from\|import\) ' etl/twstock_etl/jobs.py
```
預期：無輸出（離開碼 1）

```
cd /home/claude/TwStock && TWSTOCK_TEST_DATABASE_URL=$(scripts/pg_temp.sh start) .venv/bin/python -m pytest -rs
```
預期：**313 passed, 1 skipped**（T3-0-2 已完成的前提下；若本任務先做則是 312 passed, 1 skipped）。本任務**不新增也不刪除任何測試**。

```
cd /home/claude/TwStock/web && npm test 2>&1 | grep -c 'not configured to support act'
```
預期：`0`

```
cd /home/claude/TwStock/web && npm test
```
預期：`Test Files  9 passed (9)`、`Tests  60 passed (60)`（T3-0-1 已完成的前提下）。

```
cd /home/claude/TwStock && scripts/m1_verify.sh | tail -1 && scripts/m2_verify.sh | tail -1
```
預期：`M1 VERIFY PASSED`、`M2 VERIFY PASSED`。`jobs.py` 與 `chip_repository.py` 都在這兩條路徑上，必跑。

### 4.5 範圍邊界（本任務不要做）

- 三處都是**行為等價**的改寫：不要順手改邏輯、不要改錯誤訊息、不要改 SQL 文字、不要改函式簽名。
- 不要把 `chip_repository.py` 其他的 `text(...)` 查詢也改成模組常數（那是另一種重構，會動到一大片）。
- 不要動 `price_repository.py` 或其他 API 檔案。
- 不要改 `etl/twstock_etl/` 底下 `jobs.py` 以外的檔案。
- 不要動 `web/` 底下 `setupTests.ts` 以外的檔案。

---

## 5. T3-0-4　U-13：npm 弱點升級（**獨立任務、獨立審查**）

### 5.1 目前狀況

`cd web && npm audit` 目前回報 **5 個弱點（1 critical／3 high／1 moderate）**：

| 套件 | 目前版本 | 嚴重度 | 說明 |
| --- | --- | --- | --- |
| `react-router` / `react-router-dom` | 7.9.1 | **critical + high**（13 條 advisory，含 turbo-stream RCE） | 多為 SSR／server action 情境，本專案是純 SPA + nginx 靜態檔，但數量太多不宜再拖 |
| `vite` | 7.1.5 | high（6 條） | 全部是 dev server 的 `server.fs.deny` 繞過與路徑穿越，正式部署不跑 dev server |
| `@vitest/mocker` / `vitest` | 3.2.4 | moderate | dev 相依 |

### 5.2 升級目標版本（Architect 已實測過，照抄即可）

只升到「修掉 critical／high 的**最低**版本」，**不跨大版本**（D-042）：

```
react-router-dom  7.9.1  →  7.18.4
vite              7.1.5  →  7.3.6
vitest            3.2.4  →  3.2.7
```

**不要**升 `vite@8`、**不要**升 `vitest@5`、**不要**動 `@vitejs/plugin-react`（5.0.2 不變）、**不要**動 `react`／`react-dom`（19.1.1 不變）、**不要**動 `lightweight-charts`（4.2.3 不變，D-039 的 v4 API 假設建立在這個版本上）、**不要**動 `typescript`、`jsdom`、`@testing-library/*`。

**不要**跑 `npm audit fix --force`——它會把 `vitest` 拉到 5.0.1（破壞性）。

### 5.3 指令

```
cd /home/claude/TwStock/web && npm install --no-fund react-router-dom@7.18.4 vite@7.3.6 vitest@3.2.7
```

`package.json` 的三個版本號要變成精確鎖定（`"react-router-dom": "7.18.4"`、`"vite": "7.3.6"`、`"vitest": "3.2.7"`，**不帶 `^`**）；`npm install` 若自動加上 `^`，手動改掉再跑一次 `npm install` 讓 lock 檔一致。`package-lock.json` 一起進版控。

### 5.4 `react-router-dom` 7.18 破壞性變更的檢查

本專案用到的 API 只有 6 處（Architect 已 grep 過全部 `web/src/`）：

| 檔案 | 用到的 API |
| --- | --- |
| `web/src/main.tsx` | `BrowserRouter` |
| `web/src/App.tsx` | `Routes`、`Route`、`Link` |
| `web/src/pages/SearchPage.tsx` | `Link` |
| `web/src/pages/StockPage.tsx` | `useParams` |
| `web/src/pages/SearchPage.test.tsx` | `MemoryRouter` |
| `web/src/pages/StockPage.test.tsx` | `MemoryRouter`、`Routes`、`Route` |

這些都是 v7 的穩定 API。**Architect 已實跑過完整升級**：9 檔 57 測全過、`npm run build` 0 error、bundle 從 406.29 kB / gzip 129.67 kB 變成 410.39 kB / gzip 131.01 kB（+4.1 kB）。**所以若測試或 build 失敗，是 Coder 動到了不該動的東西，不是版本問題——停下來回報，不要自行改路由程式。**

### 5.5 驗收指令與預期輸出

```
cd /home/claude/TwStock/web && npm test
```
預期：`Test Files  9 passed (9)`、`Tests  60 passed (60)`（T3-0-1 已完成的前提下）。**一個測試都不准改**。

```
cd /home/claude/TwStock/web && npm run build
```
預期：`vite v7.3.6 building client environment for production...`、`✓ 56 modules transformed.`、0 個 TypeScript error、JS bundle 約 410 kB / gzip 約 131 kB。

```
cd /home/claude/TwStock/web && npm audit
```
預期**恰好**：

```
@vitest/mocker  2.1.0 - 4.1.10
Severity: moderate
...
  vitest  2.1.0-beta.1 - 4.1.10
  Depends on vulnerable versions of @vitest/mocker
...
2 moderate severity vulnerabilities
```

也就是 **critical 0、high 0、moderate 2**。剩下這 2 個要升 `vitest@5`（破壞性）才能修，本包**刻意不修**，理由見 D-042——`vitest` 是 devDependency，不會進 `dist/`，也不會上正式機。

```
cd /home/claude/TwStock/web && grep -n '"react-router-dom"\|"vite"\|"vitest"' package.json
```
預期：三行都是精確版本、不帶 `^`。

### 5.6 範圍邊界（本任務不要做）

- **只動 `web/package.json` 與 `web/package-lock.json` 兩個檔案。** 任何 `.ts`／`.tsx` 都不要改，任何後端檔案都不要改。
- 不要跑 `npm audit fix --force`、不要跑 `npm update`。
- 不要升級未列在 §5.2 的任何套件（包含 transitive 相依，交給 lock 檔自己解）。
- 不要刪 `node_modules` 重裝以外的清理動作；不要把 `node_modules` 或 `dist` 加進版控。
- 若升級後 `npm audit` 出現 §5.5 以外的結果（例如又冒出新的 high），**停下來回報**，不要自行再升版本。

---

## 6. 任務順序與相依

```
T3-0-1（U-17，前端單位）  ─┐
T3-0-2（U-15，後端 upsert）─┼─ 三者彼此無相依，但照此順序做，審查也照此順序
T3-0-3（U-16，三項風格債）─┘
                            └─→ T3-0-4（U-13，npm 升級）：獨立一輪審查
```

- **T3-0-1 排第一**：唯一使用者看得到的錯誤，優先級最高。
- **T3-0-3 的 §4.2 依賴 T3-0-1 的測試已定版**：T3-0-1 會新增 2 個前端測試，先做完 T3-0-1，T3-0-3 的「`act` 提示歸零且 60 測全過」才是一句話能驗完的事。
- **T3-0-4 一定排最後、且單獨一輪審查**：升版會動到 lock 檔與 `node_modules`，混在其他任務裡會讓「測試掛掉是誰造成的」變得無法判斷。做 T3-0-4 之前，T3-0-1 ～ T3-0-3 必須都已 APPROVE 並 commit。

四個任務全部 APPROVE 後，Architect 重跑 §0 的四條完成標準做本包驗收，通過才開 M3 正式規格。

---

## 7. 流程規則（沿用 D-027）

- **Coder 不得 `git commit`**，改完通知 Reviewer。
- **審查報告一律由 Reviewer 寫**，放 `docs/reviews/T3-0-<n>.md`。
- 每個任務一輪一份報告；退回重做的第 2 輪寫進同一份的「第 2 輪」章節。
- 規格不清楚就**停下來問 Architect**，不要猜。

---

## 8. 本包不涵蓋（M3 正式規格再處理）

| # | 項目 | 為什麼不在這包 |
| --- | --- | --- |
| U-8 | 搜尋沒有模糊比對與索引 | 要改 schema（索引）與 API 行為，是功能不是技術債 |
| U-10 | 上櫃除權息／上櫃還原價 | 需要新來源與還原係數重算，是 M3 最大的一塊 |
| U-11 | 斷點續傳只解了一部分 | 要重新設計 job 狀態，範圍大 |
| V-9 ～ V-20 | 真實來源格式驗證 | 本環境連不到官方站，只能在使用者 Mac 上做 |
| — | lightweight-charts 升 v5、法人堆疊柱 | D-039 已說明留待之後的里程碑 |
| — | 集保資料太短時前端標示「資料累積中」 | M2 報告 §4 的建議，屬 M3 功能範圍 |
