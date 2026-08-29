"""AI profile schemas — config layer contract (no key material, ever)."""

from typing import Literal

from pydantic import BaseModel, Field

Preset = Literal["dashscope", "deepseek", "openrouter", "custom"]
Endpoint = Literal["chat_completions", "responses"]


class ProfileBase(BaseModel):
    preset: Preset = "custom"
    endpoint: Endpoint = "chat_completions"
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(0.3, ge=0.0, le=2.0)


class ProfileCreate(ProfileBase):
    name: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    api_key: str | None = None          # 可选；提供则写 keychain


class ProfileUpdate(BaseModel):         # 全可选，exclude_unset 后按字段打补丁
    preset: Preset | None = None
    endpoint: Endpoint | None = None
    base_url: str | None = Field(None, min_length=1)
    model: str | None = Field(None, min_length=1)
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    api_key: str | None = None          # 非空 → 覆盖 keychain；空/缺省 → 保留原 key


class ProfileOut(ProfileBase):          # GET/POST/PUT 响应 —— 无任何 key 物料
    name: str
    source: Literal["user", "env"] = "user"
    has_key: bool = False


class ProfileList(BaseModel):
    active_profile: str | None = None
    profiles: list[ProfileOut] = []


class ActiveIn(BaseModel):
    name: str


class TestResult(BaseModel):
    ok: bool
    latency_ms: int | None = None
    error: str | None = None


class TemplatesOut(BaseModel):           # M4c：GET /ai/templates
    defaults: dict[str, str]             # 8 键全文 → 编辑器 placeholder
    overrides: dict[str, str]            # 当前覆盖（已规范化）
    template_hash: str


class TemplatesUpdate(BaseModel):        # PUT /ai/templates
    templates: dict[str, str]            # 8 键全量提交；值 = 覆盖文本或空串（=重置）


class TemplatesSaved(BaseModel):
    overrides: dict[str, str]
    template_hash: str
