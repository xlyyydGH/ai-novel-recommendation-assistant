from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


TXT_LIBRARY = Path(__file__).with_name("txt_library")

PROFILE_KEYWORDS = ["悬疑", "规则", "诡异", "恐怖", "高压", "宿舍", "直播", "镜子", "倒计时", "失踪", "民俗", "副本", "游戏", "入侵", "机缘", "天赋", "主角", "神赐", "S级", "盗神", "不朽", "神明游戏", "重生", "命运"]
HOOK_WORDS = ["规则", "不能", "必须", "倒计时", "失踪", "镜子", "短信", "直播", "门外", "红字", "编号", "档案", "重生", "天赋", "神赐", "S级", "盗神", "不朽", "机缘", "命运", "副本", "神明游戏", "入侵"]
PACE_WORDS = ["突然", "立刻", "推开", "跑", "响起", "弹出", "发现", "决定", "追", "敲门", "消失", "抽取", "抢", "偷", "清空", "击杀", "通关", "进入", "升级", "获得"]
AGENCY_WORDS = ["记录", "试探", "决定", "推断", "验证", "反问", "追上", "藏起", "打开", "写下", "对照", "抢", "偷", "抽取", "清空", "布局", "反杀", "选择", "夺走", "利用"]
OPEN_THREAD_WORDS = ["为什么", "谁", "消失", "倒计时", "编号", "镜子", "门外", "短信", "直播间", "档案", "名单", "机缘", "天赋", "神赐", "命运", "神明游戏", "副本", "主角", "女主", "男主", "入侵"]
GENERIC_WORDS = {
    "第一章",
    "第二章",
    "第三章",
    "宿舍",
    "走廊",
    "镜子",
    "手机",
    "规则",
    "直播",
    "门外",
    "黑板",
    "档案",
    "女生",
    "同桌",
    "老师",
    "管理员",
}


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _story_path(story_id: str) -> Path:
    TXT_LIBRARY.mkdir(exist_ok=True)
    requested = Path(story_id).name
    candidates = [TXT_LIBRARY / requested]
    if not requested.endswith(".txt"):
        candidates.append(TXT_LIBRARY / f"{requested}.txt")
    for path in candidates:
        if path.exists() and path.suffix.lower() == ".txt":
            return path
    raise FileNotFoundError(f"story not found: {story_id}")


def _story_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("书名："):
            return line.replace("书名：", "", 1).strip() or path.stem
        if re.match(r"^第[一二三四五六七八九十百千万\d]+[章节回]", line):
            return re.sub(r"\(\d+-\d+章\)$", "", path.stem).strip()
        return line[:40]
    return path.stem


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])", re.sub(r"\s+", " ", text))
    return [part.strip() for part in parts if len(part.strip()) >= 10]


def parse_chapters(text: str) -> list[dict]:
    text = _normalize(text)
    pattern = re.compile(r"(?m)^\s*(第[一二三四五六七八九十百千万\d]+[章节回][^\n]*)\s*$")
    matches = list(pattern.finditer(text))
    chapters: list[dict] = []
    if matches:
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                chapters.append({"index": index + 1, "title": match.group(1).strip(), "text": body})
        return chapters

    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    for index, block in enumerate(blocks[:8], start=1):
        chapters.append({"index": index, "title": f"片段 {index}", "text": block})
    return chapters


def _count_words(text: str, words: list[str]) -> int:
    return sum(text.count(word) for word in words)


def _top_sentences(text: str, words: list[str], limit: int = 3) -> list[str]:
    scored = []
    for sentence in _sentences(text):
        score = _count_words(sentence, words)
        if score:
            scored.append((score, len(sentence), sentence))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [sentence for _, _, sentence in scored[:limit]]


def _extract_characters(text: str) -> list[dict]:
    names: Counter[str] = Counter()
    for pattern in [
        r"([\u4e00-\u9fa5]{2,3})(?:说|问|道|发现|提醒|推开|写下|站在|看见|拿出|按住|摇头|低声)",
        r"(?:叫|名叫|同桌|室友|管理员|老师)([\u4e00-\u9fa5]{2,3})",
    ]:
        for match in re.finditer(pattern, text):
            name = match.group(1)
            if name not in GENERIC_WORDS and not any(word in name for word in GENERIC_WORDS):
                names[name] += 1
    roles = []
    for name, count in names.most_common(6):
        if count >= 1:
            clue = next((sentence for sentence in _sentences(text) if name in sentence), "")
            roles.append({"name": name, "signal": clue[:46] + ("..." if len(clue) > 46 else "")})
    return roles


