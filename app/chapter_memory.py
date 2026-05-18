from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


MEMORY_PATH = Path(__file__).with_name("chapter_memory.json")

EVENT_PATTERNS = {
    "规则出现": ["规则", "禁止", "必须", "不能", "违反"],
    "异常现象": ["诡异", "怪谈", "异常", "鬼", "怪物", "消失"],
    "危机升级": ["死亡", "惩罚", "危险", "倒计时", "逃", "血"],
    "主角推理": ["发现", "意识到", "推理", "线索", "判断", "观察"],
    "主动选择": ["决定", "选择", "反击", "制定", "利用", "破解"],
    "人物冲突": ["争吵", "质问", "威胁", "怀疑", "背叛", "救"],
}

STYLE_PATTERNS = {
    "规则怪谈": ["规则", "怪谈", "违反", "禁忌"],
    "高压求生": ["死亡", "惩罚", "逃", "危险", "倒计时"],
    "强悬念": ["为什么", "秘密", "真相", "身份", "背后", "异常"],
    "主角行动力": ["决定", "选择", "发现", "利用", "破解", "反击"],
    "氛围恐怖": ["黑暗", "血", "鬼", "尸", "寒意", "敲门"],
}

GENERIC_NAMES = {
    "规则",
    "主角",
    "宿舍",
    "系统",
    "怪谈",
    "老师",
    "同学",
    "男人",
    "女人",
    "声音",
    "手机",
    "房间",
    "世界",
}


def load_memory() -> list[dict]:
    if not MEMORY_PATH.exists():
        return []
    return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))


def save_memory(items: list[dict]) -> None:
    MEMORY_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])", _normalize_text(text))
    return [part.strip() for part in parts if len(part.strip()) >= 8]


