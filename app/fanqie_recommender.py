from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable


PROFILE_PATH = Path(__file__).with_name("fanqie_user_profile.json")
FEEDBACK_PATH = Path(__file__).with_name("fanqie_feedback.json")

POSITIVE_FEEDBACK = {"想看类似", "喜欢", "加入书架", "继续推荐"}
NEGATIVE_FEEDBACK = {
    "不感兴趣",
    "简介不符",
    "节奏太慢",
    "设定老套",
    "主角降智",
    "文笔不适",
    "恐怖氛围不够",
    "感情线不喜欢",
    "不想看类似",
    "屏蔽题材",
    "确认弃读",
}
ABANDON_REASON_GROUPS = {
    "简介不符": ["简介兑现风险", "标题党风险"],
    "节奏太慢": ["慢热风险", "前三章钩子风险"],
    "设定老套": ["套路重复风险", "设定新鲜度不足"],
    "主角降智": ["主角智商风险", "行动力风险"],
    "文笔不适": ["文风适配风险", "阅读流畅度风险"],
    "恐怖氛围不够": ["氛围强度风险", "悬疑恐怖预期不匹配"],
    "感情线不喜欢": ["感情线干扰风险", "CP 走向风险"],
}


def load_profile() -> dict:
    if not PROFILE_PATH.exists():
        raise FileNotFoundError("fanqie_user_profile.json not found")
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def load_feedback() -> list[dict]:
    if not FEEDBACK_PATH.exists():
        return []
    return json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))


def save_feedback(items: list[dict]) -> None:
    FEEDBACK_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _book_key(book: dict) -> str:
    return str(book.get("book_id") or book.get("title"))


def _book_index(books: Iterable[dict]) -> dict[str, dict]:
    result = {}
    for book in books:
        result[_book_key(book)] = book
        result[book["title"]] = book
    return result


def _labels(book: dict) -> list[str]:
    labels = []
    for label in book.get("inferred_genres", []) + book.get("inferred_tags", []):
        if label and label != "其他" and label not in labels:
            labels.append(label)
    return labels


def _counter_from_books(books: list[dict], base_weight: float = 1.0) -> Counter[str]:
    counter: Counter[str] = Counter()
    for book in books:
        weight = base_weight + float(book.get("progress_ratio") or 0) * 2.0
        for label in _labels(book):
            counter[label] += weight
    return counter


