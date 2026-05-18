"""Dependency-free HTTP server for the demo.

Run with:

    python run.py

The server exposes the API described in the README and serves the static
frontend from /static plus index.html at /.
"""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .data import FEEDBACK_OPTIONS, USERS, get_book
from .recommender import (
    all_books,
    book_analysis,
    build_user_profile,
    chapter_summary,
    chapters_for_book,
    recap,
    recommend,
    record_feedback,
    similar_readers,
)
from .fanqie_recommender import fanqie_diagnostics, fanqie_recommendations, record_fanqie_feedback
from .public_recall import public_candidates, public_recall_recommendations
from .chapter_memory import analyze_chapter, chapter_memory_for_book
from .txt_story_analyzer import analyze_txt_story, build_progress_recap, list_txt_stories
from .minimax_story_llm import minimax_progress_recap, minimax_status, minimax_story_analysis


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
FANQIE_PROFILE = ROOT / "app" / "fanqie_user_profile.json"


def json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, text: str, status: int = 200) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if not length:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "NovelAssistantDemo/1.0"

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}

        try:
            if path == "/api/health":
                return json_response(self, {"ok": True, "service": "AI 小说试读决策与续读恢复助手"})
            if path == "/api/users":
                return json_response(self, {"items": USERS})
            if path == "/api/books":
                return json_response(self, {"items": all_books()})
            if path == "/api/fanqie/profile":
                if FANQIE_PROFILE.exists():
                    return json_response(self, json.loads(FANQIE_PROFILE.read_text(encoding="utf-8")))
                return json_response(self, {"error": "fanqie profile not imported"}, status=404)
            if path == "/api/fanqie/recommendations":
                limit = int(query.get("limit", "30"))
                return json_response(self, fanqie_recommendations(limit=limit))
            if path == "/api/fanqie/diagnostics":
                return json_response(self, fanqie_diagnostics())
            if path == "/api/public-recall/candidates":
                return json_response(self, {"items": public_candidates()})
            if path == "/api/public-recall/recommendations":
                limit = int(query.get("limit", "12"))
                return json_response(self, public_recall_recommendations(limit=limit))
            if path == "/api/chapter-memory":
                return json_response(
                    self,
                    chapter_memory_for_book(
                        query.get("book_id", query.get("title", "")),
                        query.get("title", ""),
                    ),
                )
            if path == "/api/txt-stories":
                return json_response(self, list_txt_stories())
            if path == "/api/txt-story-analysis":
                return json_response(
                    self,
                    analyze_txt_story(
                        query.get("id", ""),
                        int(query.get("chapters", "3")),
                        int(query.get("start", "1")),
                    ),
                )
            if path == "/api/txt-progress-recap":
                story_id = query.get("id", "")
                upto = int(query.get("upto", "1"))
                recent = int(query.get("recent", "15"))
                if query.get("llm", "1") == "0":
                    return json_response(self, build_progress_recap(story_id, upto, recent))
                return json_response(
                    self,
                    minimax_progress_recap(story_id, upto, recent, query.get("force", "0") == "1"),
                )
            if path == "/api/llm/status":
                return json_response(self, minimax_status())
            if path == "/api/txt-story-llm-analysis":
                return json_response(
                    self,
                    minimax_story_analysis(
                        query.get("id", ""),
                        int(query.get("start", "1")),
                        int(query.get("chapters", "3")),
                        query.get("force", "0") == "1",
                    ),
                )
            if path == "/api/profile":
                return json_response(self, build_user_profile(query.get("user_id", "user_xly")))
            if path == "/api/similar-readers":
                return json_response(self, {"items": similar_readers(query.get("user_id", "user_xly"))})
            if path == "/api/recommendations":
                limit = int(query.get("limit", "20"))
                return json_response(self, recommend(query.get("user_id", "user_xly"), limit=limit))

            segments = [part for part in path.split("/") if part]
            if len(segments) >= 3 and segments[0] == "api" and segments[1] == "books":
                book_id = segments[2]
                book = get_book(book_id)
                if not book:
                    return json_response(self, {"error": "book not found"}, status=404)
                if len(segments) == 3:
                    return json_response(self, book)
                if len(segments) == 4 and segments[3] == "analysis":
                    return json_response(self, book_analysis(book_id, query.get("user_id", "user_xly")))
                if len(segments) == 4 and segments[3] == "chapters":
                    return json_response(self, {"items": chapters_for_book(book_id)})
                if len(segments) == 5 and segments[3] == "chapters":
                    return json_response(self, chapter_summary(book_id, segments[4]))
                if len(segments) == 4 and segments[3] == "recap":
                    return json_response(
                        self,
                        recap(book_id, query.get("user_id", "user_xly"), query.get("before_chapter")),
                    )

            return self.serve_static(path)
        except Exception as exc:  # pragma: no cover - demo safeguard
            return json_response(self, {"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            payload = read_json_body(self)
            if path == "/api/feedback":
                return json_response(
                    self,
                    record_feedback(
                        payload.get("user_id", "user_xly"),
                        payload["book_id"],
                        payload.get("feedback_type", "不感兴趣"),
                        payload.get("reason", ""),
                    ),
                )
            if path == "/api/fanqie/feedback":
                result = record_fanqie_feedback(
                    str(payload["book_id"]),
                    payload.get("feedback_type", "不感兴趣"),
                    payload.get("reason", ""),
                )
                result["recommendations"] = fanqie_recommendations(limit=8)
                return json_response(self, result)
            if path == "/api/analyze":
                # Lightweight mock analysis for custom text typed by the user.
                intro = payload.get("intro", "")
                chapters = payload.get("chapters", "")
                positive = []
                negative = []
                text = intro + "\n" + chapters
                for tag in ["规则", "悬念", "智商", "反套路", "群像", "女强", "快节奏"]:
                    if tag in text:
                        positive.append(tag)
                for tag in ["拖沓", "降智", "误会", "套路", "文笔白"]:
                    if tag in text:
                        negative.append(tag)
                return json_response(
                    self,
                    {
                        "positive_tags": positive or ["待人工复核"],
                        "negative_tags": negative,
                        "hook_score": 8.2 if positive else 6.8,
                        "intro_consistency_score": 8.0 if intro and chapters else 6.5,
                        "summary": "这是本地 Mock LLM 分析结果；接入真实 LLM API 后可替换为模型输出。",
                    },
                )
            if path == "/api/chapter-memory/analyze":
                return json_response(self, analyze_chapter(payload))
            return json_response(self, {"error": "not found"}, status=404)
        except KeyError as exc:
            return json_response(self, {"error": f"missing field: {exc}"}, status=400)
        except Exception as exc:  # pragma: no cover - demo safeguard
            return json_response(self, {"error": str(exc)}, status=500)

    def serve_static(self, path: str) -> None:
        if path in {"/", ""}:
            file_path = STATIC_DIR / "index.html"
        elif path.startswith("/static/"):
            file_path = ROOT / path.lstrip("/")
        else:
            return text_response(self, "Not found", status=404)

        file_path = file_path.resolve()
        if not str(file_path).startswith(str(STATIC_DIR.resolve())) or not file_path.exists():
            return text_response(self, "Not found", status=404)

        content = file_path.read_bytes()
        mime, _ = mimetypes.guess_type(str(file_path))
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args) -> None:
        print("%s - %s" % (self.address_string(), format % args))


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"AI Novel Recommendation Assistant running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        server.server_close()
