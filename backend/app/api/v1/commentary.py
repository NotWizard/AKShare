"""Commentary endpoints — AI macro analysis text.

GET  /commentary        → latest batch (or generating/empty status)
POST /commentary/regenerate → sync generate (caller waits), returns new batch.
    Token-guarded (F4): it spends money on paid LLM calls, and any page the
    user browsed could otherwise fire it with
    ``fetch(…, {method:'POST', mode:'no-cors'})`` — a billing attack that needs
    no response body, so CORS never blocked it.
GET  /commentary/history → batch index (desc); ?ts=… single-batch detail
"""

from fastapi import APIRouter, Depends, HTTPException

from backend.app.core import commentary
from backend.app.core.auth import require_token
from backend.app.schemas.commentary import Commentary

router = APIRouter(prefix="/commentary", tags=["commentary"])


@router.get("", response_model=Commentary)
def get_commentary():
    """Latest AI commentary (or status=generating/empty)."""
    return Commentary(**commentary.get_current())


@router.post("/regenerate", response_model=Commentary,
             dependencies=[Depends(require_token)])
def regenerate():
    """Re-run the model on current data (sync). Returns the new commentary."""
    return Commentary(**commentary.generate(blocking=True))


@router.get("/history")
def history(ts: str | None = None):
    """批次索引（ts 倒序）；带 ?ts=… 返回该批完整详情，未知 ts → 404。"""
    if ts is None:
        return {"items": commentary.history_index()}
    batch = commentary.get_batch(ts)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"批次不存在：{ts}")
    return Commentary(**batch)