def _count_hits(text: str, patterns: dict[str, list[str]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for label, words in patterns.items():
        counter[label] = sum(text.count(word) for word in words)
    return counter


def _extract_key_events(text: str) -> list[str]:
    hits = _count_hits(text, EVENT_PATTERNS)
    events = [label for label, count in hits.most_common() if count > 0]
    return events[:5] or ["情节推进待人工复核"]


def _extract_characters(text: str) -> list[str]:
    names = []
    for match in re.finditer(r"([\u4e00-\u9fa5]{2,4})(?:说|问|道|喊|叫|看|想|笑|哭|提醒|发现|决定)", text):
        name = match.group(1)
        if name not in GENERIC_NAMES and not any(word in name for word in ["什么", "没有", "这个", "那个"]):
            names.append(name)
    counted = Counter(names)
    return [name for name, _ in counted.most_common(5)]


def _extract_open_threads(sentences: list[str]) -> list[str]:
    markers = ["为什么", "秘密", "真相", "身份", "背后", "异常", "消失", "未", "没有解释"]
    threads = []
    for sentence in sentences:
        if any(marker in sentence for marker in markers):
            cleaned = sentence[:42] + ("..." if len(sentence) > 42 else "")
            threads.append(cleaned)
    return threads[:3] or ["仍需继续阅读确认核心谜题和人物动机。"]


def _score(text: str, labels: list[str], total_sentences: int) -> dict:
    style_hits = _count_hits(text, STYLE_PATTERNS)
    hook = min(10.0, 5.6 + style_hits["强悬念"] * 0.35 + style_hits["高压求生"] * 0.3 + style_hits["规则怪谈"] * 0.18)
    pace = min(10.0, 5.4 + len(labels) * 0.55 + min(total_sentences, 35) * 0.04)
    agency = min(10.0, 5.2 + style_hits["主角行动力"] * 0.42 + ("主动选择" in labels) * 0.8)
    atmosphere = min(10.0, 5.2 + style_hits["氛围恐怖"] * 0.38 + style_hits["规则怪谈"] * 0.16)
    return {
        "hook_score": round(hook, 1),
        "pace_score": round(pace, 1),
        "protagonist_agency": round(agency, 1),
        "atmosphere_score": round(atmosphere, 1),
    }


def _summary_from_signals(title: str, events: list[str], characters: list[str], scores: dict) -> str:
    event_text = "、".join(events[:3])
    char_text = "、".join(characters[:3]) if characters else "主要角色"
    quality = "强" if scores["hook_score"] >= 8 else "中等" if scores["hook_score"] >= 6.8 else "偏弱"
    return f"《{title}》围绕{event_text}推进，{char_text}参与当前冲突；开篇钩子强度{quality}，适合继续观察设定是否持续兑现。"


def _memory_key(book_id: str, title: str) -> str:
    return str(book_id or title).strip()


def analyze_chapter(payload: dict) -> dict:
    text = _normalize_text(payload.get("chapter_text", ""))
    if len(text) < 80:
        raise ValueError("chapter_text too short; paste at least one meaningful chapter segment")

    book_id = str(payload.get("book_id") or payload.get("title") or "manual").strip()
    title = str(payload.get("title") or book_id).strip()
    chapter_index = int(payload.get("chapter_index") or 1)
    chapter_title = str(payload.get("chapter_title") or f"第 {chapter_index} 章").strip()
    sentences = _sentences(text)
    events = _extract_key_events(text)
    characters = _extract_characters(text)
    threads = _extract_open_threads(sentences)
    scores = _score(text, events, len(sentences))

    card = {
        "book_id": book_id,
        "title": title,
        "chapter_index": chapter_index,
        "chapter_title": chapter_title,
        "summary": _summary_from_signals(title, events, characters, scores),
        "key_events": events,
        "characters": characters,
        "open_threads": threads,
        "scores": scores,
        "source_policy": "只保存结构化剧情记忆卡，不保存章节原文。",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    items = load_memory()
    key = _memory_key(book_id, title)
    items = [
        item for item in items
        if not (_memory_key(item.get("book_id", ""), item.get("title", "")) == key and item.get("chapter_index") == chapter_index)
    ]
    items.append(card)
    items.sort(key=lambda item: (_memory_key(item.get("book_id", ""), item.get("title", "")), item.get("chapter_index", 0)))
    save_memory(items[-240:])
    return {"ok": True, "card": card, "memory": chapter_memory_for_book(book_id, title)}


def _aggregate_report(cards: list[dict], title: str) -> dict:
    if not cards:
        return {
            "confidence": "低",
            "recap": "尚未导入章节，暂时只能做基于元信息的轻量判断。",
            "trial_report": "导入当前章节或前三章后，可生成真正基于正文的无剧透试读判断。",
            "next_hint": "先导入第 1 章，确认设定钩子和主角行动力。",
        }

    events = Counter(event for card in cards for event in card.get("key_events", []))
    characters = Counter(name for card in cards for name in card.get("characters", []))
    threads = []
    for card in cards:
        threads.extend(card.get("open_threads", []))
    avg_hook = sum(card.get("scores", {}).get("hook_score", 0) for card in cards) / len(cards)
    avg_pace = sum(card.get("scores", {}).get("pace_score", 0) for card in cards) / len(cards)
    avg_agency = sum(card.get("scores", {}).get("protagonist_agency", 0) for card in cards) / len(cards)
    confidence = "高" if len(cards) >= 3 else "中" if len(cards) >= 1 else "低"
    event_text = "、".join(name for name, _ in events.most_common(4))
    character_text = "、".join(name for name, _ in characters.most_common(4)) or "主要角色待继续识别"
    trial_judgment = "值得继续读" if avg_hook >= 7.6 and avg_agency >= 6.8 else "建议低成本试读" if avg_hook >= 6.6 else "需要谨慎继续"

    return {
        "confidence": confidence,
        "recap": f"已基于《{title}》{len(cards)} 章生成剧情记忆：目前主线围绕{event_text or '核心冲突'}展开，涉及{character_text}。",
        "trial_report": (
            f"正文级试读判断：前三章/已导入章节平均钩子 {avg_hook:.1f}，节奏 {avg_pace:.1f}，"
            f"主角行动力 {avg_agency:.1f}。系统判断：{trial_judgment}。"
        ),
        "next_hint": f"续读时优先关注：{threads[0] if threads else '规则边界、人物动机和未解伏笔'}",
        "open_threads": list(dict.fromkeys(threads))[:5],
        "key_events": [name for name, _ in events.most_common(6)],
        "characters": [name for name, _ in characters.most_common(6)],
        "scores": {
            "avg_hook": round(avg_hook, 1),
            "avg_pace": round(avg_pace, 1),
            "avg_agency": round(avg_agency, 1),
        },
    }


def chapter_memory_for_book(book_id: str, title: str = "") -> dict:
    key = _memory_key(book_id, title)
    cards = [
        item for item in load_memory()
        if _memory_key(item.get("book_id", ""), item.get("title", "")) == key
    ]
    cards.sort(key=lambda item: item.get("chapter_index", 0))
    display_title = title or (cards[0]["title"] if cards else book_id)
    return {
        "book_id": book_id,
        "title": display_title,
        "cards": cards,
        "aggregate": _aggregate_report(cards, display_title),
        "storage_policy": "系统不保存章节原文，只保存摘要、事件、人物、伏笔和评分。",
    }
