from __future__ import annotations

import json
from pathlib import Path


def clean_sound_dictionary(json_path: Path) -> int:
    """Remove entries where sound_jp and sound_zh are identical; return removed count."""
    with json_path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    if not isinstance(data, list):
        raise ValueError(f"{json_path} does not contain a JSON array")

    original_len = len(data)
    filtered = [entry for entry in data if entry.get("sound_jp") != entry.get("sound_zh")]
    removed = original_len - len(filtered)

    if removed:
        with json_path.open("w", encoding="utf-8") as fp:
            json.dump(filtered, fp, ensure_ascii=False, indent=2)
            fp.write("\n")

    return removed


def main() -> None:
    base_dir = Path(__file__).resolve().parent / "stepc"
    if not base_dir.is_dir():
        raise FileNotFoundError(f"找不到目錄: {base_dir}")

    total_removed = 0
    targets = sorted(base_dir.glob("sound_dictionary*.json"))

    if not targets:
        raise FileNotFoundError(f"在 {base_dir} 找不到 sound_dictionary*.json 檔案")

    for json_path in targets:
        removed = clean_sound_dictionary(json_path)
        total_removed += removed
        print(f"{json_path}: 移除 {removed} 筆資料")

    print(f"總共移除 {total_removed} 筆資料")


if __name__ == "__main__":
    main()