def _counter_from_feedback(feedback: list[dict], books_by_key: dict[str, dict], types: set[str]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for item in feedback:
        if item.get("feedback_type") not in types:
            continue
        book = books_by_key.get(str(item.get("book_id"))) or books_by_key.get(str(item.get("title")))
        if not book:
            continue
        for label in _labels(book):
            counter[label] += 1.8
    return counter


def _title_bonus(title: str) -> float:
    bonus = 0.0
    if any(word in title for word in ["诡异", "规则", "怪谈", "副本", "无限", "恐怖"]):
        bonus += 0.12
    if any(word in title for word in ["求生", "生存", "末世", "公路"]):
        bonus += 0.08
    if any(word in title for word in ["推演", "直播", "降临", "邪神", "玩家"]):
        bonus += 0.06
    return bonus


def _risk_for_book(book: dict, negative_counter: Counter[str]) -> tuple[float, list[str]]:
    reasons = []
    risk = 0.12
    labels = set(_labels(book))

    for label, weight in negative_counter.most_common(6):
        if label in labels:
            risk += min(weight * 0.055, 0.22)
            reasons.append(f"命中显式负反馈标签「{label}」")

    if not labels:
        risk += 0.1
        reasons.append("标题可识别信息少，需试读验证")

    return round(min(risk, 0.92), 3), reasons[:3]


def _trial_report(book: dict, matched: list[str], risk_reasons: list[str], components: dict) -> dict:
    labels = _labels(book)
    title = book["title"]
    hook_level = "强" if any(label in labels for label in ["强悬念", "高压求生"]) else "中"
    novelty = "较高" if any(word in title for word in ["诡异", "规则", "无限", "副本", "邪神", "推演"]) else "待验证"
    intro_promise = "建议重点看前 3 章是否兑现标题/简介里的核心设定。"
    if "规则怪谈/诡异" in labels or "悬疑恐怖" in labels:
        intro_promise = "重点验证诡异设定是否足够新、悬念是否在前 3 章迅速建立。"
    elif "末世求生" in labels:
        intro_promise = "重点验证生存压力、资源冲突和主角行动力是否足够明确。"

    fit_points = []
    if matched:
        fit_points.append(f"命中你近期高热爱的「{'、'.join(matched[:3])}」。")
    if components.get("标题兴趣", 0) > 0:
        fit_points.append("标题含有你近期偏好的高压/诡异/副本类兴趣词。")
    if book.get("status") == "unread" or book.get("progress_ratio") is None:
        fit_points.append("目前适合放入待试读队列，不会被低网页进度误伤。")

    risk_points = risk_reasons[:]
    if not risk_points:
        if hook_level == "中":
            risk_points.append("前三章钩子强度需要实际试读确认。")
        else:
            risk_points.append("暂无显式负反馈冲突，但仍建议先读 3 章验证正文兑现度。")
    if not matched:
        risk_points.append("与高热爱样本标签匹配较弱，属于探索型候选。")

    return {
        "headline": "无剧透选书报告",
        "hook_level": hook_level,
        "novelty": novelty,
        "intro_promise": intro_promise,
        "fit_points": fit_points[:3],
        "risk_points": risk_points[:3],
        "try_plan": "先读 3 章：第 1 章看设定钩子，第 2-3 章看主角行动力和悬念升级；若仍无核心冲突，可降低优先级。",
    }


def _bookshelf_recap(book: dict, matched: list[str]) -> dict:
    labels = _labels(book)
    title = book["title"]
    progress = book.get("progress_text") or "网页端暂无同步进度"
    status = book.get("status")
    label_text = "、".join(labels[:4]) or "题材待识别"

    if status == "unread":
        recap = f"《{title}》还处在未读状态，当前没有可回顾的正文剧情；可先把它当作「{label_text}」方向的待试读候选。"
        resume_hint = "先读前 3 章，重点看设定钩子、主角行动力和悬念升级是否连续出现。"
    elif book.get("progress_ratio") is None:
        recap = f"《{title}》在书架中暂无网页端进度，可能是 App 端进度未同步；当前只基于书架记录和题材标签做续读提醒，不伪造正文剧情。"
        resume_hint = "打开正文后先扫最近一章标题和上一章结尾，再决定是否继续追。"
    else:
        recap = f"网页端记录《{title}》读到 {progress}，可作为续读入口；由于本地没有抓取正文，只回顾可验证的书架进度和兴趣标签。"
        resume_hint = "续读前先回看上一章末尾冲突，再确认主线目标、危险规则和主角当前资源。"

    memory_points = []
    if matched:
        memory_points.append(f"你选择它的主要原因是命中近期高热爱标签：{'、'.join(matched[:3])}。")
    if any(label in labels for label in ["规则怪谈/诡异", "悬疑恐怖"]):
        memory_points.append("续读时优先记住当前规则、异常现象和未解释线索。")
    if any(label in labels for label in ["无限流/副本", "高压求生", "末世求生"]):
        memory_points.append("续读时关注副本/生存目标、倒计时压力和主角已掌握的信息差。")
    if any(label in labels for label in ["主角能力/推演", "反套路/邪神养成"]):
        memory_points.append("续读时确认主角能力边界是否扩大，以及是否出现反套路反转。")
    if not memory_points:
        memory_points.append("续读时先确认主角目标、主要冲突和上一次停读原因。")

    return {
        "headline": "续读前情回顾",
        "basis": "基于书架进度、题材标签和你的高热爱画像生成；未抓取正文时不编造具体剧情。",
        "progress": progress,
        "recap": recap,
        "memory_points": memory_points[:3],
        "resume_hint": resume_hint,
    }


def record_fanqie_feedback(book_id: str, feedback_type: str, reason: str = "") -> dict:
    profile = load_profile()
    books_by_key = _book_index(profile["books"])
    book = books_by_key.get(str(book_id))
    if not book:
        raise KeyError(f"book not found: {book_id}")

    items = load_feedback()
    items.append({
        "book_id": book.get("book_id"),
        "title": book["title"],
        "feedback_type": feedback_type,
        "reason": reason or feedback_type,
        "reason_group": ABANDON_REASON_GROUPS.get(feedback_type, []),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_feedback(items[-80:])
    return {
        "ok": True,
        "saved": items[-1],
        "summary": _feedback_summary(items),
    }


def _feedback_summary(feedback: list[dict]) -> dict:
    counts = Counter(item.get("feedback_type", "未知") for item in feedback)
    reason_groups = Counter(
        group
        for item in feedback
        for group in item.get("reason_group", [])
    )
    return {
        "total": len(feedback),
        "positive": sum(counts[k] for k in POSITIVE_FEEDBACK),
        "negative": sum(counts[k] for k in NEGATIVE_FEEDBACK),
        "by_type": counts.most_common(),
        "reason_groups": reason_groups.most_common(),
    }


def _feedback_book_ids(feedback: list[dict], types: set[str]) -> set[str]:
    return {
        str(item.get("book_id"))
        for item in feedback
        if item.get("feedback_type") in types and item.get("book_id")
    }


def _recommendation_pipeline(profile: dict, candidates: list[dict], scored: list[dict], feedback: list[dict]) -> list[dict]:
    top_items = scored[:8]
    top_genres = {
        genre
        for item in top_items
        for genre in item.get("inferred_genres", [])
        if genre != "待识别"
    }
    return [
        {
            "name": "画像构建",
            "detail": f"{len(profile['high_love_books'])} 本高热爱正样本，{len(profile['early_drop_or_low_progress_books'])} 本进度待验证",
        },
        {
            "name": "候选召回",
            "detail": f"从 {profile['counts']['unique_books']} 本书架书中召回 {len(candidates)} 本未读/无进度候选",
        },
        {
            "name": "特征排序",
            "detail": "融合题材标签、标题兴趣词、待试读状态、显式反馈冲突和试读风险",
        },
        {
            "name": "重排解释",
            "detail": f"Top {len(top_items)} 覆盖 {len(top_genres)} 类题材，并为每本书生成可解释推荐理由",
        },
        {
            "name": "反馈闭环",
            "detail": f"已记录 {len(feedback)} 条显式反馈；低网页进度仍只作为待验证信号",
        },
    ]


def _metrics(candidates: list[dict], scored: list[dict], feedback: list[dict]) -> dict:
    top_items = scored[:8]
    top_scores = [item["score"] for item in top_items]
    matched_count = sum(1 for item in top_items if item.get("matched_tags"))
    genres = {
        genre
        for item in top_items
        for genre in item.get("inferred_genres", [])
        if genre != "待识别"
    }
    feedback_summary = _feedback_summary(feedback)
    return {
        "candidate_count": len(candidates),
        "top_avg_score": round(sum(top_scores) / len(top_scores), 3) if top_scores else 0,
        "explain_coverage": round(matched_count / len(top_items), 3) if top_items else 0,
        "genre_diversity": len(genres),
        "feedback_total": feedback_summary["total"],
        "feedback_positive": feedback_summary["positive"],
        "feedback_negative": feedback_summary["negative"],
    }


def fanqie_recommendations(limit: int = 30) -> dict:
    profile = load_profile()
    books = profile["books"]
    feedback = load_feedback()
    books_by_key = _book_index(books)

    high_love = profile["high_love_books"]
    low_progress = profile["early_drop_or_low_progress_books"]
    positive = _counter_from_books(high_love)
    positive.update(_counter_from_feedback(feedback, books_by_key, POSITIVE_FEEDBACK))

    # Only explicit feedback is treated as negative. Low web progress is noisy:
    # it may mean unread, unsynced, or finished on mobile.
    negative = _counter_from_feedback(feedback, books_by_key, NEGATIVE_FEEDBACK)
    blocked_ids = _feedback_book_ids(feedback, NEGATIVE_FEEDBACK)
    boosted_ids = _feedback_book_ids(feedback, POSITIVE_FEEDBACK)

    candidates = [
        book for book in books
        if (book.get("progress_ratio") is None or book.get("status") == "unread")
        and _book_key(book) not in blocked_ids
    ]

    scored = []
    for book in candidates:
        genres = [g for g in book.get("inferred_genres", []) if g != "其他"]
        tags = [t for t in book.get("inferred_tags", []) if t != "其他"]
        labels = genres + tags
        positive_match = sum(positive[label] for label in labels)
        negative_match = sum(negative[label] for label in labels)
        max_positive = max(sum(positive.values()), 1)
        max_negative = max(sum(negative.values()), 1)

        fit = positive_match / max_positive
        conflict = negative_match / max_negative if negative else 0.0
        title_signal = _title_bonus(book["title"])
        unread_bonus = 0.06 if book.get("status") == "unread" else 0.0
        feedback_boost = 0.12 if _book_key(book) in boosted_ids else 0.0
        risk, risk_reasons = _risk_for_book(book, negative)

        score = 0.36 + fit * 1.24 + title_signal + unread_bonus + feedback_boost - conflict * 0.5 - risk * 0.08
        score = max(0.0, min(score, 1.0))

        matched = []
        for label in labels:
            if positive.get(label, 0) > 0:
                matched.append(label)
        matched = list(dict.fromkeys(matched))

        components = {
            "画像匹配": round(fit, 3),
            "标题兴趣": round(title_signal, 3),
            "待试读加成": round(unread_bonus, 3),
            "反馈加成": round(feedback_boost, 3),
            "负反馈冲突": round(conflict, 3),
            "试读风险": risk,
        }

        if matched:
            reason = f"适合你：匹配高热爱样本里的「{'、'.join(matched[:3])}」。"
        else:
            reason = "适合你：和当前高热爱样本匹配较弱，但可作为探索型候选。"

        if book.get("status") == "unread":
            reason += " 已在书架但未读，适合验证“简介吸引但正文是否兑现”。"
        elif book.get("progress_ratio") is None:
            reason += " 书架暂无进度，适合排入待试读队列。"
        if feedback_boost:
            reason += " 你已给过正向反馈，因此提高优先级。"

        if risk_reasons:
            reason += f" 可能不适合：{'；'.join(risk_reasons[:2])}。"
        elif not matched:
            reason += " 可能不适合：标签匹配度较低，需要试读确认。"
        else:
            reason += " 可能不适合：暂无明显雷点，但仍建议先看前三章。"

        recall_sources = ["书架待试读"]
        if matched:
            recall_sources.append("高热爱标签召回")
        else:
            recall_sources.append("探索召回")
        if title_signal:
            recall_sources.append("标题兴趣词召回")

        scored.append({
            "book_id": book.get("book_id"),
            "title": book["title"],
            "score": round(score, 3),
            "drop_risk": risk,
            "reason": reason,
            "risk_note": "；".join(risk_reasons) if risk_reasons else "暂无显式负反馈冲突，建议前三章试读。",
            "matched_tags": matched,
            "inferred_genres": genres or ["待识别"],
            "inferred_tags": tags or ["待识别"],
            "status": book.get("status"),
            "progress_text": book.get("progress_text"),
            "recall_sources": recall_sources,
            "components": components,
            "trial_report": _trial_report(book, matched, risk_reasons, components),
            "reading_recap": _bookshelf_recap(book, matched),
            "abandon_feedback_options": list(ABANDON_REASON_GROUPS.keys()),
        })

    scored.sort(key=lambda item: (item["score"], -item["drop_risk"]), reverse=True)

    return {
        "basis": {
            "positive_books": high_love[:8],
            "progress_uncertain_books": low_progress[:6],
            "positive_signals": positive.most_common(8),
            "negative_signals": negative.most_common(8),
            "feedback": _feedback_summary(feedback),
            "abandon_feedback_options": list(ABANDON_REASON_GROUPS.keys()),
        },
        "metrics": _metrics(candidates, scored, feedback),
        "pipeline": _recommendation_pipeline(profile, candidates, scored, feedback),
        "items": scored[:limit],
    }


def fanqie_diagnostics() -> dict:
    data = fanqie_recommendations(limit=12)
    return {
        "pipeline": data["pipeline"],
        "metrics": data["metrics"],
        "basis": data["basis"],
        "top_items": data["items"][:5],
    }
