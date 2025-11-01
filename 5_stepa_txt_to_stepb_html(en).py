import os
import json
from pathlib import Path

def convert_to_long_path(path):
    """
    將 Windows 路徑轉換為長路徑格式以避免 MAX_PATH 問題
    在 Windows 系統中，路徑前綴 \\?\ 可以支援超過 260 字元的路徑
    """
    abs_path = os.path.abspath(path)
    if os.name == 'nt' and not abs_path.startswith('\\\\?\\'):
        if abs_path.startswith('\\\\'):
            # UNC 路徑
            return '\\\\?\\UNC\\' + abs_path[2:]
        else:
            # 一般路徑
            return '\\\\?\\' + abs_path
    return abs_path

def process_txt_file(input_path, output_path):
    """
    處理單個 txt 檔案：
    1. 去除空白行
    2. 修剪每行首尾空格
    3. 為每行加上 <p> 標籤和 data-line 屬性
    """
    try:
        # 使用長路徑格式讀取檔案
        long_input_path = convert_to_long_path(input_path)
        
        # 讀取檔案內容（UTF-8 編碼）
        with open(long_input_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 處理每一行
        processed_lines = []
        line_number = 1
        
        for line in lines:
            # 修剪首尾空格
            stripped_line = line.strip()
            
            # 跳過空白行
            if not stripped_line:
                continue
            
            # 加上 <p> 標籤和 data-line 屬性
            formatted_line = f'<p data-line="{line_number}">{stripped_line}</p>\n'
            processed_lines.append(formatted_line)
            line_number += 1
        
        # 使用長路徑格式寫入檔案
        long_output_path = convert_to_long_path(output_path)
        
        # 確保輸出目錄存在
        output_dir = os.path.dirname(long_output_path)
        os.makedirs(output_dir, exist_ok=True)
        
        # 寫入處理後的內容（UTF-8 編碼）
        with open(long_output_path, 'w', encoding='utf-8') as f:
            f.writelines(processed_lines)
        
        print(f"已處理: {input_path} -> {output_path}")
        return True
        
    except Exception as e:
        print(f"處理檔案時發生錯誤 {input_path}: {str(e)}")
        return False

def create_default_json(output_path):
    """
    建立預設的 JSON 檔案，包含英文-中文對照的預設資料
    """
    default_data = [{"en": "Adam", "zh": "亞當"}, {"en": "Ahn", "zh": "安"}, {"en": "Alice", "zh": "愛莉絲"}, {"en": "Alicia", "zh": "艾莉西亞"}, {"en": "Alberta", "zh": "阿爾伯塔"}]
    
    try:
        # 使用長路徑格式寫入檔案
        long_output_path = convert_to_long_path(output_path)
        
        # 確保輸出目錄存在
        output_dir = os.path.dirname(long_output_path)
        os.makedirs(output_dir, exist_ok=True)
        
        # 寫入 JSON 檔案（UTF-8 編碼，緊湊格式）
        with open(long_output_path, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, ensure_ascii=False, separators=(',', ':'))
        
        print(f"已建立 JSON: {output_path}")
        return True
        
    except Exception as e:
        print(f"建立 JSON 檔案時發生錯誤 {output_path}: {str(e)}")
        return False

def main():
    """
    主程式：
    1. 處理 stepa 子目錄下的所有 txt 檔案，生成 HTML 格式到 stepb
    2. 為每個 txt 檔案生成預設 JSON 到 stepc
    """
    # 定義輸入和輸出目錄（相對路徑）
    input_dir = 'stepa'
    html_output_dir = 'stepb'
    json_output_dir = 'stepc'
    
    # 檢查輸入目錄是否存在
    if not os.path.exists(input_dir):
        print(f"錯誤: 找不到輸入目錄 '{input_dir}'")
        print(f"請確保在執行此程式前已建立 '{input_dir}' 目錄")
        return
    
    # 確保輸出目錄存在
    os.makedirs(html_output_dir, exist_ok=True)
    os.makedirs(json_output_dir, exist_ok=True)
    
    # 取得所有 txt 檔案
    txt_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.txt')]
    
    if not txt_files:
        print(f"在 '{input_dir}' 目錄中沒有找到 txt 檔案")
        return
    
    print(f"找到 {len(txt_files)} 個 txt 檔案")
    print("開始處理...\n")
    
    # 處理每個 txt 檔案
    html_success_count = 0
    json_success_count = 0
    
    for txt_file in txt_files:
        # 處理 HTML 輸出（stepb）
        input_path = os.path.join(input_dir, txt_file)
        html_output_path = os.path.join(html_output_dir, txt_file)
        
        if process_txt_file(input_path, html_output_path):
            html_success_count += 1
        
        # 處理 JSON 輸出（stepc）
        # 將 .txt 副檔名改為 .json
        json_filename = os.path.splitext(txt_file)[0] + '.json'
        json_output_path = os.path.join(json_output_dir, json_filename)
        
        if create_default_json(json_output_path):
            json_success_count += 1
    
    print(f"\n處理完成！")
    print(f"HTML 檔案: 成功處理 {html_success_count}/{len(txt_files)} 個檔案 (stepb)")
    print(f"JSON 檔案: 成功建立 {json_success_count}/{len(txt_files)} 個檔案 (stepc)")

if __name__ == '__main__':
    main()