def _summary(text: str, title: str) -> str:
    sentences = _sentences(text)
    hook = _top_sentences(text, HOOK_WORDS, limit=1)
    action = _top_sentences(text, AGENCY_WORDS, limit=1)
    first = sentences[0] if sentences else ""
    pieces = [hook[0] if hook else first, action[0] if action else ""]
    pieces = [piece for piece in pieces if piece]
    return f"{title}：{' '.join(pieces)[:150]}"


def _chapter_card(chapter: dict) -> dict:
    text = chapter["text"]
    events = _top_sentences(text, HOOK_WORDS + PACE_WORDS, limit=4)
    open_threads = _top_sentences(text, OPEN_THREAD_WORDS, limit=3)
    hook_score = min(10.0, 5.4 + _count_words(text, HOOK_WORDS) * 0.34)
    pace_score = min(10.0, 5.2 + _count_words(text, PACE_WORDS) * 0.22 + min(len(_sentences(text)), 24) * 0.05)
    agency_score = min(10.0, 5.0 + _count_words(text, AGENCY_WORDS) * 0.32)
    match_score = min(10.0, 5.0 + _count_words(text, PROFILE_KEYWORDS) * 0.24)
    return {
        "chapter_index": chapter["index"],
        "chapter_title": chapter["title"],
        "summary": _summary(text, chapter["title"]),
        "key_events": events,
        "open_threads": open_threads,
        "scores": {
            "hook": round(hook_score, 1),
            "pace": round(pace_score, 1),
            "agency": round(agency_score, 1),
            "profile_match": round(match_score, 1),
        },
    }


def _reader_facing_summary(cards: list[dict]) -> str:
    pieces = [card["summary"] for card in cards[:5]]
    return " ".join(pieces)[:260]


def _protagonist_profile(avg_agency: float, cards: list[dict]) -> str:
    if avg_agency >= 7.4:
        action = "主角行动力很强，遇到机会会主动判断、主动出手，不是等剧情推着走。"
    elif avg_agency >= 6.4:
        action = "主角有一定主动性，会围绕已知信息做选择，但还需要继续看后续是否稳定。"
    else:
        action = "这几章里主角形象还没有完全立住，主动性和目标感需要更多章节验证。"
    hook = " ".join(card["chapter_title"] for card in cards[:3])
    return f"{action} 当前人物印象主要来自 {hook} 这几章里的选择和行动。"


def _plot_progress(selected: list[dict], cards: list[dict], all_events: list[str]) -> str:
    range_text = f"第 {selected[0]['index']} - {selected[-1]['index']} 章"
    if all_events:
        event_text = "；".join(dict.fromkeys(all_events[:3]))
        return f"剧情推进到{range_text}：核心设定已经抛出，主角开始围绕关键机会/冲突行动。当前主要进展是：{event_text}"
    return f"剧情推进到{range_text}：这一段主要完成当前阶段的铺垫和转折，后续需要继续看冲突是否升级。"


def list_txt_stories() -> dict:
    TXT_LIBRARY.mkdir(exist_ok=True)
    items = []
    for path in sorted(TXT_LIBRARY.glob("*.txt"), key=lambda item: item.stat().st_mtime, reverse=True):
        text = _read_text(path)
        chapters = parse_chapters(text)
        items.append(
            {
                "id": path.name,
                "title": _story_title(path, text),
                "chapter_count": len(chapters),
                "size_kb": round(path.stat().st_size / 1024, 1),
            }
        )
    return {"items": items, "library_path": str(TXT_LIBRARY)}


