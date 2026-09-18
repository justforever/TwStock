# ETL Fixture 說明

本目錄包含 ETL parser 的測試樣本資料。

## 列表

| 檔案 | 來源 URL | 撰寫日期 | 說明 |
| --- | --- | --- | --- |
| `isin_twse_strmode2.html` | https://isin.twse.com.tw/isin/C_public.jsp?strMode=2 | 2026-09-18 | TWSE 上市個股清單（ISIN 一覽表） |
| `isin_tpex_strmode4.html` | https://isin.twse.com.tw/isin/C_public.jsp?strMode=4 | 2026-09-18 | TPEx 上櫃個股清單（ISIN 一覽表） |
| `twse_holiday_schedule_2026.json` | https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule | 2026-09-18 | 2026 年 TWSE 休市日 |
| `TWSE_price_20260916.json` | https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260916&type=ALLBUT0999&response=json | 2026-09-19 | TWSE 上市日成交（2026-09-16） |
| `TWSE_price_20260917.json` | https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260917&type=ALLBUT0999&response=json | 2026-09-19 | TWSE 上市日成交（2026-09-17） |
| `TWSE_price_20260918.json` | https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260918&type=ALLBUT0999&response=json | 2026-09-19 | TWSE 上市日成交（2026-09-18） |
| `TPEx_price_20260916.json` | https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=2026/09/16&type=EW&response=json | 2026-09-19 | TPEx 上櫃日成交（2026-09-16） |
| `TPEx_price_20260917.json` | https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=2026/09/17&type=EW&response=json | 2026-09-19 | TPEx 上櫃日成交（2026-09-17） |
| `TPEx_price_20260918.json` | https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=2026/09/18&type=EW&response=json | 2026-09-19 | TPEx 上櫃日成交（2026-09-18） |
| `TPEx_price_legacy_sample.json` | https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&d=115/09/18&o=json | 2026-09-19 | TPEx 舊版日成交（備援用） |
| `TAIEX_index_202609.json` | https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date=20260901&response=json | 2026-09-19 | TAIEX 指數日 K（2026 年 9 月） |
| `exright_20260901_20260930.json` | https://www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate=20260901&endDate=20260930&response=json | 2026-09-19 | TWSE 除權除息計算結果表（2026-09-01 ～ 2026-09-30） |

## 格式說明

- **ISIN HTML**：手寫樣本，依官方公開格式撰寫。原始網頁為 MS950 編碼，本檔以 UTF-8 儲存。資料值僅供測試，不保證與現況一致。
- **TWSE Holiday JSON**：手寫樣本，依官方公開格式撰寫。資料值僅供測試，不保證與現況一致。

## 編碼路徑

ISIN HTML 檔案原始編碼為 MS950，被轉換為 UTF-8 存儲。`decode_isin_bytes()` 函式應能正確處理原始 MS950 編碼，因此 `test_decode_isin_bytes_cp950` 會透過 `encode("cp950")` 來驗證 MS950 路徑。
