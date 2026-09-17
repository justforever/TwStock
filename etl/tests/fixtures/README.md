# ETL Fixture 說明

本目錄包含 ETL parser 的測試樣本資料。

## 列表

| 檔案 | 來源 URL | 撰寫日期 | 說明 |
| --- | --- | --- | --- |
| `isin_twse_strmode2.html` | https://isin.twse.com.tw/isin/C_public.jsp?strMode=2 | 2026-09-18 | TWSE 上市個股清單（ISIN 一覽表） |
| `isin_tpex_strmode4.html` | https://isin.twse.com.tw/isin/C_public.jsp?strMode=4 | 2026-09-18 | TPEx 上櫃個股清單（ISIN 一覽表） |
| `twse_holiday_schedule_2026.json` | https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule | 2026-09-18 | 2026 年 TWSE 休市日 |

## 格式說明

- **ISIN HTML**：手寫樣本，依官方公開格式撰寫。原始網頁為 MS950 編碼，本檔以 UTF-8 儲存。資料值僅供測試，不保證與現況一致。
- **TWSE Holiday JSON**：手寫樣本，依官方公開格式撰寫。資料值僅供測試，不保證與現況一致。

## 編碼路徑

ISIN HTML 檔案原始編碼為 MS950，被轉換為 UTF-8 存儲。`decode_isin_bytes()` 函式應能正確處理原始 MS950 編碼，因此 `test_decode_isin_bytes_cp950` 會透過 `encode("cp950")` 來驗證 MS950 路徑。
