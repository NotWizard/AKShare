"""AI commentary schema — mirrors the commentary SQLite row."""

from pydantic import BaseModel


class Commentary(BaseModel):
    ts: str | None = None               # generation time ISO
    data_as_of: str | None = None       # data cutoff date the comment is based on
    composite_score: int | None = None
    text: str                           # generated commentary
    model: str | None = None            # model identifier
    stale: bool = False                 # data refreshed since generation
    status: str = "ok"                  # ok | generating | empty | error
    msg: str | None = None              # error / generating message
