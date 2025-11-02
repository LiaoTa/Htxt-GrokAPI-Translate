## Htxt-GrokAPI-Translate
這個程式修改成便攜式，可自動並邊翻譯邊自動增加翻譯對照表,保持人名地名從頭到尾一致。
需要設定Grok API key，(別用ChatGPT API，你翻譯情色txt，5000行，可以用審查名義檔下1000多行，你心裡只剩毀滅吧,啥玩意)
提示詞專門針對日文翻譯中文痛點修改。
簡易使用說明 下載並解壓,在.env那寫入你的API key，把你要翻譯的日文文件(限定txt)放到stepa目錄下,雙擊1.bat，把stepb目錄下文件拷貝到stepd目錄下，雙擊2.bat，如果完成有行數失敗，再雙擊2.bat，他會針對沒完成或失敗的再跑一次,你會再
stepaa/目錄下看到翻譯完成的檔案。
下載地址:
https://drive.google.com/file/d/1vqr-o3YIDMwyuaxF56rfg-wjfqxBKAOw/view?usp=sharing
## 日英文TXT批次翻譯成中文TXT流程總覽

這個專案提供一套從原始文字到最終合併輸出的完整管線，透過 Grok 模型批次翻譯日文或英文內容，並邊翻譯邊自動增加翻譯對照表與擬聲詞字典，可保持人名地名從頭到尾一致。以下依執行順序介紹各個腳本的用途：

1. `1_stepa_txt_to_stepb_html.py`
   - 讀取 `stepa/` 的純文字檔。
   - 將每行內容轉成 `<p data-line="編號">…</p>` 格式的 HTML，輸出至 `stepb/`。
   - 為每個檔案在 `stepc/` 建立對應的初始 `translation_dictionary` JSON。
2. `2_Trans_JP_to_ZH_grok-4-fast-reasoning.py`
   - 讀取 `stepd/` 的 HTML 檔，依批次呼叫 Grok `grok-4-fast-reasoning` 模型。
   - 依批次內容挑選相關翻譯對照與擬聲詞條目，並在回傳後合併更新。
   - 將翻譯結果回寫原檔，並保留 request、response、錯誤與純文字備份。
3. `3_sound_dictionary_clean.py`
   - 清理 `stepc/` 目錄下所有 `sound_dictionary*.json`，移除 `sound_jp` 與 `sound_zh` 相同的條目。
   - 維持擬聲詞字典的品質與可讀性。
4. `4_stepl_merge_to_stepm.py`
   - 讀取 `stepl/` 的多個翻譯結果，依 `data-line` 交錯排列。
   - 將整理後的純文字輸出到 `stepm/output.txt`，方便後續彙整或校稿。
5. `5_stepa_txt_to_stepb_html(en).py`
   - 這是建立英中對照的基本翻譯對照表。
   - 讀取 `stepa/` 的純文字檔。
   - 將每行內容轉成 `<p data-line="編號">…</p>` 格式的 HTML，輸出至 `stepb/`。
   - 為每個檔案在 `stepc/` 建立對應的初始 `translation_dictionary` JSON。
6. `6_Trans_EN_to_ZH_grok-4-fast-reasoning.py`
   - 這是英文翻譯成中文，去除擬聲詞功能，保留基本自動增加的翻譯對照表。
   - 讀取 `stepd/` 的 HTML 檔，依批次呼叫 Grok `grok-4-fast-reasoning` 模型。
   - 依批次內容挑選相關翻譯對照與擬聲詞條目，並在回傳後合併更新。
   - 將翻譯結果回寫原檔，並保留 request、response、錯誤與純文字備份。
---

### 主要目錄說明

- `stepa/`：原始純文字來源。
- `stepb/`：步驟 1 產生的 HTML。用HTML標籤來包裹行號，進行程式結構定位。
- `stepc/`：翻譯字典與擬聲詞字典所在地。
  - `<檔名>.json`：各檔案專屬的 `translation_dictionary`。
  - `sound_dictionary.json`：全局擬聲詞字典（以 indent=2 儲存）。
