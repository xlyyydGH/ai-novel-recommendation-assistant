"""Safe MiniMax configuration for the public repository.

Do not hard-code real API keys. Set MINIMAX_API_KEY in the environment instead.
"""

from __future__ import annotations

import os


MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")

MINIMAX_TIMEOUT_SECONDS = int(os.getenv("MINIMAX_TIMEOUT_SECONDS", "120"))
MINIMAX_MAX_INPUT_CHARS = int(os.getenv("MINIMAX_MAX_INPUT_CHARS", "90000"))
MINIMAX_MAX_OUTPUT_TOKENS = int(os.getenv("MINIMAX_MAX_OUTPUT_TOKENS", "4096"))
