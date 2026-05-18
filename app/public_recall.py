from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .fanqie_recommender import load_feedback, load_profile


SEED_PATH = Path(__file__).with_name("public_candidates_seed.json")
CACHE_PATH = Path(__file__).with_name("fanqie_public_candidates.json")

INTEREST_WORDS = {
    "规则怪谈": ["规则", "怪谈", "隐藏规则"],
    "悬疑恐怖": ["诡异", "恐怖", "惊悚", "灵异", "诡舍"],
    "末世求生": ["末世", "求生", "生存", "公路"],
    "无限/副本": ["无限", "副本", "游戏入侵"],
    "反套路/邪神养成": ["邪神", "反套路", "Boss"],
    "强悬念": ["强悬念", "悬疑", "隐藏提示"],
    "高压求生": ["高压", "生存", "求生"],
    "主角能力/推演": ["推演", "提示", "能力"],
}

NEGATIVE_TYPE_TO_LABELS = {
    "简介不符": ["简介兑现风险"],
    "节奏太慢": ["慢热风险"],
    "设定老套": ["套路重复风险"],
    "主角降智": ["主角智商风险"],
    "文笔不适": ["文风适配风险"],
    "恐怖氛围不够": ["氛围强度风险"],
    "感情线不喜欢": ["感情线干扰风险"],
}


def _read_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def public_candidates() -> list[dict]:
    seen = set()
    items = []
    for book in _read_json_list(SEED_PATH) + _read_json_list(CACHE_PATH):
        key = book.get("book_id") or book.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(book)
    return items


def _profile_keywords(profile: dict) -> list[str]:
    labels = []
    for book in profile.get("high_love_books", []):
        labels.extend(book.get("inferred_genres", []))
        labels.extend(book.get("inferred_tags", []))
    for item in profile.get("preferred_style_tags", []):
        if isinstance(item, (list, tuple)) and item:
            labels.append(item[0])
        else:
            labels.append(item)
    for item in profile.get("favorite_genres", []):
        if isinstance(item, (list, tuple)) and item:
            labels.append(item[0])
        else:
            labels.append(item)

    counter = Counter(label for label in labels if label and label != "其他")
    keywords = []
    for label, _ in counter.most_common(8):
        for word in INTEREST_WORDS.get(label, [label]):
            if word not in keywords:
                keywords.append(word)
    return keywords[:10]


def _candidate_text(book: dict) -> str:
    parts = [
        book.get("title", ""),
        book.get("category", ""),
        book.get("intro", ""),
        " ".join(book.get("tags", [])),
    ]
    return " ".join(parts)


def _candidate_labels(book: dict) -> list[str]:
    text = _candidate_text(book)
    labels = set(book.get("tags", []))
    for label, words in INTEREST_WORDS.items():
        if any(word in text for word in words):
            labels.add(label)
    return list(labels)


def _parse_word_count(text: str) -> float:
    match = re.search(r"([\d.]+)\s*万", text or "")
    if not match:
        return 0.0
    return float(match.group(1))


def _short_intro(book: dict) -> str:
    intro = re.sub(r"\s+", " ", book.get("intro", "")).strip()
    if intro:
        return intro[:72] + ("..." if len(intro) > 72 else "")
    return f"公开页暂未抓到简介，先根据书名《{book['title']}》和题材标签判断。"


def _title_try_plan(title: str, labels: list[str]) -> str:
    if "制定规则" in title or "改写" in title:
        return f"试读《{title}》：第 1 章看主角是否真的能影响规则，第 2-3 章看规则变化是否带来新解法，而不是只换皮闯关。"
    if "隐藏提示" in title or "提示" in title:
        return f"试读《{title}》：先看提示能力是否有代价和限制，再看主角是否主动推理，而不是完全被系统喂答案。"
    if "我即" in title or "即怪谈" in title:
        return f"试读《{title}》：确认身份反转是否在前几章形成压迫感，以及主角站位是否足够特别。"
    if "打工" in title or "Boss" in title:
        return f"试读《{title}》：看反套路职业设定是否带来稳定笑点/爽点，以及诡异 Boss 关系是否有新鲜互动。"
    if "生存游戏" in title or "游戏入侵" in title:
        return f"试读《{title}》：看生存规则、奖励惩罚和资源争夺是否清楚，避免只有设定没有推进。"
    if any(label in labels for label in ["民俗灵异", "悬疑恐怖"]):
        return f"试读《{title}》：看恐怖氛围是否靠具体细节建立，悬念是否在前 3 章持续升级。"
    return f"试读《{title}》：前 3 章分别看设定钩子、冲突推进、主角行动力；如果三项都弱，就降低优先级。"


