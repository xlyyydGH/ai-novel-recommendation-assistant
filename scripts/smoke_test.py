from __future__ import annotations

import json
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE = "http://127.0.0.1:8000"


def get(path: str) -> dict:
    with urlopen(BASE + quote(path, safe="/:?=&%"), timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post(path: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(BASE + path, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    health = get("/api/health")
    assert health["ok"] is True

    recs = get("/api/recommendations?user_id=user_xly&limit=5")
    assert recs["items"], "recommendations should not be empty"
    first = recs["items"][0]
    assert "reason" in first and "drop_risk" in first

    fanqie_recs = get("/api/fanqie/recommendations?limit=5")
    assert fanqie_recs["items"], "fanqie recommendations should not be empty"
    assert fanqie_recs["pipeline"], "fanqie recommendation pipeline should be exposed"
    assert "metrics" in fanqie_recs and fanqie_recs["metrics"]["candidate_count"] > 0
    assert "components" in fanqie_recs["items"][0]

    diagnostics = get("/api/fanqie/diagnostics")
    assert diagnostics["metrics"]["explain_coverage"] >= 0

    public_recall = get("/api/public-recall/recommendations?limit=3")
    assert public_recall["items"], "public recall should return candidates"
    assert public_recall["scope_note"].startswith("公开候选召回")
    assert public_recall["items"][0]["trial_report"]["headline"] == "无剧透选书报告"

    memory_result = post(
        "/api/chapter-memory/analyze",
        {
            "book_id": "smoke_memory_book",
            "title": "烟测规则怪谈",
            "chapter_index": 1,
            "chapter_title": "第 1 章 宿舍规则",
            "chapter_text": "宿舍门口贴着三条规则，夜里十二点后不能开门，听见敲门声必须保持安静。主角发现手机出现隐藏提示，决定利用规则漏洞救下同伴。走廊尽头传来脚步声，宿管的身份仍然异常，所有人都意识到违反规则会受到惩罚。",
        },
    )
    assert memory_result["card"]["summary"]
    assert "chapter_text" not in memory_result["card"]
    memory = get("/api/chapter-memory?book_id=smoke_memory_book&title=烟测规则怪谈")
    assert memory["cards"], "chapter memory should be saved as structured cards"

    stories = get("/api/txt-stories")
    assert stories["items"], "txt library should expose at least one sample story"
    story = next((item for item in stories["items"] if item["chapter_count"] >= 30), stories["items"][0])
    txt_report = get(f"/api/txt-story-analysis?id={story['id']}&chapters=3")
    assert txt_report["chapter_cards"], "txt analysis should read chapter cards"
    assert txt_report["aggregate"]["trial_verdict"], "txt analysis should generate trial verdict"
    assert txt_report["characters"], "txt analysis should extract character signals"
    start = 20 if story["chapter_count"] >= 24 else 1
    range_chapters = 5 if story["chapter_count"] >= start + 4 else story["chapter_count"] - start + 1
    ranged_report = get(f"/api/txt-story-analysis?id={story['id']}&start={start}&chapters={range_chapters}")
    assert ranged_report["story"]["range_start"] == start
    assert len(ranged_report["chapter_cards"]) == range_chapters
    progress_upto = min(300, story["chapter_count"])
    progress = get(f"/api/txt-progress-recap?id={story['id']}&upto={progress_upto}&recent=15&llm=0")
    assert progress["story"]["upto"] == progress_upto
    assert progress["recap"]["what_happened"], "progress recap should summarize previous plot"
    assert progress["recap"]["protagonist_profile"], "progress recap should expose protagonist profile"
    assert progress["recap"]["plot_progress"], "progress recap should expose current progress"
    llm_status = get("/api/llm/status")
    assert llm_status["provider"] == "MiniMax"

    analysis = get(f"/api/books/{first['book_id']}/analysis?user_id=user_xly")
    assert analysis["intro_consistency_score"] > 0

    post(
        "/api/feedback",
        {"user_id": "user_xly", "book_id": first["book_id"], "feedback_type": "不感兴趣", "reason": "冒烟测试"},
    )

    print("smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
