from __future__ import annotations

import argparse
import json
import re
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "fanqie_public_candidates.json"


def fetch(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 public-candidate-demo/1.0",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    with urlopen(req, timeout=10) as response:
        return response.read().decode("utf-8", errors="ignore")


def clean(text: str) -> str:
    text = re.sub(r"<script.*?</script>", "", text, flags=re.S)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def first(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.S)
        if match:
            return clean(match.group(1))[:400]
    return ""


def parse_candidate(url: str, html: str) -> dict:
    text = clean(html)
    title = first([
        r"<title>(.*?)_番茄小说",
        r"<title>(.*?)</title>",
        r'"bookName"\s*:\s*"([^"]+)"',
        r'"name"\s*:\s*"([^"]+)"',
    ], html)
    title = re.sub(r"_番茄小说.*$", "", title).strip() or text[:20]
    author = first([r'"author"\s*:\s*"([^"]+)"', r"作者[:：]\s*([^ ]+)"], html)
    intro = first([
        r'"description"\s*:\s*"([^"]+)"',
        r'"abstract"\s*:\s*"([^"]+)"',
        r"简介[:：]\s*(.{20,260})",
    ], html)
    book_id = first([r"/page/(\d+)", r"/keyword/(\d+)"], url)
    tags = []
    for word in ["规则怪谈", "诡异", "悬疑", "恐怖", "无限", "副本", "求生", "末世", "直播", "系统", "女强"]:
        if word in text and word not in tags:
            tags.append(word)
    return {
        "book_id": book_id or url,
        "title": title,
        "author": author,
        "source_url": url,
        "source_type": "public_page",
        "status": "公开页面抓取",
        "category": " / ".join(tags[:3]),
        "word_count_text": first([r"([\d.]+万字)"], text),
        "reader_count_text": first([r"([\d.]+万人在读)"], text),
        "intro": intro or "公开页面已抓取，简介字段需人工复核。",
        "tags": tags,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="低频抓取番茄公开页面，扩充本地公开候选池。")
    parser.add_argument("urls", nargs="+", help="公开书籍页或关键词页 URL")
    args = parser.parse_args()

    existing = []
    if OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8"))
    by_key = {item.get("book_id") or item.get("source_url"): item for item in existing}
    for url in args.urls:
        html = fetch(url)
        item = parse_candidate(url, html)
        by_key[item.get("book_id") or url] = item
        print(f"saved: {item['title']} <- {url}")
    OUT.write_text(json.dumps(list(by_key.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
