"""AI commentary schema — v2 batch shape (overall + sections + provenance)."""

from pydantic import BaseModel


class Provenance(BaseModel):
    model: str | None = None
    endpoint: str | None = None
    template_hash: str | None = None
    data_as_of: dict[str, str | None] | None = None   # 来源表 → 最新日期（表空 null）
    profile: str | None = None
    generated_at: str | None = None


class Commentary(BaseModel):
    status: str = "ok"                 # ok | generating | empty | error
    msg: str | None = None
    hint: str | None = None            # 无 profile/key 时给前端 CTA 路由（/ai-settings）
    stale: bool = False
    regenerating: bool = False         # 生成在途但展示上一批（F10 语义合并）
    overall: str = ""
    sections: dict[str, str] = {}
    provenance: Provenance | None = None


class BatchItem(BaseModel):            # M4c：history 索引行（每批一行）
    generated_at: str
    model: str | None = None
    profile: str | None = None
    template_hash: str | None = None
    status: str = "ok"                 # 落库批次必然完整，恒 ok
    stale: bool = False
    overall_preview: str = ""          # overall 前 80 字（超长加「…」）


class HistoryIndex(BaseModel):
    items: list[BatchItem] = []
