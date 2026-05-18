from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from . import llm_settings
from .txt_story_analyzer import build_progress_recap, _read_text, _story_path, _story_title, parse_chapters


CACHE_DIR = Path(__file__).with_name("llm_cache")
PROMPT_VERSION = "minimax_story_v3_trial_decision"
PROGRESS_PROMPT_VERSION = "minimax_progress_recap_v3_recovery"


def _api_key() -> str:
    return os.getenv("MINIMAX_API_KEY") or llm_settings.MINIMAX_API_KEY.strip()


def minimax_status() -> dict:
    key = _api_key()
    return {
        "provider": "MiniMax",
        "model": llm_settings.MINIMAX_MODEL,
        "base_url": llm_settings.MINIMAX_BASE_URL,
        "configured": bool(key),
        "config_file": "app/llm_settings.py",
        "note": "在 app/llm_settings.py 填写 MINIMAX_API_KEY，或设置环境变量 MINIMAX_API_KEY。",
    }


def _endpoint() -> str:
    return llm_settings.MINIMAX_BASE_URL.rstrip("/") + "/chat/completions"


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _cache_key(story_id: str, start: int, chapters: int, prompt_text: str) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "story_id": story_id,
                "start": start,
                "chapters": chapters,
                "model": llm_settings.MINIMAX_MODEL,
                "prompt_version": PROMPT_VERSION,
                "prompt_hash": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return digest[:32]


def _progress_cache_key(story_id: str, upto: int, recent: int, prompt_text: str) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "story_id": story_id,
                "upto": upto,
                "recent": recent,
                "model": llm_settings.MINIMAX_MODEL,
                "prompt_version": PROGRESS_PROMPT_VERSION,
                "prompt_hash": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return f"progress_{digest[:32]}"


def _selected_chapters(story_id: str, start: int, chapters: int) -> tuple[Path, str, list[dict]]:
    path = _story_path(story_id)
    text = _read_text(path)
    parsed = parse_chapters(text)
    if not parsed:
        raise ValueError("txt has no readable chapters")
    start_index = max(0, min(start - 1, len(parsed) - 1))
    chapter_count = max(1, min(chapters, 20))
    selected = parsed[start_index : start_index + chapter_count]
    return path, _story_title(path, text), selected


def _progress_sample_indices(upto: int, recent: int) -> list[int]:
    anchors = [1, 2, 3, 5, 10, 20]
    anchors.extend(range(25, upto + 1, 25))
    anchors.extend(range(max(1, upto - recent + 1), upto + 1))
    anchors.append(upto)
    return sorted({index for index in anchors if 1 <= index <= upto})


