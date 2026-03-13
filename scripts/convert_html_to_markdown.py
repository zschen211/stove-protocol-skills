import os
from pathlib import Path
from typing import List

from bs4 import BeautifulSoup, NavigableString, Tag


# 项目根目录：scripts/ 的上一级
PROJECT_ROOT = Path(__file__).resolve().parent.parent
HTML_ROOT = PROJECT_ROOT / "output"
MD_ROOT = PROJECT_ROOT / "api-desc"


def _inline_to_markdown(node: Tag | NavigableString) -> str:
    """将行内节点转换为 markdown 文本。"""
    if isinstance(node, NavigableString):
        return str(node)

    text_parts: List[str] = []
    name = node.name

    if name in {"strong", "b"}:
        inner = "".join(_inline_to_markdown(child) for child in node.children)
        return f"**{inner}**"

    if name in {"em", "i"}:
        inner = "".join(_inline_to_markdown(child) for child in node.children)
        return f"*{inner}*"

    if name == "code":
        inner = "".join(_inline_to_markdown(child) for child in node.children)
        return f"`{inner}`"

    if name == "a":
        inner = "".join(_inline_to_markdown(child) for child in node.children)
        href = node.get("href", "").strip()
        if href:
            return f"[{inner}]({href})"
        return inner

    # 其他行内标签，递归拼接子节点文本
    for child in node.children:
        text_parts.append(_inline_to_markdown(child))

    return "".join(text_parts)


def _table_to_markdown(table: Tag) -> str:
    """将 <table> 转换为 markdown 表格。"""
    headers: List[str] = []
    rows: List[List[str]] = []

    thead = table.find("thead")
    if thead:
        head_tr = thead.find("tr")
        if head_tr:
            for th in head_tr.find_all(["th", "td"]):
                headers.append(_inline_to_markdown(th).strip())

    tbody = table.find("tbody") or table
    for tr in tbody.find_all("tr"):
        row: List[str] = []
        for td in tr.find_all(["td", "th"]):
            row.append(_inline_to_markdown(td).strip())
        if row:
            rows.append(row)

    if not headers and rows:
        headers = [f"col{i+1}" for i in range(len(rows[0]))]

    if not headers:
        return ""

    lines: List[str] = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        cells = row + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def _list_to_markdown(ul_or_ol: Tag) -> str:
    """将 <ul>/<ol> 转换为 markdown 列表。"""
    ordered = ul_or_ol.name == "ol"
    lines: List[str] = []

    index = 1
    for li in ul_or_ol.find_all("li", recursive=False):
        prefix = f"{index}." if ordered else "-"
        content = "".join(_inline_to_markdown(child) for child in li.children)
        content = content.strip()
        if content:
            lines.append(f"{prefix} {content}")
        index += 1

    return "\n".join(lines)


def html_to_markdown(html: str) -> str:
    """将 Stove 文档页面（精简版 HTML）转换为 markdown 文本。"""
    soup = BeautifulSoup(html, "html.parser")

    root = soup.find("div", class_="vp-doc")
    if root is None:
        # 兜底：直接返回纯文本
        body = soup.find("body")
        return body.get_text("\n", strip=True) if body else soup.get_text("\n", strip=True)

    # 实际内容在内部的第一个 <div> 中
    inner = root.find("div") or root

    blocks: List[str] = []

    for child in inner.children:
        if isinstance(child, NavigableString):
            if not child.string or not child.string.strip():
                continue
            blocks.append(child.strip())
            continue

        name = child.name

        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            prefix = "#" * level
            text = _inline_to_markdown(child).strip()
            blocks.append(f"{prefix} {text}")
            continue

        # 代码块容器：div.language-xxx > pre > code
        classes = child.get("class") or []
        language = None
        for cls in classes:
            if cls.startswith("language-"):
                language = cls.removeprefix("language-")
                break
        if language:
            pre = child.find("pre")
            if pre:
                code_text = pre.get_text("", strip=False)
                fence_lang = language or ""
                blocks.append(f"```{fence_lang}\n{code_text}\n```")
                continue

        if name == "p":
            text = _inline_to_markdown(child).strip()
            if text:
                blocks.append(text)
            continue

        if name in {"ul", "ol"}:
            md_list = _list_to_markdown(child)
            if md_list:
                blocks.append(md_list)
            continue

        if name == "table":
            table_md = _table_to_markdown(child)
            if table_md:
                blocks.append(table_md)
            continue

        if name == "hr":
            blocks.append("---")
            continue

        # 其他不常见块级元素，退化为纯文本
        text = child.get_text("\n", strip=True)
        if text:
            blocks.append(text)

    return "\n\n".join(blocks).rstrip() + "\n"


def convert_all() -> None:
    """遍历 output/ 下的 html 文件，全部转换为 markdown。"""
    if not HTML_ROOT.exists():
        raise SystemExit(f"HTML root not found: {HTML_ROOT}")

    for category in ("public", "maker", "taker"):
        html_dir = HTML_ROOT / category
        if not html_dir.exists():
            continue

        md_dir = MD_ROOT / category
        os.makedirs(md_dir, exist_ok=True)

        for html_path in html_dir.glob("*.html"):
            md_path = md_dir / (html_path.stem + ".md")
            with html_path.open("r", encoding="utf-8") as f:
                html = f.read()

            markdown = html_to_markdown(html)

            with md_path.open("w", encoding="utf-8") as f:
                f.write(markdown)

            print(f"Converted {html_path.relative_to(PROJECT_ROOT)} -> {md_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    convert_all()

