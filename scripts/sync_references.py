import re
from pathlib import Path
from typing import Dict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_DESC_ROOT = PROJECT_ROOT / "api-desc"

SKILL_REF_MAP: Dict[str, Path] = {
    "public": PROJECT_ROOT / "skills" / "stove-public-api" / "references",
    "maker": PROJECT_ROOT / "skills" / "stove-maker-api" / "references",
    "taker": PROJECT_ROOT / "skills" / "stove-taker-api" / "references",
}


def extract_title(md_path: Path) -> str:
    """Extract the first level-1 heading (# ...) as title."""
    text = md_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            # 形如: "# Query Maker Positions [​](#anchor)"
            content = line[2:].strip()
            # 去掉后面的链接部分
            if " [" in content:
                content = content.split(" [", 1)[0].strip()
            return content or md_path.stem
    return md_path.stem


def sanitize_filename(title: str) -> str:
    """Make a safe filename from title,尽量保持可读."""
    # 替换路径分隔符
    title = title.replace("/", "-").replace("\\", "-")
    # 去掉首尾空白
    title = title.strip()
    # 控制长度防止极端长标题
    if len(title) > 120:
        title = title[:120].rstrip()
    return title or "untitled"


def main() -> None:
    if not API_DESC_ROOT.exists():
        raise SystemExit(f"api-desc directory not found at {API_DESC_ROOT}")

    for category, target_dir in SKILL_REF_MAP.items():
        src_dir = API_DESC_ROOT / category
        if not src_dir.exists():
            continue
        target_dir.mkdir(parents=True, exist_ok=True)

        for md_path in src_dir.glob("*.md"):
            content = md_path.read_text(encoding="utf-8")
            if not content.strip():
                # 源文档为空，则跳过，不复制
                continue

            title = extract_title(md_path)
            fname = sanitize_filename(title) + ".md"
            dest = target_dir / fname
            dest.write_text(content, encoding="utf-8")
            print(f"Copied {md_path.relative_to(PROJECT_ROOT)} -> {dest.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