def _excerpt(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", "\n", text.strip())
    if len(compact) <= limit:
        return compact
    head = max(200, int(limit * 0.62))
    tail = max(120, limit - head)
    return compact[:head] + "\n[中间内容已压缩]\n" + compact[-tail:]


def _progress_context(story_id: str, upto: int, recent: int) -> tuple[dict, str, str]:
    path = _story_path(story_id)
    text = _read_text(path)
    parsed = parse_chapters(text)
    if not parsed:
        raise ValueError("txt has no readable chapters")

    upto = max(1, min(upto, len(parsed)))
    recent = max(3, min(recent, 30))
    title = _story_title(path, text)
    indices = _progress_sample_indices(upto, recent)
    recent_start = max(1, upto - recent + 1)
    parts = []
    for index in indices:
        chapter = parsed[index - 1]
        limit = 1500 if index >= recent_start or index <= 3 else 760
        parts.append(
            f"### 第 {chapter['index']} 章：{chapter['title']}\n"
            f"{_excerpt(chapter['text'], limit)}"
        )
    context = "\n\n".join(parts)
    if len(context) > llm_settings.MINIMAX_MAX_INPUT_CHARS:
        context = context[: llm_settings.MINIMAX_MAX_INPUT_CHARS] + "\n[后续抽样内容已因长度限制压缩]"
    story = {
        "id": path.name,
        "title": title,
        "chapter_count": len(parsed),
        "upto": upto,
        "recent_start": recent_start,
        "recent_end": upto,
    }
    return story, title, context


def _build_progress_prompt(story: dict, context: str) -> tuple[list[dict], str]:
    system = (
        "你是面向网文读者的 AI 阅读助手。你要根据用户本地 TXT 的抽样章节，"
        "生成“读到第 N 章”的续读恢复备忘录。只总结 1-N 章，不剧透 N 章之后。"
        "不要引用长段原文，不要逐章罗列，不要输出技术过程、评分、调试信息。"
        "答案必须短、完整、像给读者看的续读备忘录。必须只输出合法 JSON。"
    )
    user = f"""
书名：{story['title']}
总章数：{story['chapter_count']}
用户读到：第 {story['upto']} 章
最近重点章节范围：第 {story['recent_start']}-{story['recent_end']} 章

请输出这个 JSON 结构：
{{
  "recap": {{
    "what_happened": "120-180字，概括1到N章主线，不逐章列。",
    "protagonist_profile": "90-140字，主角姓名、性格、能力、行事风格。",
    "plot_progress": "90-140字，剧情到第N章的当前局面和最近重点。",
    "resume_hint": "60-100字，从第N+1章接着读前要记住的关键点。"
  }}
}}

硬性要求：
1. 四个字段都必须以完整句号、问号或感叹号结尾。
2. 不要写超过要求字数的长段落。
3. 不要把“第1章、第25章、第50章”这种采样过程展示给用户。
4. 不要输出 JSON 之外的任何内容。

抽样章节如下：
{context}
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}], user


def _clip_at_sentence(value: object, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_chars:
        return text if text.endswith(("。", "！", "？", ".", "!", "?")) else text + "。"
    clipped = text[:max_chars]
    last = max(clipped.rfind(mark) for mark in "。！？.!?")
    if last >= max_chars * 0.55:
        clipped = clipped[: last + 1]
    else:
        clipped = clipped.rstrip("，,；;、：:")
        clipped += "。"
    return clipped


def _shape_progress_recap(recap: dict, fallback: dict) -> dict:
    return {
        "what_happened": _clip_at_sentence(recap.get("what_happened") or fallback["what_happened"], 210),
        "protagonist_profile": _clip_at_sentence(
            recap.get("protagonist_profile") or fallback["protagonist_profile"], 160
        ),
        "plot_progress": _clip_at_sentence(recap.get("plot_progress") or fallback["plot_progress"], 170),
        "resume_hint": _clip_at_sentence(recap.get("resume_hint") or fallback["resume_hint"], 130),
    }


def _chapter_context(selected: list[dict]) -> tuple[str, bool]:
    max_chars = llm_settings.MINIMAX_MAX_INPUT_CHARS
    budget_per_chapter = max(2000, max_chars // max(len(selected), 1))
    truncated = False
    parts = []
    for chapter in selected:
        body = chapter["text"].strip()
        if len(body) > budget_per_chapter:
            body = body[:budget_per_chapter] + "\n[本章过长，已截断给模型；规则层仍保留完整章节边界。]"
            truncated = True
        parts.append(f"## 第 {chapter['index']} 章：{chapter['title']}\n{body}")
    joined = "\n\n".join(parts)
    if len(joined) > max_chars:
        joined = joined[:max_chars] + "\n[输入超过最大字符预算，已截断。]"
        truncated = True
    return joined, truncated


def _build_prompt(story_id: str, title: str, selected: list[dict]) -> tuple[list[dict], str, bool]:
    range_start = selected[0]["index"]
    range_end = selected[-1]["index"]
    chapter_text, truncated = _chapter_context(selected)
    system = (
        "你是一个小说阅读助手，任务是基于用户已经合法提供的小说正文做结构化阅读理解。"
        "你不能编造正文中没有的信息；不能输出大段原文；无剧透报告只讨论风格、节奏、设定兑现和阅读风险。"
        "输出必须是合法 JSON，不要 Markdown，不要解释推理过程。"
    )
    user = f"""
请分析小说《{title}》第 {range_start}-{range_end} 章。

核心任务：做“新书三章止损”判断。请直接回答正文是否兑现标题/简介承诺、主角是否讨喜、节奏是否值得继续追。

用户画像：偏好悬疑/规则/游戏入侵/爽文推进/高行动力主角；讨厌简介党、节奏拖沓、主角降智、设定不兑现。

请返回如下 JSON 字段：
{{
  "story": {{
    "title": "{title}",
    "range_start": {range_start},
    "range_end": {range_end}
  }},
  "no_spoiler_trial_report": {{
    "verdict": "面向未读者的无剧透试读结论",
    "fit_points": ["为什么适合该用户"],
    "risk_points": ["可能不适合的地方"],
    "continue_plan": "建议继续读哪几章、验证什么",
    "scores": {{
      "hook": 0-10,
      "pace": 0-10,
      "protagonist_agency": 0-10,
      "profile_match": 0-10
    }}
  }},
  "plot_recap": {{
    "spoiler_level": "仅包含第 {range_start}-{range_end} 章已读范围",
    "what_happened": "这几章主要讲了什么，160字以内",
    "current_progress": "剧情大概推进到什么地步了，120字以内"
  }},
  "protagonist_profile": {{
    "name": "主角名，不确定则写主角",
    "image": "主角的人物形象/性格/行事风格，120字以内",
    "motivation": "主角当前目标或驱动力，80字以内",
    "agency": "主角主动性如何，80字以内"
  }},
  "chapter_brief": [
    {{"chapter_index": 1, "chapter_title": "标题", "summary": "本章讲了什么，60字以内"}}
  ]
}}

正文：
{chapter_text}
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}], user, truncated


