"""Recommendation and reading-assistant logic for the demo app."""

from __future__ import annotations

from collections import Counter, defaultdict
from math import sqrt
from typing import Iterable

from .data import BOOKS, CHAPTERS, READING_EVENTS, get_book


LOVE_EVENTS = {"read_chapter", "add_bookshelf", "like"}
NEGATIVE_EVENTS = {"abandon_book", "dislike"}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def book_ids_for_user(user_id: str, positive: bool = True) -> set[str]:
    events = LOVE_EVENTS if positive else NEGATIVE_EVENTS
    return {event["book_id"] for event in READING_EVENTS if event["user_id"] == user_id and event["event_type"] in events}


def weighted_event_score(event: dict) -> float:
    score = 0.0
    score += min(event.get("duration_seconds", 0) / 7200, 2.0)
    score += event.get("progress", 0) * 2.2
    if event["event_type"] == "add_bookshelf":
        score += 1.2
    if event["event_type"] == "abandon_book":
        score -= 2.0
    return score


def build_user_profile(user_id: str) -> dict:
    tag_scores: Counter[str] = Counter()
    avoid_scores: Counter[str] = Counter()
    genre_scores: Counter[str] = Counter()
    loved_books = []
    abandoned_books = []

    for event in READING_EVENTS:
        if event["user_id"] != user_id:
            continue
        book = get_book(event["book_id"])
        if not book:
            continue
        score = weighted_event_score(event)
        if event["event_type"] in LOVE_EVENTS and score > 0:
            loved_books.append(book["id"])
            genre_scores[book["category"]] += max(score, 0.8)
            for tag in book["positive_tags"]:
                tag_scores[tag] += max(score, 0.8)
        if event["event_type"] in NEGATIVE_EVENTS:
            abandoned_books.append(book["id"])
            for tag in book["negative_tags"]:
                avoid_scores[tag] += abs(score) + 0.8
            # If a book is abandoned early, even positive tags become less certain.
            if event.get("progress", 1) < 0.15:
                for tag in book["positive_tags"]:
                    avoid_scores[f"不想要弱化的{tag}"] += 0.2

    return {
        "user_id": user_id,
        "favorite_genres": [name for name, _ in genre_scores.most_common(4)],
        "preferred_style_tags": [name for name, _ in tag_scores.most_common(7)],
        "avoid_tags": [name for name, _ in avoid_scores.most_common(6)],
        "recent_loved_books": list(dict.fromkeys(loved_books))[:5],
        "recent_abandoned_books": list(dict.fromkeys(abandoned_books))[:5],
        "short_term_interest_score": normalize_counter(tag_scores),
    }


def normalize_counter(counter: Counter[str]) -> dict[str, float]:
    if not counter:
        return {}
    max_score = max(counter.values())
    return {name: round(value / max_score, 3) for name, value in counter.most_common(8)}


def user_vector(user_id: str) -> Counter[str]:
    vector: Counter[str] = Counter()
    for event in READING_EVENTS:
        if event["user_id"] != user_id:
            continue
        book = get_book(event["book_id"])
        if not book:
            continue
        sign = -1 if event["event_type"] in NEGATIVE_EVENTS else 1
        weight = abs(weighted_event_score(event)) or 1.0
        for tag in book["positive_tags"]:
            vector[tag] += sign * weight
        vector[book["category"]] += sign * weight
    return vector