def _trial_report(book: dict, matched: list[str], risks: list[str], score_parts: dict) -> dict:
    labels = _candidate_labels(book)
    title = book["title"]
    intro = _short_intro(book)
    word_count = _parse_word_count(book.get("word_count_text", ""))
    source_type = book.get("source_type")

    hook_level = "强" if any(label in labels for label in ["强悬念", "高压求生", "规则怪谈", "悬疑恐怖"]) else "中"
    novelty_words = ["制定规则", "我即", "隐藏提示", "改写", "打工", "契约", "净化"]
    novelty = "较高" if any(word in title for word in novelty_words) else ("中等" if matched else "待验证")

    core_hook = f"这本书公开信息里的核心钩子是：{intro}"
    label_hint = "、".join(labels[:4]) or "题材待验证"
    intro_promise = f"它需要兑现的不是泛泛的“诡异好看”，而是「{label_hint}」能否在开篇形成具体规则、危险和主角选择。"

    fit_points = []
    if matched:
        fit_points.append(f"与你高热爱的「{'、'.join(matched[:3])}」有交集。")
    else:
        fit_points.append("与高热爱样本弱匹配，适合作为小比例探索候选。")
    if book.get("keyword_hits"):
        fit_points.append(f"召回词命中「{'、'.join(book.get('keyword_hits', [])[:3])}」。")
    if source_type == "public_page":
        fit_points.append("来源是公开书籍页，书名、作者、分类更稳定。")
    else:
        fit_points.append("来源是公开推荐/关键词候选，可扩展口味但需要更强试读验证。")

    risk_points = list(risks[:2])
    if word_count and word_count < 10:
        risk_points.append(f"当前公开字数约 {book.get('word_count_text')}，样本偏短，质量稳定性还不能早下结论。")
    if "无女主" in book.get("category", ""):
        risk_points.append("偏无女主/弱感情线，如果你想看强情感拉扯，可能不是这一类。")
    if not book.get("intro"):
        risk_points.append("公开简介不足，标题承诺和正文兑现度需要试读确认。")
    if not risk_points:
        risk_points.append("暂无显式负反馈冲突，但仍要验证开篇是否兑现标题承诺。")

    return {
        "headline": "无剧透选书报告",
        "hook_level": hook_level,
        "novelty": novelty,
        "core_hook": core_hook,
        "intro_promise": intro_promise,
        "fit_points": fit_points[:3],
        "risk_points": risk_points[:3],
        "try_plan": _title_try_plan(title, labels),
        "score_parts": score_parts,
    }


def public_recall_recommendations(limit: int = 12) -> dict:
    profile = load_profile()
    feedback = load_feedback()
    keywords = _profile_keywords(profile)
    candidates = public_candidates()
    bookshelf_titles = {book["title"] for book in profile.get("books", [])}
    high_love_labels = Counter()
    for book in profile.get("high_love_books", []):
        for label in book.get("inferred_genres", []) + book.get("inferred_tags", []):
            if label and label != "其他":
                high_love_labels[label] += 1 + float(book.get("progress_ratio") or 0)

    negative_types = Counter(
        item.get("feedback_type")
        for item in feedback
        if item.get("feedback_type") in NEGATIVE_TYPE_TO_LABELS
    )

    scored = []
    for book in candidates:
        if book.get("title") in bookshelf_titles:
            continue
        labels = _candidate_labels(book)
        matched = [label for label in labels if high_love_labels.get(label, 0) > 0]
        keyword_hits = [word for word in keywords if word in _candidate_text(book)]
        source_bonus = 0.08 if book.get("source_type") == "public_page" else 0.04
        length_bonus = 0.04 if _parse_word_count(book.get("word_count_text", "")) >= 30 else 0.0
        fit = min(sum(high_love_labels[label] for label in matched) / max(sum(high_love_labels.values()), 1), 1.0)
        keyword_score = min(len(keyword_hits) * 0.08, 0.24)

        risks = []
        risk = 0.14
        for feedback_type, count in negative_types.items():
            for label in NEGATIVE_TYPE_TO_LABELS[feedback_type]:
                if "简介" in label and not book.get("intro"):
                    risk += 0.08 * count
                    risks.append(label)
                elif feedback_type == "恐怖氛围不够" and "悬疑恐怖" not in labels:
                    risk += 0.05 * count
                    risks.append(label)
        if book.get("status") == "公开帖子推荐":
            risks.append("公开帖子推荐，正文质量需试读验证")
            risk += 0.03
        risk = min(risk, 0.72)

        score = 0.32 + fit * 0.9 + keyword_score + source_bonus + length_bonus - risk * 0.12
        score = max(0.0, min(score, 1.0))
        score_parts = {
            "画像匹配": round(fit, 3),
            "关键词命中": round(keyword_score, 3),
            "来源可信": round(source_bonus, 3),
            "篇幅稳定": round(length_bonus, 3),
            "试读风险": round(risk, 3),
        }
        reason = (
            f"公开候选召回：命中「{'、'.join(keyword_hits[:3]) or '探索'}」，"
            f"与高热爱标签「{'、'.join(matched[:3]) or '弱匹配'}」相关。"
        )
        report_book = {**book, "keyword_hits": keyword_hits}
        scored.append({
            "book_id": book.get("book_id"),
            "title": book["title"],
            "author": book.get("author", ""),
            "source_url": book.get("source_url"),
            "source_type": book.get("source_type"),
            "status": book.get("status", ""),
            "category": book.get("category", ""),
            "word_count_text": book.get("word_count_text", ""),
            "reader_count_text": book.get("reader_count_text", ""),
            "intro": book.get("intro", ""),
            "labels": labels,
            "matched_tags": matched,
            "keyword_hits": keyword_hits,
            "score": round(score, 3),
            "risk": round(risk, 3),
            "reason": reason,
            "score_parts": score_parts,
            "trial_report": _trial_report(report_book, matched, risks, score_parts),
        })

    scored.sort(key=lambda item: (item["score"], -item["risk"]), reverse=True)
    return {
        "scope_note": "公开候选召回不是番茄后台全站召回；仅使用公开页面/公开推荐帖候选并在本地重排。",
        "keywords": keywords,
        "sources": sorted({item.get("source_type", "unknown") for item in candidates}),
        "counts": {
            "seed_candidates": len(_read_json_list(SEED_PATH)),
            "cached_candidates": len(_read_json_list(CACHE_PATH)),
            "total_public_candidates": len(candidates),
            "after_bookshelf_dedup": len(scored),
        },
        "items": scored[:limit],
    }