def _call_minimax(messages: list[dict]) -> dict:
    key = _api_key()
    if not key:
        raise RuntimeError("MiniMax API key is not configured")

    payload = {
        "model": llm_settings.MINIMAX_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": llm_settings.MINIMAX_MAX_OUTPUT_TOKENS,
        "stream": False,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        _endpoint(),
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        timeout = max(llm_settings.MINIMAX_TIMEOUT_SECONDS, 240)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"MiniMax HTTP {exc.code}: {detail}") from exc

    body = json.loads(raw)
    content = body["choices"][0]["message"]["content"]
    parsed = _extract_json(content)
    return {
        "provider": "MiniMax",
        "model": llm_settings.MINIMAX_MODEL,
        "raw_usage": body.get("usage", {}),
        "analysis": parsed,
    }


def minimax_story_analysis(story_id: str, start: int = 1, chapters: int = 3, force: bool = False) -> dict:
    status = minimax_status()
    if not status["configured"]:
        return {
            "ok": False,
            "configured": False,
            "status": status,
            "error": "MiniMax API key is not configured",
        }

    _, title, selected = _selected_chapters(story_id, start, chapters)
    messages, prompt_text, truncated = _build_prompt(story_id, title, selected)
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / f"{_cache_key(story_id, start, chapters, prompt_text)}.json"
    if cache_path.exists() and not force:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached["cache_hit"] = True
        return cached

    result = _call_minimax(messages)
    payload = {
        "ok": True,
        "configured": True,
        "cache_hit": False,
        "input": {
            "story_id": story_id,
            "title": title,
            "range_start": selected[0]["index"],
            "range_end": selected[-1]["index"],
            "chapters": len(selected),
            "truncated": truncated,
        },
        **result,
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def minimax_progress_recap(story_id: str, upto: int = 1, recent: int = 15, force: bool = False) -> dict:
    local = build_progress_recap(story_id, upto, recent)
    status = minimax_status()
    if not status["configured"]:
        return local

    story, _, context = _progress_context(story_id, upto, recent)
    messages, prompt_text = _build_progress_prompt(story, context)
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / f"{_progress_cache_key(story_id, story['upto'], recent, prompt_text)}.json"
    if cache_path.exists() and not force:
        return json.loads(cache_path.read_text(encoding="utf-8"))

    try:
        result = _call_minimax(messages)
        analysis = result.get("analysis", {})
        recap = analysis.get("recap", analysis)
        merged = _shape_progress_recap(recap, local["recap"])
        payload = {"story": story, "recap": merged}
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    except Exception:
        return local