def cosine_similarity(a: Counter[str], b: Counter[str]) -> float:
    keys = set(a) | set(b)
    dot = sum(a[key] * b[key] for key in keys)
    norm_a = sqrt(sum(value * value for value in a.values()))
    norm_b = sqrt(sum(value * value for value in b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def similar_readers(user_id: str) -> list[dict]:
    target = user_vector(user_id)
    readers = sorted({event["user_id"] for event in READING_EVENTS if event["user_id"] != user_id})
    results = []
    for reader in readers:
        sim = cosine_similarity(target, user_vector(reader))
        common_books = sorted(book_ids_for_user(user_id) & book_ids_for_user(reader))
        results.append({"user_id": reader, "similarity": round(sim, 3), "common_books": common_books})
    return sorted(results, key=lambda item: item["similarity"], reverse=True)


def tag_overlap_score(book_tags: Iterable[str], preferred_tags: Iterable[str]) -> float:
    preferred = set(preferred_tags)
    tags = set(book_tags)
    if not tags or not preferred:
        return 0.0
    return len(tags & preferred) / len(tags | preferred)


def avoid_conflict_score(book_tags: Iterable[str], avoid_tags: Iterable[str]) -> float:
    avoid = set(avoid_tags)
    tags = set(book_tags)
    if not tags or not avoid:
        return 0.0
    direct = len(tags & avoid)
    fuzzy = sum(1 for avoid_tag in avoid for tag in tags if tag in avoid_tag or avoid_tag in tag)
    return clamp((direct + 0.35 * fuzzy) / max(len(tags), 1))


def estimate_drop_risk(book: dict, profile: dict) -> float:
    avoid = avoid_conflict_score(book["negative_tags"], profile["avoid_tags"])
    low_hook = clamp((8.5 - book["hook_score"]) / 4.5)
    low_consistency = clamp((8.5 - book["intro_consistency_score"]) / 4.5)
    mismatch = 1.0 - tag_overlap_score(book["positive_tags"] + [book["category"]], profile["preferred_style_tags"] + profile["favorite_genres"])
    return round(clamp(0.34 * avoid + 0.26 * low_hook + 0.20 * low_consistency + 0.20 * mismatch), 3)


def similar_reader_boost(book_id: str, user_id: str) -> float:
    sims = similar_readers(user_id)
    if not sims:
        return 0.0
    boost = 0.0
    for sim in sims:
        reader = sim["user_id"]
        if book_id in book_ids_for_user(reader):
            boost += max(sim["similarity"], 0) * 0.45
    return clamp(boost)


def recommendation_reason(book: dict, profile: dict, drop_risk: float, final_score: float) -> str:
    matched_tags = [tag for tag in book["positive_tags"] if tag in set(profile["preferred_style_tags"])]
    matched = "、".join(matched_tags[:3]) if matched_tags else book["category"]
    reason = (
        f"你近期偏好「{matched}」，这本书的简介一致性 {book['intro_consistency_score']:.1f}/10，"
        f"前三章钩子 {book['hook_score']:.1f}/10，相似读者留存 {int(book['similar_reader_retention'] * 100)}%。"
    )
    if drop_risk >= 0.52:
        reason += " 但存在一定弃读风险，建议低优先级试读。"
    elif final_score >= 0.82:
        reason += " 推荐优先试读。"
    return reason


def risk_note(book: dict, profile: dict, drop_risk: float) -> str:
    conflicts = [tag for tag in book["negative_tags"] if tag in set(profile["avoid_tags"])]
    if conflicts:
        return "潜在雷点：" + "、".join(conflicts)
    if drop_risk > 0.5:
        return "和近期高热爱风格存在偏差，可能需要读到后面才进入状态。"
    if book["negative_tags"]:
        return "可接受风险：" + "、".join(book["negative_tags"][:2])
    return "暂无明显雷点。"


def recommend(user_id: str, limit: int = 20) -> dict:
    profile = build_user_profile(user_id)
    read_or_abandoned = book_ids_for_user(user_id, True) | book_ids_for_user(user_id, False)
    items = []

    for book in BOOKS:
        if book["id"] in read_or_abandoned:
            continue
        interest_match = tag_overlap_score(book["positive_tags"] + [book["category"]], profile["preferred_style_tags"] + profile["favorite_genres"])
        sim_boost = similar_reader_boost(book["id"], user_id)
        drop_risk = estimate_drop_risk(book, profile)
        avoid_conflict = avoid_conflict_score(book["negative_tags"], profile["avoid_tags"])
        final_score = (
            0.25 * interest_match
            + 0.20 * book["similar_reader_retention"]
            + 0.15 * (book["intro_consistency_score"] / 10)
            + 0.15 * (book["hook_score"] / 10)
            + 0.10 * (book["quality_score"] / 10)
            + 0.10 * sim_boost
            - 0.20 * drop_risk
            - 0.15 * avoid_conflict
        )
        final_score = round(clamp(final_score), 3)
        items.append(
            {
                "book_id": book["id"],
                "title": book["title"],
                "author": book["author"],
                "category": book["category"],
                "status": book["status"],
                "word_count": book["word_count"],
                "cover_theme": book["cover_theme"],
                "tags": book["positive_tags"][:5],
                "negative_tags": book["negative_tags"],
                "final_score": final_score,
                "drop_risk": drop_risk,
                "intro_consistency_score": book["intro_consistency_score"],
                "hook_score": book["hook_score"],
                "reason": recommendation_reason(book, profile, drop_risk, final_score),
                "risk_note": risk_note(book, profile, drop_risk),
            }
        )

    items.sort(key=lambda item: item["final_score"], reverse=True)
    return {"profile": profile, "similar_readers": similar_readers(user_id), "items": items[:limit]}


def book_analysis(book_id: str, user_id: str) -> dict:
    book = get_book(book_id)
    if not book:
        raise KeyError(book_id)
    profile = build_user_profile(user_id)
    drop_risk = estimate_drop_risk(book, profile)
    mismatch_points = []
    if book["intro_consistency_score"] < 8:
        mismatch_points.append("简介承诺和正文推进存在轻微偏差")
    if book["hook_score"] < 8:
        mismatch_points.append("前三章钩子不够强，需要更多耐心")
    if book["negative_tags"]:
        mismatch_points.extend(book["negative_tags"][:2])

    return {
        "book_id": book["id"],
        "title": book["title"],
        "intro": book["intro"],
        "positive_tags": book["positive_tags"],
        "negative_tags": book["negative_tags"],
        "intro_promises": [book["category"], *book["positive_tags"][:3]],
        "text_evidence": [
            "前三章出现核心设定并推动主线冲突",
            "主角首次关键选择能体现作品承诺的阅读体验",
        ],
        "mismatch_points": mismatch_points or ["暂未发现明显简介党风险"],
        "intro_consistency_score": book["intro_consistency_score"],
        "hook_score": book["hook_score"],
        "style_score": book["style_score"],
        "quality_score": book["quality_score"],
        "drop_risk": drop_risk,
        "recommendation_note": risk_note(book, profile, drop_risk),
        "analysis_summary": book["summary"],
        "comments_signal": book["comments_signal"],
    }


def chapter_summary(book_id: str, chapter_id: str | None = None) -> dict:
    chapters = CHAPTERS.get(book_id, [])
    if not chapters:
        return {
            "chapter_id": chapter_id or "demo",
            "summary": "该书暂未录入章节正文，系统将基于书籍简介生成摘要。",
            "key_events": [],
            "characters": [],
            "foreshadowing": [],
        }
    if chapter_id:
        for chapter in chapters:
            if chapter["id"] == chapter_id:
                return chapter
    return chapters[0]


def recap(book_id: str, user_id: str, before_chapter: str | None = None) -> dict:
    book = get_book(book_id)
    summary = chapter_summary(book_id, before_chapter)
    if not book:
        raise KeyError(book_id)
    return {
        "book_id": book_id,
        "user_id": user_id,
        "recap": f"你上次读到《{book['title']}》中「{summary.get('title', '当前章节')}」附近：{summary['summary']}",
        "important_characters": [
            {"name": name, "status": "与当前主线相关", "relationship": "关键人物"}
            for name in summary.get("characters", [])
        ],
        "open_threads": summary.get("foreshadowing", []),
        "next_reading_hint": "继续阅读前建议记住规则边界、人物动机和未解伏笔。",
    }


def record_feedback(user_id: str, book_id: str, feedback_type: str, reason: str = "") -> dict:
    event_type = "like" if feedback_type in {"喜欢", "加入书架"} else "dislike"
    READING_EVENTS.append(
        {
            "user_id": user_id,
            "book_id": book_id,
            "event_type": event_type,
            "duration_seconds": 0,
            "progress": 0,
            "chapter_index": 0,
            "reason": reason or feedback_type,
        }
    )
    return {"ok": True, "profile": build_user_profile(user_id)}


def all_books() -> list[dict]:
    return BOOKS


def chapters_for_book(book_id: str) -> list[dict]:
    return CHAPTERS.get(book_id, [])