def analyze_txt_story(story_id: str, chapters: int = 3, start: int = 1) -> dict:
    path = _story_path(story_id)
    text = _read_text(path)
    parsed = parse_chapters(text)
    start_index = max(0, min(start - 1, max(len(parsed) - 1, 0)))
    chapter_count = max(1, min(chapters, 20))
    selected = parsed[start_index : start_index + chapter_count]
    if not selected:
        raise ValueError("txt has no readable chapters")

    title = _story_title(path, text)
    merged = "\n".join(chapter["text"] for chapter in selected)
    cards = [_chapter_card(chapter) for chapter in selected]
    characters = _extract_characters(merged)
    all_events = [event for card in cards for event in card["key_events"]]
    all_threads = [thread for card in cards for thread in card["open_threads"]]
    avg_hook = sum(card["scores"]["hook"] for card in cards) / len(cards)
    avg_pace = sum(card["scores"]["pace"] for card in cards) / len(cards)
    avg_agency = sum(card["scores"]["agency"] for card in cards) / len(cards)
    avg_match = sum(card["scores"]["profile_match"] for card in cards) / len(cards)

    range_label = f"第 {selected[0]['index']} - {selected[-1]['index']} 章"
    if avg_hook >= 7.8 and avg_match >= 7.0:
        verdict = f"值得继续读：{range_label}已经给出稳定爽点/悬念和画像命中点。"
    elif avg_hook >= 6.8:
        verdict = f"建议继续观察：{range_label}钩子成立，但还要验证后续节奏和设定兑现。"
    else:
        verdict = f"暂时放入低优先级：{range_label}正文信号不足，可能不适合当前偏好。"

    fit_points = []
    if avg_match >= 7:
        fit_points.append("命中你近期偏好的悬疑、规则、高压和诡异氛围。")
    if avg_hook >= 7:
        fit_points.append("前三章持续抛出未解问题，不只依赖简介吸引。")
    if avg_agency >= 6.8:
        fit_points.append("主角有记录、试探、验证等主动行为，不是被动等待剧情推着走。")

    risk_points = []
    if avg_pace < 6.8:
        risk_points.append("节奏推进偏慢，需要继续观察冲突是否升级。")
    if len(characters) < 2:
        risk_points.append("该范围内人物关系还不够清晰，后续可能需要更多正文支撑。")
    if not risk_points:
        risk_points.append("暂无强负反馈，但仍要验证 5-10 章是否重复同一类悬念。")

    what_happened = _reader_facing_summary(cards)
    protagonist = _protagonist_profile(avg_agency, cards)
    progress = _plot_progress(selected, cards, all_events)

    return {
        "story": {
            "id": path.name,
            "title": title,
            "chapter_count": len(parsed),
            "analyzed_chapters": len(selected),
            "range_start": selected[0]["index"],
            "range_end": selected[-1]["index"],
        },
        "source_policy": "分析对象来自本地 txt_library 中的 TXT；报告只展示结构化摘要，不展示长段正文。",
        "aggregate": {
            "headline": f"{range_label}正文级无剧透试读报告",
            "recap": " ".join(card["summary"] for card in cards)[:280],
            "what_happened": what_happened,
            "protagonist_profile": protagonist,
            "plot_progress": progress,
            "trial_verdict": verdict,
            "fit_points": fit_points,
            "risk_points": risk_points,
            "next_reading_plan": f"继续看第 {selected[-1]['index'] + 1}-{selected[-1]['index'] + 3} 章时，重点验证：核心爽点是否升级、机缘/副本线索是否兑现、主角是否保持主动选择。",
            "scores": {
                "avg_hook": round(avg_hook, 1),
                "avg_pace": round(avg_pace, 1),
                "avg_agency": round(avg_agency, 1),
                "avg_profile_match": round(avg_match, 1),
            },
        },
        "characters": characters,
        "open_threads": list(dict.fromkeys(all_threads))[:6],
        "key_events": list(dict.fromkeys(all_events))[:8],
        "chapter_cards": cards,
    }


def _chunk_ranges(total: int, size: int) -> list[tuple[int, int]]:
    return [(start, min(start + size - 1, total)) for start in range(1, total + 1, size)]


def _range_title(chapters: list[dict]) -> str:
    if not chapters:
        return "未知阶段"
    first_title = re.sub(r"^第[一二三四五六七八九十百千万\d]+[章节回]\s*", "", chapters[0]["title"]).strip()
    last_title = re.sub(r"^第[一二三四五六七八九十百千万\d]+[章节回]\s*", "", chapters[-1]["title"]).strip()
    if first_title and last_title and first_title != last_title:
        return f"{first_title} -> {last_title}"
    return first_title or last_title or f"第 {chapters[0]['index']}-{chapters[-1]['index']} 章"


