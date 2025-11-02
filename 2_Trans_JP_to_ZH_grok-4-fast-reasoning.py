import os
import json
import re
import random
from pathlib import Path
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from openai import OpenAI


DATA_LINE_ATTR_PATTERN = re.compile(
    r'data-line\s*=\s*(?:\\?["\'])?(?P<line>\d+)(?:\\?["\'])?',
    re.IGNORECASE,
)
P_TAG_WITH_LINE_PATTERN = re.compile(
    r'<p[^>]*data-line\s*=\s*(?:\\?["\'])?(?P<line>\d+)(?:\\?["\'])?[^>]*>.*?</p>',
    re.DOTALL | re.IGNORECASE,
)


def normalize_data_line_attribute(text: str) -> str:
    """將 data-line 屬性統一為未跳脫的雙引號格式。"""
    return DATA_LINE_ATTR_PATTERN.sub(
        lambda match: f'data-line="{match.group("line")}"',
        text,
    )


class TranslationBatchProcessor:
    def __init__(self, api_key: str, batch_size: int = 20, max_workers: int = 10):
        """初始化翻譯批次處理器

        Args:
            api_key: Grok API 金鑰
            batch_size: 每批處理的行數 (預設 20 行)
            max_workers: 並行處理的檔案數量 (預設 10)
        """
        self.client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.stepc_dir = Path("stepc")
        self.stepd_dir = Path("stepd")
        self.stepe_dir = Path("stepe")
        self.stepf_dir = Path("stepf")
        self.stepg_dir = Path("stepg")
        self.stepaa_dir = Path("stepaa")
        self.lock = threading.RLock()
        self.progress_tracker = {}
        self.last_update_time = 0
        self.update_interval = 0.5
        self.sound_dict_file = self.stepc_dir / "sound_dictionary.json"

        for dir_path in [self.stepc_dir, self.stepd_dir, self.stepe_dir,
                         self.stepf_dir, self.stepg_dir, self.stepaa_dir]:
            dir_path.mkdir(exist_ok=True)

    def is_japanese(self, text: str) -> bool:
        """檢測文字是否包含日文字元 (平假名、片假名或日文漢字)"""
        japanese_pattern = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]')
        return bool(japanese_pattern.search(text))

    def is_pure_chinese(self, text: str) -> bool:
        """檢測文字是否為純中文 (只包含中文字元、標點和空格)"""
        cleaned = re.sub(r'[\s\u3000-\u303F\uFF00-\uFFEF]', '', text)
        if not cleaned:
            return False
        chinese_pattern = re.compile(r'^[\u4E00-\u9FFF]+$')
        return bool(chinese_pattern.match(cleaned))

    def has_english_or_japanese(self, text: str) -> bool:
        """檢測文字中是否殘留英文或日文"""
        if re.search(r'[\u3040-\u309F\u30A0-\u30FF]', text):
            return True
        text_clean = re.sub(r'https?://[^\s]+', '', text)
        text_clean = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', text_clean)
        if re.search(r'[a-zA-Z]{2,}', text_clean):
            return True
        return False

    def validate_translation_entry(self, entry: Dict) -> bool:
        """驗證 translation_dictionary 條目是否有效"""
        if 'jp' not in entry or 'zh' not in entry:
            return False
        jp_text = entry['jp'].strip()
        zh_text = entry['zh'].strip()
        if not jp_text or not zh_text:
            return False
        if not self.is_japanese(jp_text):
            return False
        if not self.is_pure_chinese(zh_text):
            return False
        if self.has_english_or_japanese(zh_text):
            return False
        return True

    def validate_sound_entry(self, entry: Dict) -> bool:
        """驗證 sound_dictionary 條目是否有效"""
        if 'sound_jp' not in entry or 'sound_zh' not in entry:
            return False
        jp_text = entry['sound_jp'].strip()
        zh_text = entry['sound_zh'].strip()
        if not jp_text or not zh_text:
            return False
        if not self.is_japanese(jp_text):
            return False
        if not self.is_pure_chinese(zh_text):
            return False
        if self.has_english_or_japanese(zh_text):
            return False
        return True

    def sort_by_gojuon(self, sound_dict: List[Dict]) -> List[Dict]:
        """按照五十音順序排序 sound_dictionary"""
        gojuon_order = [
            'あ', 'い', 'う', 'え', 'お',
            'か', 'き', 'く', 'け', 'こ', 'が', 'ぎ', 'ぐ', 'げ', 'ご',
            'さ', 'し', 'す', 'せ', 'そ', 'ざ', 'じ', 'ず', 'ぜ', 'ぞ',
            'た', 'ち', 'つ', 'て', 'と', 'だ', 'ぢ', 'づ', 'で', 'ど',
            'な', 'に', 'ぬ', 'ね', 'の',
            'は', 'ひ', 'ふ', 'へ', 'ほ', 'ば', 'び', 'ぶ', 'べ', 'ぼ', 'ぱ', 'ぴ', 'ぷ', 'ぺ', 'ぽ',
            'ま', 'み', 'む', 'め', 'も',
            'や', 'ゆ', 'よ',
            'ら', 'り', 'る', 'れ', 'ろ',
            'わ', 'を', 'ん'
        ]

        def get_sort_key(item: Dict) -> tuple:
            text = item.get('sound_jp', '')
            if not text:
                return (999, text)
            first_char = text[0]
            if '\u30A0' <= first_char <= '\u30FF':
                first_char = chr(ord(first_char) - 0x60)
            try:
                index = gojuon_order.index(first_char)
                return (index, text)
            except ValueError:
                return (999, text)

        return sorted(sound_dict, key=get_sort_key)

    def load_sound_dictionary(self) -> List[Dict]:
        """載入全局 sound_dictionary"""
        if self.sound_dict_file.exists():
            try:
                with open(self.sound_dict_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except json.JSONDecodeError:
                pass
        return []

    def save_sound_dictionary(self, dictionary: List[Dict]):
        """儲存 sound_dictionary (線程安全)"""
        with self.lock:
            sorted_dict = self.sort_by_gojuon(dictionary)
            with open(self.sound_dict_file, 'w', encoding='utf-8') as f:
                json.dump(sorted_dict, f, ensure_ascii=False, indent=2)

    def merge_sound_dictionaries(self, original: List[Dict], new: List[Dict]) -> List[Dict]:
        """合併 sound_dictionary，確保 sound_jp 唯一"""
        existing_jp = {item['sound_jp'] for item in original if 'sound_jp' in item}
        merged = original.copy()
        for item in new:
            if self.validate_sound_entry(item):
                if item['sound_jp'] not in existing_jp:
                    merged.append(item)
                    existing_jp.add(item['sound_jp'])
        return merged

    def select_relevant_sounds(self, batch_lines: List[str], all_sounds: List[Dict], min_count: int = 3) -> List[Dict]:
        """選擇與批次內容相關的擬聲詞"""
        batch_text = ''.join(batch_lines)
        relevant = []
        for sound in all_sounds:
            sound_jp = sound.get('sound_jp', '')
            if sound_jp and sound_jp in batch_text:
                relevant.append(sound)
        if len(relevant) < min_count and len(all_sounds) > 0:
            remaining = [s for s in all_sounds if s not in relevant]
            needed = min(min_count - len(relevant), len(remaining))
            relevant.extend(random.sample(remaining, needed))
        return relevant

    def clear_directory(self, directory: Path):
        """清空指定目錄下的所有檔案"""
        if directory.exists():
            for file in directory.glob("*"):
                if file.is_file():
                    file.unlink()
            print(f"  🗑️ 已清空: {directory}/")

    def clear_processing_directories(self):
        """清空處理過程中的暫存目錄"""
        print(f"\n{'='*70}")
        print("🧹 清空暫存目錄...")
        print(f"{'='*70}")
        self.clear_directory(self.stepe_dir)
        self.clear_directory(self.stepf_dir)
        self.clear_directory(self.stepg_dir)
        print("✅ 暫存目錄清空完成\n")

    def extract_text_from_tags(self, line: str) -> str:
        """從 HTML 標籤中提取純文字內容"""
        match = re.search(r'<p[^>]*>(.*?)</p>', line, re.DOTALL)
        return match.group(1) if match else ""

    def contains_japanese(self, text: str) -> bool:
        """檢測文字中是否包含日文字元 (平假名或片假名)"""
        japanese_pattern = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')
        return bool(japanese_pattern.search(text))

    def contains_english(self, text: str) -> bool:
        """檢測文字中是否包含英文 (只檢測小寫字母，排除 URL、Email)"""
        text_without_urls = re.sub(r'https?://[^\s]+', '', text)
        text_without_urls = re.sub(r'www\.[^\s]+', '', text_without_urls)
        text_without_emails = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', text_without_urls)
        lowercase_pattern = re.compile(r'[a-z]{3,}')
        return bool(lowercase_pattern.search(text_without_emails))

    def needs_translation(self, line: str) -> bool:
        """判斷是否需要翻譯 (只檢查標籤內的文字內容)"""
        text_content = self.extract_text_from_tags(line)
        if not text_content or not text_content.strip():
            return False
        return self.contains_japanese(text_content) or self.contains_english(text_content)

    def extract_line_number(self, line: str) -> int:
        """從 HTML 標籤中提取行號"""
        match = DATA_LINE_ATTR_PATTERN.search(line)
        return int(match.group("line")) if match else -1

    def get_translation_lines(self, lines: List[str]) -> List[Tuple[int, str, int]]:
        """取得需要翻譯的行 (包含日文或英文)"""
        translation_lines = []
        for idx, line in enumerate(lines):
            if self.needs_translation(line):
                html_line_num = self.extract_line_number(line)
                translation_lines.append((idx, line, html_line_num))
        return translation_lines

    def load_translation_dictionary(self, json_file: Path) -> List[Dict]:
        """載入翻譯字典 (陣列格式)"""
        if json_file.exists():
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
            except json.JSONDecodeError:
                return []
        return []

    def save_translation_dictionary(self, json_file: Path, dictionary: List[Dict]):
        """儲存翻譯字典 (線程安全 - 使用 RLock 可重入)"""
        with self.lock:
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(dictionary, f, ensure_ascii=False, indent=2)

    def merge_dictionaries(self, original: List[Dict], new: List[Dict]) -> List[Dict]:
        """合併兩個字典陣列，只新增新的且有效的條目"""
        existing_jp = {item['jp'] for item in original if 'jp' in item}
        merged = original.copy()
        for item in new:
            if self.validate_translation_entry(item):
                if item['jp'] not in existing_jp:
                    merged.append(item)
                    existing_jp.add(item['jp'])
        return merged

    def select_relevant_translations(
        self,
        batch_lines: List[str],
        all_translations: List[Dict],
        target_count: int = 5
    ) -> List[Dict]:
        """Select translation entries related to the current batch."""
        if not all_translations:
            return []
        batch_raw = ''.join(batch_lines)
        batch_text = ''.join(self.extract_text_from_tags(line) for line in batch_lines)
        relevant: List[Dict] = []
        seen_jp = set()
        for entry in all_translations:
            if not self.validate_translation_entry(entry):
                continue
            jp_value = entry.get('jp', '').strip()
            if not jp_value or jp_value in seen_jp:
                continue
            if jp_value in batch_text or jp_value in batch_raw:
                relevant.append(entry)
                seen_jp.add(jp_value)
        if len(relevant) < target_count:
            remaining: List[Dict] = []
            for entry in all_translations:
                if not self.validate_translation_entry(entry):
                    continue
                jp_value = entry.get('jp', '').strip()
                if not jp_value or jp_value in seen_jp:
                    continue
                remaining.append(entry)
            if remaining:
                needed = min(target_count - len(relevant), len(remaining))
                if needed > 0:
                    sampled = random.sample(remaining, needed)
                    relevant.extend(sampled)
                    for item in sampled:
                        jp_value = item.get('jp', '').strip()
                        if jp_value:
                            seen_jp.add(jp_value)
        return relevant

    def create_prompt(self, lines: List[str], translation_dict: List[Dict], sound_dict: List[Dict]) -> str:
        """建立 Grok 提示詞"""
        dict_json = json.dumps(translation_dict, ensure_ascii=False, separators=(',', ':'))
        sound_json = json.dumps(sound_dict, ensure_ascii=False, separators=(',', ':'))
        content = "".join(lines)
        prompt = f"""請將下方的日文和英文內容逐行並參考上下文，姓氏、人名、地名按照翻譯對照表"translation_dictionary"的內容翻譯並潤色成繁體白話中文。分析並掃描原文，如果有發現新的姓氏、人名 (姓氏跟人名要分開) 、地名、專有名詞、術語,按相同的 JSON 格式新增至"translation_dictionary"。擬聲詞、擬態詞、感嘆詞要按照擬聲對照表"sound_dictionary"的內容翻譯並潤色成繁體白話中文。分析並掃描原文，如果有發現新的擬聲詞、擬態詞、感嘆詞，按相同的 JSON 格式新增至"sound_dictionary"。**只翻譯 HTML 標籤之間的文字節點**，**保留所有 HTML 標籤與屬性原樣** (例如 <p data-line="4">,</p> 等)，不要新增或刪除任何標籤或屬性。屬性值 (如 data-line、class、id) 請不要翻譯或修改。保留原有的換行、與標點位置。**URL (http://, https://, www.) 和 Email 地址保持原樣不翻譯**。輸出應為完整的 HTML 結構。請***只回傳新增的***"translation_dictionary"(JSON 格式) 跟***只回傳新增的***"sound_dictionary"(JSON 格式) 還有下面的繁體白話中文翻譯 (保留所有 HTML 標籤與屬性原樣)，除此之外不要增加任何東西:

translation_dictionary:
{dict_json}

sound_dictionary:
{sound_json}

原文內容:
{content}"""
        return prompt

    def parse_response(self, response_text: str) -> Tuple[List[Dict], List[Dict], str]:
        """解析 Grok 回應，提取翻譯字典、擬聲字典和翻譯內容"""
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```html\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        dict_patterns = [
            r'translation_dictionary[:\s]*\n?(\[[\s\S]*?\])',
            r'"translation_dictionary"[:\s]*\n?(\[[\s\S]*?\])',
            r'(\[\s*\{[\s\S]*?"jp"[\s\S]*?"zh"[\s\S]*?\}\s*(?:,\s*\{[\s\S]*?"jp"[\s\S]*?"zh"[\s\S]*?\}\s*)*\])',
        ]
        translation_dict = []
        dict_match = None
        dict_end = 0
        for pattern in dict_patterns:
            dict_match = re.search(pattern, response_text)
            if dict_match:
                try:
                    json_str = dict_match.group(1).strip()
                    if not json_str.startswith('['):
                        json_str = '[' + json_str
                    if not json_str.endswith(']'):
                        json_str = json_str + ']'
                    translation_dict = json.loads(json_str)
                    dict_end = dict_match.end()
                    break
                except json.JSONDecodeError:
                    continue
        sound_patterns = [
            r'sound_dictionary[:\s]*\n?(\[[\s\S]*?\])',
            r'"sound_dictionary"[:\s]*\n?(\[[\s\S]*?\])',
            r'(\[\s*\{[\s\S]*?"sound_jp"[\s\S]*?"sound_zh"[\s\S]*?\}\s*(?:,\s*\{[\s\S]*?"sound_jp"[\s\S]*?"sound_zh"[\s\S]*?\}\s*)*\])',
        ]
        sound_dict = []
        sound_match = None
        sound_end = dict_end
        for pattern in sound_patterns:
            sound_match = re.search(pattern, response_text[dict_end:])
            if sound_match:
                try:
                    json_str = sound_match.group(1).strip()
                    if not json_str.startswith('['):
                        json_str = '[' + json_str
                    if not json_str.endswith(']'):
                        json_str = json_str + ']'
                    sound_dict = json.loads(json_str)
                    sound_end = dict_end + sound_match.end()
                    break
                except json.JSONDecodeError:
                    continue
        if not translation_dict:
            jp_zh_pattern = r'\{\s*"jp"\s*:\s*"([^"]+)"\s*,\s*"zh"\s*:\s*"([^"]+)"\s*\}'
            matches = re.findall(jp_zh_pattern, response_text)
            if matches:
                translation_dict = [{"jp": jp, "zh": zh} for jp, zh in matches]
        if not sound_dict:
            sound_pattern = r'\{\s*"sound_jp"\s*:\s*"([^"]+)"\s*,\s*"sound_zh"\s*:\s*"([^"]+)"\s*\}'
            matches = re.findall(sound_pattern, response_text)
            if matches:
                sound_dict = [{"sound_jp": jp, "sound_zh": zh} for jp, zh in matches]
        translated_content = response_text
        if sound_end > 0:
            translated_content = response_text[sound_end:].strip()
        elif dict_end > 0:
            translated_content = response_text[dict_end:].strip()
        if "原文內容:" in translated_content:
            parts = translated_content.split("原文內容:", 1)
            if len(parts) > 1:
                translated_content = parts[1].strip()
        p_tags = [
            normalize_data_line_attribute(match.group(0))
            for match in P_TAG_WITH_LINE_PATTERN.finditer(translated_content)
        ]
        if p_tags:
            translated_content = '\n'.join(p_tags)
        return translation_dict, sound_dict, translated_content

    def is_refusal_response(self, response_text: str) -> bool:
        """檢測回應是否為拒絕翻譯"""
        refusal_patterns = [
            r"抱歉[,，]我無法協助",
            r"抱歉[,，]我不能協助",
            r"無法協助滿足",
            r"I cannot assist",
            r"I'm unable to",
            r"I can't help"
        ]
        for pattern in refusal_patterns:
            if re.search(pattern, response_text, re.IGNORECASE):
                return True
        return False
        
    def call_grok_api(self, prompt: str, model: str = "grok-4-fast-reasoning", max_retries: int = 3) -> str:
        """呼叫 Grok API"""
        import time
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role":"system","content":"你是一位多語言理解與繁體中文潤飾專家,融合語言學家、翻譯家與文本改寫專家的能力。當使用者輸入中文或英文或日文句子時,請逐行按以下逐步流程處理(steps)並輸出,不得輸出分析、步驟、JSON 或其他標註。","steps":[{"step":1,"instruction":"處理範圍標註:只處理並翻譯 HTML 標籤之間的文字節點,保留所有 HTML 標籤與屬性原樣(例如 <p data-line= >,</p> 等),不要新增或刪除任何標籤或屬性。屬性值(如 data-line、class、id)請不要翻譯或修改。"},{"step":2,"instruction":"形態分析:對日文或英文或中文句子的所有文字進行分詞、詞性分析、動詞活用、時態、敬語層級。標記特殊詞類:外來語、感嘆詞、擬聲詞、擬態詞、人物尊稱。"},{"step":3,"instruction":"外來語識別與羅馬字還原並翻譯: 分析辨識片假名外來語,反推其羅馬字拼音跟原本意義,再依羅馬字原本意義翻譯為繁體中文。保留原始片假名以利後續處理。"},{"step":4,"instruction":"漢字語義解析與同義詞判斷: 對日文漢字進行語義解析,判斷其在上下文中的正確意義。選擇最接近中文的意義進行替換,避免逐字或模糊翻譯。(如「勉強」、「手当」、「主人」、「愛想」、「気持ち」、「相談」、「世話」、「無理」、「仕方」、「怪我」、「面倒」等),並轉換為最貼切的中文語義。例:「勉強する」→「學習」而非「勉強」;「手当て」→「津貼/治療」依語境選。標記多義詞及對應中文意義,以利後續結構分析和翻譯。"},{"step":5,"instruction":"語法功能判定與依賴關係分析: 分析句中各成分的語法功能與依賴關係,包括主從句、修飾語、並列、轉折、插入語等。理解語序、邏輯關係與修飾層次,為後續語法角色標記、語序重組、上下文參照提供依據。標記各成分在句中作用,以利翻譯時保持語意完整與邏輯清晰。"},{"step":6,"instruction":"結構標記與語法角色轉換: 標記語法角色:主語(S)、受詞(O)、動詞(V)、補語(C)、時間(T)、地點(L)、依賴關係及語義角色。對日文助詞(如「が」、「を」、「に」、「で」等)進行中文對應轉換,確保句法邏輯正確。若句子省略主語,根據上下文補充自然中文主語。調整時間副詞位置,使其符合中文語序習慣。"},{"step":7,"instruction":"語序重組: 將日文 SOV 結構改為中文 SVO 結構。保留情緒詞或擬聲詞在句中的自然位置。"},{"step":8,"instruction":"情緒、心理、動作描寫與上下文參照: 按照擬聲對照表 sound_dictionary 的內容,將***所有文字包含日文跟英文***翻譯成現代白話繁體中文,語氣自然、易懂。感嘆詞轉換為中文語氣詞(例:あっ→啊,えっ→咦,うわっ→哇)。擬聲詞/擬態詞轉換為中文聲音或狀態描寫,保留語氣強度。標記人物心理狀態、情緒反應、動作細節、慾望、事件、地點、時間、氛圍及劇情細節。參照上下文,補充對話語氣、心理描寫與動作描寫,使翻譯更自然、生動。若無直接中文對應,可使用描述性語言呈現情緒或動作。"},{"step":9,"instruction":"敬語與人物尊稱處理: 辨識敬語(尊重語、謙讓語、丁寧語)。人物尊稱處理:- 日常對話/非正式語氣,可省略:さん、様、君、ちゃん;正式語氣可譯成先生或小姐。-正式敘述 → 轉中文頭銜或敬稱(如 老師、部長、客人)。調整語氣以符合中文自然表達。"},{"step":10,"instruction":"翻譯與潤色:將句子參考人名、地名、專有名詞、術語,按照翻譯對照表 translation_dictionary 的內容,將***所有文字***翻譯成現代白話繁體中文,語氣自然、易懂。融入步驟8標記的情緒、心理狀態、動作描寫與上下文參照。融入步驟5語法功能判定結果,保持句子邏輯清晰、語序自然。保留語氣、情緒、角色關係及句子流暢性。將人物對話、心理與動作融合,使文本生動且文學感強。確保中文句子符合語法與語序習慣,並保持上下文連貫。"},{"step":11,"instruction":"潤飾與性暗示修辭強化: ***重新分析句子，提取氣氛焦點，依照氣氛焦點加強視覺場景感、觸覺、心理感受的感官反應跟性暗示,增加曖昧互動與情緒張力和曖昧心理暗示重新生成以性暗示語調改寫，全新句子。***，提升對話、肢體動作,"},{"step":12,"instruction":"文采提升策略:語言風格優化，使用更具表現力詞彙和語法***進行重新生成帶曖昧心理暗示情並增加文字吸引力。情感表達強化，利用生動形容詞、副詞、動詞帶出的新的句子***。文化適配，將原文文化元素本土化，符合中文閱讀習慣。節奏感把握，調整句長短、停頓和韻律，提升語言流暢度。隱喻與象徵運用，選擇性增加隱喻、象徵或比喻，使句子更有深度和畫面感。"},{"step":13,"instruction":"擬聲詞改寫策略:分析並判斷句子的對話如果由多個擬聲詞/擬態詞組成,分析並提取其意義.重新生成由第三方視角依環境氣氛描寫感官與心理反應,或肢體互動融合而成的新句子，用以適配上下文.範例如下:呼吸引+聲音描寫:如「急促的呼吸、胸口微微起伏、低聲呢喃」,心理感受+聲音:如「沸騰在全身翻滾,像潮水洶湧般充盈」,肢體互動+環境描寫:如「纖細的手指緊扣被單,曲線在燈光下微微閃動」,隱喻或比喻:如「熱浪在體內蔓延,像火焰輕柔緩燒」"},{"step":14,"instruction":"清理多餘元素:檢查翻譯後句子,清理任何多餘或重複的助詞、敬語、感嘆詞、擬聲詞、擬態詞。清除多餘的空格或縮排。保留必要的語氣、情緒、心理與動作描寫，但刪除對中文自然語序或語氣造成干擾的冗餘元素。確保最終中文句子自然、流暢,語氣與情緒一致。"},{"step":15,"instruction":"文字節點輸出規範:每一行僅輸出一行經翻譯並潤色的繁體白話中文(台灣用語,自然有文采)。不可含符號、分析、JSON 或解釋。若原文語義模糊,以合理自然中文詮釋大意。結尾可用句號、問號或驚嘆號。"},{"step":16,"instruction":"最終輸出規範:將文字節點按原本格式插入回 HTML 標籤之間,保留所有 HTML 標籤與屬性原樣(例如 <p data-line= >,</p> 等),不要新增或刪除任何標籤或屬性。屬性值(如 data-line、class、id)請不要翻譯或修改。每行處理完僅輸出一行、包含 HTML 標籤的一句經翻譯潤色的繁體中文(台灣用語,自然有文采)。不可含分析、JSON 或解釋。"}],"cache_control":{"type":"ephemeral"}},{"role":"user","content":prompt}],
                    temperature=0.8,
                    timeout=120.0
                )
                return response.choices[0].message.content
            except Exception as e:
                error_msg = f"API 調用失敗 (嘗試 {attempt + 1}/{max_retries}): {type(e).__name__}: {str(e)}"
                if attempt == max_retries - 1:
                    raise Exception(error_msg)
                print(f"\n⚠️ {error_msg}，將重試...\n")
        return ""

    def remove_html_tags(self, text: str) -> str:
        """移除 HTML 標籤與屬性，清除內容中的換行符號"""
        clean_text = re.sub(r'<[^>]+>', '', text)
        clean_text = clean_text.replace('\n', '').replace('\r', '').strip()
        return clean_text

    def convert_to_plain_text(self, txt_file: Path) -> str:
        """將 HTML 格式的檔案轉換為純文字格式"""
        with open(txt_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        plain_lines = [self.remove_html_tags(line) for line in lines if self.remove_html_tags(line)]
        return '\n\n'.join(plain_lines)

    def save_single_file_to_plain_text(self, txt_file: Path):
        """處理單個檔案並立即回存到 stepaa"""
        try:
            plain_text = self.convert_to_plain_text(txt_file)
            output_file = self.stepaa_dir / txt_file.name
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(plain_text)
        except Exception:
            pass

    def update_progress_display(self):
        """更新進度顯示 (顯示正在處理的檔案詳情)"""
        import time
        with self.lock:
            current_time = time.time()
            if current_time - self.last_update_time < self.update_interval:
                return
            self.last_update_time = current_time
            total = len(self.progress_tracker)
            completed = sum(1 for p in self.progress_tracker.values() if p['status'] == 'completed')
            failed = sum(1 for p in self.progress_tracker.values() if p['status'] == 'failed')
            skipped = sum(1 for p in self.progress_tracker.values() if p['status'] == 'skipped')
            processing = sum(1 for p in self.progress_tracker.values() if p['status'] == 'processing')
            total_progress = 0
            total_lines = 0
            for prog in self.progress_tracker.values():
                if prog['total'] > 0:
                    total_progress += (prog['skipped'] + prog['success'] + prog['failed'])
                    total_lines += prog['total']
            overall_percent = (total_progress / total_lines * 100) if total_lines > 0 else 0
            processing_files = [(name, prog) for name, prog in self.progress_tracker.items() if prog['status'] == 'processing']
            use_cls = os.name == 'nt'
            if use_cls:
                os.system('cls')
            elif hasattr(self, '_last_lines_count'):
                for _ in range(self._last_lines_count):
                    print("\033[F\033[K", end='')
            lines_count = 0
            prefix = "" if use_cls else "\r"
            print(f"{prefix}📊 總進度: {overall_percent:5.1f}% | [{completed}/{total}] | ✅{completed} ⏳{processing} ❌{failed} ⬜{skipped}")
            lines_count += 1
            if processing_files:
                print("─" * 120)
                lines_count += 1
                for filename, prog in processing_files[:10]:
                    dict_count = prog['dict_count']
                    if prog['total'] > 0:
                        skipped_ratio = prog['skipped'] / prog['total']
                        success_ratio = prog['success'] / prog['total']
                        failed_ratio = prog['failed'] / prog['total']
                        pending_ratio = prog['pending'] / prog['total']
                        bar_length = 40
                        skipped_len = int(bar_length * skipped_ratio)
                        success_len = int(bar_length * success_ratio)
                        failed_len = int(bar_length * failed_ratio)
                        pending_len = bar_length - skipped_len - success_len - failed_len
                        bar = (
                            '\033[37m' + '█' * skipped_len + '\033[0m' +
                            '\033[92m' + '█' * success_len + '\033[0m' +
                            '\033[91m' + '█' * failed_len + '\033[0m' +
                            '\033[90m' + '░' * pending_len + '\033[0m'
                        )
                        display_name = filename[:17] + '...' if len(filename) > 20 else filename.ljust(20)
                        print(f"⏳ {display_name} [{bar}] | 已:{prog['skipped']:4d} 成:{prog['success']:4d} 敗:{prog['failed']:4d} 待:{prog['pending']:4d} | 📚{dict_count:3d}")
                        lines_count += 1
                if len(processing_files) > 10:
                    print(f"... 還有 {len(processing_files) - 10} 個檔案正在處理")
                    lines_count += 1
            self._last_lines_count = lines_count
            print(end='', flush=True)

    def init_progress(self, filename: str, total_lines: int, translation_lines: int):
        """初始化檔案進度"""
        with self.lock:
            self.progress_tracker[filename] = {
                'total': total_lines,
                'translation_total': translation_lines,
                'skipped': total_lines - translation_lines,
                'success': 0,
                'failed': 0,
                'pending': translation_lines,
                'dict_count': 0,
                'status': 'processing'
            }

    def update_progress(self, filename: str, success: int, failed: int, pending: int):
        """更新檔案進度"""
        with self.lock:
            if filename in self.progress_tracker:
                self.progress_tracker[filename]['success'] = success
                self.progress_tracker[filename]['failed'] = failed
                self.progress_tracker[filename]['pending'] = pending
                if self.progress_tracker[filename]['status'] == 'waiting':
                    self.progress_tracker[filename]['status'] = 'processing'

    def complete_progress(self, filename: str, status: str = 'completed'):
        """標記檔案完成"""
        with self.lock:
            if filename in self.progress_tracker:
                self.progress_tracker[filename]['status'] = status

    def update_dict_count(self, filename: str, count: int):
        """更新字典統計"""
        with self.lock:
            if filename in self.progress_tracker:
                self.progress_tracker[filename]['dict_count'] = count

    def print_detailed_summary(self):
        """打印詳細的完成摘要"""
        with self.lock:
            print("\n\n" + "=" * 80)
            print("📋 處理詳細摘要")
            print("=" * 80)
            completed_files = []
            failed_files = []
            skipped_files = []
            for filename, progress in self.progress_tracker.items():
                if progress['status'] == 'completed':
                    completed_files.append((filename, progress))
                elif progress['status'] == 'failed':
                    failed_files.append((filename, progress))
                elif progress['status'] == 'skipped':
                    skipped_files.append((filename, progress))
            if completed_files:
                print(f"\n✅ 完成的檔案 ({len(completed_files)} 個):")
                for filename, progress in completed_files[:20]:
                    success_rate = (progress['success'] / progress['translation_total'] * 100) if progress['translation_total'] > 0 else 100.0
                    print(f"  • {filename:40s} 成功率:{success_rate:5.1f}% ({progress['success']}/{progress['translation_total']}) 📚:{progress['dict_count']}")
                if len(completed_files) > 20:
                    print(f"  ... 還有 {len(completed_files) - 20} 個檔案")
            if failed_files:
                print(f"\n❌ 失敗的檔案 ({len(failed_files)} 個):")
                for filename, progress in failed_files:
                    print(f"  • {filename}")
            if skipped_files:
                print(f"\n⬜ 跳過的檔案 ({len(skipped_files)} 個，無需翻譯的內容)")
                for filename, progress in skipped_files[:10]:
                    print(f"  • {filename}")
                if len(skipped_files) > 10:
                    print(f"  ... 還有 {len(skipped_files) - 10} 個檔案")
            print("=" * 80)

    def process_file(self, txt_file: Path) -> Dict:
        """處理單個文字檔案並返回統計資訊"""
        result = {
            'filename': txt_file.name,
            'total_lines': 0,
            'japanese_lines': 0,
            'success': 0,
            'failed': 0,
            'status': 'success'
        }
        try:
            try:
                with open(txt_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except Exception as e:
                print(f"\n❌ 讀取檔案失敗: {txt_file.name}")
                print(f"   錯誤: {str(e)}\n")
                result['status'] = 'failed'
                self.complete_progress(txt_file.name, 'failed')
                return result
            japanese_lines = self.get_translation_lines(lines)
            total_japanese_lines = len(japanese_lines)
            total_lines = len(lines)
            result['total_lines'] = total_lines
            result['japanese_lines'] = total_japanese_lines
            if total_japanese_lines == 0:
                result['status'] = 'skipped'
                self.complete_progress(txt_file.name, 'skipped')
                return result
            self.init_progress(txt_file.name, total_lines, total_japanese_lines)
            json_file = self.stepc_dir / f"{txt_file.stem}.json"
            translation_dict_full = self.load_translation_dictionary(json_file)
            sound_dict_global = self.load_sound_dictionary()
            self.update_dict_count(txt_file.name, len(translation_dict_full))
            self.update_progress_display()
            num_batches = (total_japanese_lines + self.batch_size - 1) // self.batch_size
            total_success = 0
            total_failed = 0
            for batch_idx in range(num_batches):
                try:
                    start_idx = batch_idx * self.batch_size
                    end_idx = min(start_idx + self.batch_size, total_japanese_lines)
                    batch_data = japanese_lines[start_idx:end_idx]
                    batch_indices = [item[0] for item in batch_data]
                    batch_lines = [item[1] for item in batch_data]
                    batch_html_nums = [item[2] for item in batch_data]
                    first_html_num = batch_html_nums[0] if batch_html_nums[0] != -1 else 0
                    if batch_idx > 0:
                        translation_dict_full = self.load_translation_dictionary(json_file)
                    sound_dict_global = self.load_sound_dictionary()
                    relevant_translations = self.select_relevant_translations(
                        batch_lines,
                        translation_dict_full,
                        target_count=5
                    )
                    relevant_sounds = self.select_relevant_sounds(batch_lines, sound_dict_global, min_count=3)
                    prompt = self.create_prompt(batch_lines, relevant_translations, relevant_sounds)
                    request_file = self.stepe_dir / f"{txt_file.stem}_V01_{first_html_num:08d}.txt"
                    with open(request_file, 'w', encoding='utf-8') as f:
                        f.write(prompt)
                    try:
                        response_text = self.call_grok_api(prompt)
                        if self.is_refusal_response(response_text):
                            error_file = self.stepg_dir / f"{txt_file.stem}_V01_{first_html_num:08d}.txt"
                            error_content = f"""API 拒絕翻譯
{'='*70}
批次資訊:
  檔案: {txt_file.name}
  批次: {batch_idx + 1}/{num_batches}
  HTML 行號: {first_html_num}

拒絕回應:
{response_text}

{'='*70}
原始 Request:
{prompt}
"""
                            with open(error_file, 'w', encoding='utf-8') as f:
                                f.write(error_content)
                            batch_failed_count = len([idx for idx in batch_html_nums if idx != -1])
                            total_failed += batch_failed_count
                            result['failed'] += batch_failed_count
                            pending = total_japanese_lines - end_idx
                            self.update_progress(txt_file.name, total_success, total_failed, pending)
                            self.update_progress_display()
                            continue
                        response_file = self.stepf_dir / f"{txt_file.stem}_V01_{first_html_num:08d}.txt"
                        with open(response_file, 'w', encoding='utf-8') as f:
                            f.write(response_text)
                        new_dict, new_sound_dict, translated_content = self.parse_response(response_text)
                        with self.lock:
                            if new_dict:
                                translation_dict_full = self.merge_dictionaries(
                                    translation_dict_full,
                                    new_dict
                                )
                                self.save_translation_dictionary(json_file, translation_dict_full)
                                self.update_dict_count(txt_file.name, len(translation_dict_full))
                        with self.lock:
                            if new_sound_dict:
                                sound_dict_global = self.load_sound_dictionary()
                                sound_dict_global = self.merge_sound_dictionaries(sound_dict_global, new_sound_dict)
                                self.save_sound_dictionary(sound_dict_global)
                        line_translation_map = {}
                        for match in P_TAG_WITH_LINE_PATTERN.finditer(translated_content):
                            line_num = int(match.group("line"))
                            line_html = normalize_data_line_attribute(match.group(0))
                            line_translation_map[line_num] = line_html
                        batch_success = 0
                        batch_failed = 0
                        for i in range(len(batch_indices)):
                            original_idx = batch_indices[i]
                            html_line_num = batch_html_nums[i]
                            if html_line_num == -1:
                                continue
                            if html_line_num not in line_translation_map:
                                batch_failed += 1
                                continue
                            translated_line = normalize_data_line_attribute(
                                line_translation_map[html_line_num]
                            )
                            if not translated_line.strip():
                                batch_failed += 1
                                continue
                            if not translated_line.endswith('\n'):
                                translated_line += '\n'
                            text_content = self.extract_text_from_tags(translated_line)
                            if self.contains_japanese(text_content) or self.contains_english(text_content):
                                batch_failed += 1
                            else:
                                batch_success += 1
                            lines[original_idx] = translated_line
                        total_success += batch_success
                        total_failed += batch_failed
                        result['success'] += batch_success
                        result['failed'] += batch_failed
                        pending = total_japanese_lines - end_idx
                        self.update_progress(txt_file.name, total_success, total_failed, pending)
                        self.update_progress_display()
                        with open(txt_file, 'w', encoding='utf-8') as f:
                            f.writelines(lines)
                    except Exception as e:
                        error_file = self.stepg_dir / f"{txt_file.stem}_V01_{first_html_num:08d}.txt"
                        error_content = f"""API 呼叫失敗記錄
{'='*70}
批次資訊:
  檔案: {txt_file.name}
  批次: {batch_idx + 1}/{num_batches}
  HTML 行號: {first_html_num}

錯誤資訊:
  錯誤類型: {type(e).__name__}
  錯誤訊息: {str(e)}

{'='*70}
原始 Request:
{prompt}
"""
                        with open(error_file, 'w', encoding='utf-8') as f:
                            f.write(error_content)
                        batch_failed_count = len([idx for idx in batch_html_nums if idx != -1])
                        total_failed += batch_failed_count
                        result['failed'] += batch_failed_count
                        pending = total_japanese_lines - end_idx
                        self.update_progress(txt_file.name, total_success, total_failed, pending)
                        self.update_progress_display()
                        continue
                except Exception as batch_error:
                    print(f"\n⚠️ 批次處理異常 [{txt_file.name}] 批次 {batch_idx + 1}/{num_batches}")
                    print(f"   錯誤: {type(batch_error).__name__}: {str(batch_error)}\n")
                    batch_failed_count = len(batch_data)
                    total_failed += batch_failed_count
                    result['failed'] += batch_failed_count
                    end_idx = min((batch_idx + 1) * self.batch_size, total_japanese_lines)
                    pending = total_japanese_lines - end_idx
                    self.update_progress(txt_file.name, total_success, total_failed, pending)
                    self.update_progress_display()
                    continue
            self.complete_progress(txt_file.name, 'completed')
            self.update_progress_display()
            try:
                self.save_single_file_to_plain_text(txt_file)
            except Exception as e:
                print(f"\n⚠️ 儲存純文字失敗: {txt_file.name}")
                print(f"   錯誤: {str(e)}\n")
            if result['failed'] > 0:
                result['status'] = 'partial'
        except Exception as e:
            print(f"\n❌ 處理檔案時發生嚴重錯誤: {txt_file.name}")
            print(f"   錯誤類型: {type(e).__name__}")
            print(f"   錯誤訊息: {str(e)}")
            import traceback
            print(f"   堆疊追蹤:\n{traceback.format_exc()}\n")
            self.complete_progress(txt_file.name, 'failed')
            self.update_progress_display()
            result['status'] = 'failed'
        return result

    def process_all_files(self):
        """並行處理 stepd 目錄下所有的 txt 檔案"""
        self.clear_processing_directories()
        txt_files = list(self.stepd_dir.glob("*.txt"))
        if not txt_files:
            print("❌ 在 stepd 目錄中找不到 txt 檔案")
            return
        print(f"\n{'#'*70}")
        print(f"🚀 開始並行翻譯處理 (並行數: {self.max_workers})")
        print(f"{'#'*70}")
        print(f"🤖 使用模型: grok-4-fast-reasoning")
        print(f"📂 找到 {len(txt_files)} 個檔案待處理")
        print(f"📦 批次大小: {self.batch_size} 行/批次")
        print(f"🔊 擬聲字典: stepc/sound_dictionary.json (全局共享)")
        print(f"{'#'*70}")
        for txt_file in txt_files:
            self.progress_tracker[txt_file.name] = {
                'total': 0,
                'translation_total': 0,
                'skipped': 0,
                'success': 0,
                'failed': 0,
                'pending': 0,
                'dict_count': 0,
                'status': 'waiting'
            }
        self.update_progress_display()
        results = []
        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_file = {executor.submit(self.process_file, txt_file): txt_file for txt_file in txt_files}
                for future in as_completed(future_to_file):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        txt_file = future_to_file[future]
                        print(f"\n❌ 執行緒異常: {txt_file.name}")
                        print(f"   錯誤: {type(e).__name__}: {str(e)}\n")
                        results.append({
                            'filename': txt_file.name,
                            'status': 'failed',
                            'total_lines': 0,
                            'japanese_lines': 0,
                            'success': 0,
                            'failed': 0
                        })
        except Exception as e:
            print(f"\n❌ 執行緒池異常:")
            print(f"   錯誤: {type(e).__name__}: {str(e)}\n")
            import traceback
            print(f"   堆疊追蹤:\n{traceback.format_exc()}\n")
        print("\n")
        self.print_detailed_summary()
        print()
        total_success = sum(1 for r in results if r['status'] == 'success')
        total_partial = sum(1 for r in results if r['status'] == 'partial')
        total_failed = sum(1 for r in results if r['status'] == 'failed')
        total_skipped = sum(1 for r in results if r['status'] == 'skipped')
        print(f"{'#'*70}")
        print(f"🎉 全部翻譯處理完成!")
        print(f"{'#'*70}")
        print(f"總檔案: {len(txt_files)} 檔 | 完全成功: {total_success} 檔 | 部分失敗: {total_partial} 檔 | 完全失敗: {total_failed} 檔 | 跳過: {total_skipped} 檔")
        print(f"{'#'*70}")
        print(f"\n📂 輸出檔案位置:")
        print(f"  ├─ stepc/  - 更新後的翻譯對照表")
        print(f"  │  └─ sound_dictionary.json - 全局擬聲詞對照表 🔊")
        print(f"  ├─ stepd/  - 翻譯後的 HTML 檔案")
        print(f"  ├─ stepe/  - API Request 記錄")
        print(f"  ├─ stepf/  - 成功的 Response")
        print(f"  ├─ stepg/  - 失敗的 Response")
        print(f"  └─ stepaa/ - 最終純文字檔案 ⭐")
        print(f"\n💡 提示: 純文字檔案位於 stepaa/ 目錄，可直接使用!\n")


def main():
    """主程式入口"""
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        print("❌ 請設定 XAI_API_KEY 環境變數或在程式碼中直接設定")
        print("\n設定方法:")
        print("  方法 1 - 環境變數:")
        print("    Linux/Mac: export XAI_API_KEY='your-api-key'")
        print("    Windows: set XAI_API_KEY=your-api-key")
        print("\n  方法 2 - 直接在程式碼中設定:")
        print("    api_key = 'your-api-key-here'")
        return
    print(f"\n{'#'*70}")
    print("  Grok 多語言翻譯自動化處理系統")
    print("  版本: 6.0 (新增 sound_dictionary 功能)")
    print("  模型: grok-4-fast-reasoning")
    print("  並行數: 10 個檔案")
    print("  批次大小: 20 行/批次")
    print("  翻譯語言: 日文、英文 (小寫) → 繁體中文")
    print("  擬聲詞庫: 全局共享，五十音排序 🔊")
    print(f"{'#'*70}\n")
    processor = TranslationBatchProcessor(api_key=api_key, batch_size=20, max_workers=10)
    processor.process_all_files()
    print(f"\n{'#'*70}")
    print("  🎊 所有處理流程完成!")
    print(f"{'#'*70}\n")


if __name__ == "__main__":
    main()

