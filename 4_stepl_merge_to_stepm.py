from __future__ import annotations

import html
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent
INPUT_DIR = PROJECT_ROOT / "stepl"
OUTPUT_DIR = PROJECT_ROOT / "stepm"
OUTPUT_FILE = OUTPUT_DIR / "output.txt"

P_TAG_PATTERN = re.compile(
    r"<p\b[^>]*\bdata-line\s*=\s*(?:\\?['\"])?(?P<line>\d+)(?:\\?['\"])?[^>]*>(?P<content>.*?)</p>",
    re.IGNORECASE | re.DOTALL,
)
TAG_PATTERN = re.compile(r"<[^>]+>")


def strip_tags(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    no_tags = TAG_PATTERN.sub("", text)
    return html.unescape(no_tags).strip()


def parse_file(path: Path) -> Dict[int, List[str]]:
    """Return a mapping of data-line numbers to paragraph content for a file."""
    content = path.read_text(encoding="utf-8-sig")
    entries: Dict[int, List[str]] = defaultdict(list)

    for match in P_TAG_PATTERN.finditer(content):
        line_no = int(match.group("line"))
        paragraph = match.group("content").strip()
        if paragraph:
            entries[line_no].append(paragraph)

    return entries


def interleave_lines(
    files_data: List[Tuple[str, Dict[int, List[str]]]]
) -> Iterable[str]:
    """Yield interleaved paragraphs grouped by data-line."""
    all_line_numbers = set()
    for _, mapping in files_data:
        all_line_numbers.update(mapping.keys())

    for line_no in sorted(all_line_numbers):
        for _, mapping in files_data:
            paragraphs = mapping.get(line_no, [])
            for paragraph in paragraphs:
                cleaned = strip_tags(paragraph)
                if cleaned:
                    yield cleaned
        yield ""


def main() -> None:
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"Input directory not found: {INPUT_DIR}")

    txt_files = sorted(
        (path for path in INPUT_DIR.glob("*.txt") if path.is_file()),
        key=lambda p: p.name.lower(),
    )

    if not txt_files:
        print(f"No .txt files found under {INPUT_DIR}")
        return

    files_data = [(path.name, parse_file(path)) for path in txt_files]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    interleaved_lines = list(interleave_lines(files_data))
    if interleaved_lines and not interleaved_lines[-1]:
        interleaved_lines = interleaved_lines[:-1]

    OUTPUT_FILE.write_text("\n".join(interleaved_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
