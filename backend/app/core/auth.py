"""Local capability token guarding the mutating endpoints (F4).

The threat is NOT a LAN attacker — uvicorn binds 127.0.0.1 — it is **localhost
CSRF**: any page the user happens to browse can aim a request at
``http://localhost:8000/api/v1/…``. CORS does not stop the request from being
SENT (it only stops a cross-origin page from READING the response), and the
attacker never needs to read it:

    <img src="http://localhost:8000/api/v1/crcl/refresh/stream">   → full collect
    fetch('…/api/v1/commentary/regenerate', {method:'POST', mode:'no-cors'})
                                                                  → paid LLM call

So the cure has two halves. Half one lives in the API layer: the mutation is back
on POST only, and the SSE GET merely subscribes to an already-created job. Half
two is here: a capability the attacker page cannot obtain.

    * a random token is generated on startup and written to ``data/.api_token``
      with mode 0600 (gitignored, never logged, never printed);
    * ``require_token`` rejects every mutating request that does not present it
      in the ``X-API-Token`` header — 401 when absent, 403 when wrong, both with
      an actionable message instead of a 500;
    * the SPA is served by THIS process, so it reads the token same-origin from
      ``GET /api/v1/session``.

A CSRF page cannot read ``data/.api_token`` (no filesystem access) and cannot
read ``/api/v1/session``'s body (cross-origin), so it can never present the
token — while the same-origin SPA gets it for free.
"""

import logging
import os
import secrets
from pathlib import Path

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOKEN_PATH = PROJECT_ROOT / "data" / ".api_token"
HEADER_NAME = "X-API-Token"

# Process-local cache of the active token; the file is only the hand-off channel
# (and the fallback for a process that never ran the lifespan hook).
_TOKEN: str | None = None


def rotate_token() -> str:
    """Generate a fresh token, cache it, and persist it 0600. Never logs it.

    Called once from the app lifespan, so a restart invalidates any token an
    old tab is holding (the frontend re-reads ``/api/v1/session`` on 401/403).
    The in-memory cache is set BEFORE the write so a read-only ``data/`` degrades
    to "works until restart" instead of breaking every POST.
    """
    global _TOKEN
    token = secrets.token_urlsafe(32)
    _TOKEN = token
    try:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        # O_CREAT with 0o600 + explicit chmod: never group/world readable, not
        # even for the instant between create and chmod, and a pre-existing
        # looser file gets tightened rather than trusted.
        fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(token + "\n")
        os.chmod(TOKEN_PATH, 0o600)
    except OSError as e:
        logger.warning("[auth] 无法写入本机令牌文件 %s: %s（本进程内存中的令牌仍有效）",
                       TOKEN_PATH, e.__class__.__name__)
    return token


def current_token() -> str:
    """The active token: memory → file → generate.

    Lazy on purpose: a process that imported the app without running its
    lifespan (tests, ``uvicorn --factory`` probes, scripts) still has a
    WELL-DEFINED secret, so the guard can never degrade into "accept anything".
    """
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    try:
        existing = TOKEN_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        existing = ""
    if existing:
        _TOKEN = existing
        return existing
    return rotate_token()


def require_token(
    x_api_token: str | None = Header(default=None, alias=HEADER_NAME),
) -> None:
    """FastAPI dependency for every state-changing endpoint.

    ``compare_digest`` so a wrong token cannot be recovered byte-by-byte from
    response timing. Raises before the endpoint body runs, so a rejected request
    provably has no side effect.
    """
    if not x_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"缺少本机令牌：请携带 {HEADER_NAME} 头（同源页面可从 GET /api/v1/session 获取）",
        )
    if not secrets.compare_digest(x_api_token, current_token()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="本机令牌无效或已过期：请刷新页面重新获取 /api/v1/session",
        )