- `stepd/`：步驟 2 的翻譯輸入 HTML。將stepb/目錄下的txt，拷貝到這裡.可以重複執行步驟 2 ，他會再次處理失敗跟未處理的行。
- `stepe/`：Grok request 備份。
- `stepf/`：Grok 正常回應。
- `stepg/`：Grok 拒絕或錯誤回應。
- `stepaa/`：已翻譯的純文字版本。(每一行都有，可能夾雜翻譯一半跟未翻譯的行)。每次執行完成步驟 2，會根據stepd/的文件重新生成一次。
- `stepl/`：待合併的翻譯結果。可以把stepb/的原文，stepd/的翻譯文(改名)，可多版本並列，他會根據行號進行合併成原文跟翻譯的每行對照。
- `stepm/`：步驟 4 的輸出目錄（`output.txt`）。
- `portable_setup.py`：共用的便攜化工具，負責解析 `.env` 並提供專案相對路徑。

---

stepa，stepb，stepc，stepd如果有新文件要處理，要自己手動清除,但stepc/sound_dictionary.json記得保留
stepe，stepf，stepg，每重新執行步驟 2 ，會自動清除並更新。

### 執行前準備（便攜版只需執行3）

1. 安裝 Python 3.9 以上版本，並確認命令列可呼叫 `python` 或 `py`。
2. 於專案根目錄安裝必要套件：
   ```bash
   pip install openai
   ```
3. 設定 Grok API 金鑰：
   - 專案內已提供 `.env` 範本，請編輯後填入：
     ```bash
     XAI_API_KEY=你的金鑰
     ```
   - 或改用系統環境變數：
     ```bash
     # macOS / Linux
     export XAI_API_KEY="你的金鑰"

     # Windows PowerShell
     setx XAI_API_KEY "你的金鑰"
     ```
4. 確認輸入檔為 UTF-8 編碼並放置於對應目錄（例如 `stepa/` 或 `stepd/`）。

---

### 建議操作流程

1. **轉換純文字為 HTML 並建立初始字典**
   ```bash
   python 1_stepa_txt_to_stepb_html.py
   ```
   - `stepa/*.txt` → `stepb/*.txt`（HTML with data-line）
   - 同時建立 `stepc/<檔名>.json`

2. **準備翻譯輸入並執行 Grok 批次翻譯**
   - 若需要，可手動檢整 `stepb/` 內容後複製到 `stepd/`。
   ```bash
   python 2_Trans_JP_to_ZH_grok-4-fast-reasoning.py
   ```
   - 產生 API 紀錄於 `stepe/`、`stepf/`、`stepg/`，純文字輸出於 `stepaa/`。
   - 翻譯字典、擬聲詞字典會同步更新。

3. **清理擬聲詞字典（選擇性）**
   ```bash
   python 3_sound_dictionary_clean.py
   ```
   - 移除 `sound_dictionary*.json` 中重複或無效條目。

4. **整併翻譯結果（選擇性），用於比較原文跟多版本的翻譯**
   ```bash
   python 4_stepl_merge_to_stepm.py
   ```
   - `stepl/*.txt` → `stepm/output.txt`

> 可依實際情況調整順序，例如已有整理好的 HTML 時可直接放入 `stepd/` 後執行步驟 2。

---

### Windows 快速啟動（便攜版）

專案根目錄新增的 `1.bat` ~ `6.bat` 會自動切換到腳本所在目錄、載入 `.env`，並尋找可用的 Python（依序檢查 `python-3.11.9-embed-amd64\python.exe` → `venv\Scripts\python.exe` → 系統 `python.exe`／`py.exe`，若你已把可攜版 Python 移入 `venv\Scripts` 也會被偵測）。

- `1.bat`：執行 `1_stepa_txt_to_stepb_html.py`
- `2.bat`：執行 `2_Trans_JP_to_ZH_grok-4-fast-reasoning.py`
- `3.bat`：執行 `3_sound_dictionary_clean.py`
- `4.bat`：執行 `4_stepl_merge_to_stepm.py`
- `5.bat`：執行 `5_stepa_txt_to_stepb_html(en).py`
- `6.bat`：執行 `6_Trans_EN_to_ZH_grok-4-fast-reasoning.py`

> 使用方式：於 Windows 檔案總管直接雙擊、或在終端機切到專案根目錄後輸入 `1`～`6` 對應批次檔，即可進行整套翻譯流程。
>
> 若使用內建的可攜版 Python：請先於 `venv\Scripts\python311._pth` 取消註解 `import site`（目前已協助預設啟用），並把需要的套件（例如 `openai`）解壓至 `venv\Scripts\Lib\site-packages/` 後再執行批次檔。