def _chunk_memory(chapters: list[dict]) -> dict:
    cards = [_chapter_card(chapter) for chapter in chapters]
    merged_events = list(dict.fromkeys(event for card in cards for event in card["key_events"]))[:5]
    avg_agency = sum(card["scores"]["agency"] for card in cards) / len(cards)
    return {
        "range_start": chapters[0]["index"],
        "range_end": chapters[-1]["index"],
        "title": _range_title(chapters),
        "summary": _reader_facing_summary(cards),
        "protagonist_profile": _protagonist_profile(avg_agency, cards),
        "key_events": merged_events,
    }


def _arc_summary(chunks: list[dict]) -> dict:
    start = chunks[0]["range_start"]
    end = chunks[-1]["range_end"]
    summaries = " ".join(chunk["summary"] for chunk in chunks)
    events = list(dict.fromkeys(event for chunk in chunks for event in chunk.get("key_events", [])))[:6]
    return {
        "range_start": start,
        "range_end": end,
        "title": f"第 {start}-{end} 章：{chunks[0]['title']}",
        "summary": summaries[:360],
        "key_events": events,
    }


def _arc_timeline(arcs: list[dict], limit: int = 760) -> str:
    if not arcs:
        return ""
    snippets = []
    for arc in arcs:
        events = "；".join(arc.get("key_events", [])[:3])
        summary = arc["summary"][:110]
        event_text = f" 关键变化：{events}。" if events else ""
        snippets.append(f"第 {arc['range_start']}-{arc['range_end']} 章：{summary}{event_text}")
    timeline = " ".join(snippets)
    return timeline[:limit]


def build_progress_recap(story_id: str, upto: int, recent: int = 15) -> dict:
    path = _story_path(story_id)
    text = _read_text(path)
    parsed = parse_chapters(text)
    if not parsed:
        raise ValueError("txt has no readable chapters")

    upto = max(1, min(upto, len(parsed)))
    recent = max(3, min(recent, 30))
    title = _story_title(path, text)
    included = parsed[:upto]

    chunks = []
    for start, end in _chunk_ranges(upto, 5):
        chunks.append(_chunk_memory(included[start - 1 : end]))

    arcs = []
    for start, end in _chunk_ranges(len(chunks), 5):
        arcs.append(_arc_summary(chunks[start - 1 : end]))

    recent_chapters = included[max(0, upto - recent) :]
    recent_cards = [_chapter_card(chapter) for chapter in recent_chapters]
    recent_events = list(dict.fromkeys(event for card in recent_cards for event in card["key_events"]))[:6]
    avg_agency = sum(card["scores"]["agency"] for card in recent_cards) / len(recent_cards)

    arc_text = _arc_timeline(arcs)

    last_arc = arcs[-1]
    recent_text = _reader_facing_summary(recent_cards)
    protagonist = _protagonist_profile(avg_agency, recent_cards)

    if upto >= len(parsed):
        resume_hint = (
            f"已经回顾到当前 TXT 已导入的最后一章。续读时先记住最近的核心进展："
            f"{'；'.join(recent_events[:3]) or recent_text[:120]}。"
            "如果后续有新章节，可以继续导入并从这里接着生成更新后的续读恢复。"
        )
    else:
        resume_hint = (
            f"续读时先记住最近的核心进展：{'；'.join(recent_events[:3]) or recent_text[:120]}"
            f"。建议从第 {upto + 1} 章继续看，重点观察上一阶段留下的机会、冲突和主角选择是否继续升级。"
        )

    return {
        "story": {
            "id": path.name,
            "title": title,
            "chapter_count": len(parsed),
            "upto": upto,
            "recent_start": recent_chapters[0]["index"],
            "recent_end": recent_chapters[-1]["index"],
        },
        "recap": {
            "what_happened": (
                f"截至第 {upto} 章，前面主线大致经历了这些阶段：{arc_text[:520]}"
            ),
            "protagonist_profile": protagonist,
            "plot_progress": (
                f"剧情目前推进到第 {last_arc['range_start']}-{last_arc['range_end']} 章这一阶段。"
                f"最近第 {recent_chapters[0]['index']}-{recent_chapters[-1]['index']} 章的重点是：{recent_text[:260]}"
            ),
            "resume_hint": resume_hint,
        },
    }