---

### Grok 系統提示與處理步驟

- **角色設定**：將模型定位為多語言理解與繁體中文潤飾專家，禁止輸出分析或 JSON，確保回覆僅為翻譯後的內容。
- **步驟 1 – HTML 範圍鎖定**：限定只處理標籤內文字並保留所有 HTML 標籤與屬性。
- **步驟 2 – 形態分析**：對輸入句子進行分詞、詞性、敬語層級與特殊詞類標記。
- **步驟 3 – 外來語處理**：將片假名外來語還原羅馬字並依原義翻譯，同時保留片假名。
- **步驟 4 – 漢字語義判斷**：釐清多義詞語境，挑選最貼切的中文意義。
- **步驟 5 – 語法依賴分析**：分析主從、修飾、並列等語法關係，為語序重組奠定基礎。
- **步驟 6 – 結構標記**：標記主詞、受詞、動詞等語法角色並調整助詞對應。
- **步驟 7 – 語序重組**：將日文 SOV 結構調整成符合中文閱讀習慣的 SVO。
- **步驟 8 – 情緒與場景**：根據 sound_dictionary 轉寫擬聲詞，補足情緒、心理、動作描寫。
- **步驟 9 – 敬語處理**：判斷尊敬語與人物稱謂，轉換為自然的中文敬稱。
- **步驟 10 – 翻譯潤飾**：整合字典、語法與情緒資訊，產生流暢且符合語境的翻譯。
- **步驟 11 – 氣氛與曖昧強化**：依情境強化視覺、觸覺與曖昧張力，使敘事更具氛圍。
- **步驟 12 – 文采提升**：調整語句節奏與修辭，增添表現力及在地化語感。
- **步驟 13 – 擬聲詞改寫**：將擬聲／擬態詞轉化為第三人稱視角的感官描寫或隱喻。(實務上，沒看到他有實際改寫，但是整個句子更好，所以保留敘述)
- **步驟 14 – 精簡語句**：移除多餘語助詞與重複語氣，維持語句自然流暢。
- **步驟 15 – 單行輸出規範**：每行只輸出一個翻譯句子，不夾帶任何標註或說明。
- **步驟 16 – HTML 回填**：將翻譯後文字填回原 HTML 結構並保持標籤與屬性不變。

---

### 常見問題
- **提示詞中的sound_dictionary佔的比重過大**：沒辦法很精確，日文擬聲詞已經經過程式限縮，然後經過詞性分析，不會錯誤翻譯。一次完成，總比次次失敗。
- **翻譯一直失敗**：可以查看stepe，stepf下找原因,然後參考行數去stepd那修改
- **sound_dictionary跟translation_dictionary會不會一股腦的塞進提示詞**：不會，針對要處理的批次，有先比對，有需要才塞進提示詞，會補足5個,讓AI知道回應的結構。
- **未設定 `XAI_API_KEY`**：程式會提示設定方式，可改為在程式內寫死金鑰或正確匯出變數。
- **API 回應失敗**：請查看 `stepg/` 內的檔案，檢討 request 與錯誤訊息後重送。
- **JSON 解析錯誤**：請確認 `stepc/` 下的 JSON 格式正確；必要時刪除重新生成。
- **目錄不存在**：腳本會自動建立所需資料夾，但仍建議確認磁碟權限與路徑。
- **批次過大**：可調整 `2_Trans_JP_to_ZH_grok-4-fast-reasoning.py` 中的 `batch_size` 或 `max_workers`。
- **每批次行數可不可以超過20行**：當然可以，只是就像所有AI處理長文本的通病，會偏移，一般會出現文言文，所以20行是經驗法則，你可以自己測試。
- **費用**：一般來說，一本フランス書院的4000行小說，處理完要價台幣8-12元,美金0.4左右.我程式有設Cached tokens,Input是$0.05/ 1M tokens，而不是$0.20/ 1M tokens,有沒有效，不知道.Output是$0.50/ 1M tokens。

---

透過上述六個腳本即可完成從資料預處理、翻譯、字典維護到最後整併的全流程。若有額外前置或後處理需求，可以在同目錄新增腳本並沿用這些資料結構。
以上所有程式由Claude AI完成，可以出成果我也很驚訝。






