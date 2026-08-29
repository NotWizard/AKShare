"""AI config endpoints — profiles CRUD + connection test + active selection.

Zero key material in responses: `has_key` bool is the only key signal.
Keys live in the keychain (core/keychain.py); config JSON is secret-free.

All mutating endpoints are token-guarded (F4): profile CRUD hits the OS
keychain, /test spends a paid provider ping — none of them may be fireable
by a localhost-CSRF page.
"""

from fastapi import APIRouter, Depends, HTTPException

from backend.app.core import ai_config, commentary, keychain
from backend.app.core.ai_client import test_connection
from backend.app.core.auth import require_token
from backend.app.schemas.ai import (ActiveIn, ProfileCreate, ProfileList,
                                    ProfileOut, ProfileUpdate, TemplatesOut,
                                    TemplatesSaved, TemplatesUpdate, TestResult)

router = APIRouter(prefix="/ai", tags=["ai"])


def _out(p: dict) -> ProfileOut:
    return ProfileOut(**p, has_key=ai_config.key_for(p["name"]) is not None)


def _list() -> ProfileList:
    cfg = ai_config.list_profiles()
    return ProfileList(active_profile=cfg["active_profile"],
                       profiles=[_out(p) for p in cfg["profiles"]])


@router.get("/profiles", response_model=ProfileList)
def list_profiles():
    return _list()


@router.post("/profiles", response_model=ProfileOut,
             dependencies=[Depends(require_token)])
def create_profile(body: ProfileCreate):
    try:
        p = ai_config.create(body.model_dump(exclude={"api_key"}))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    # keychain 写失败 → profile 已存、key 未存，500 提示重新保存密钥
    if body.api_key and not keychain.set_key(body.name, body.api_key):
        raise HTTPException(status_code=500, detail="profile 已保存，但密钥写入失败，请重新编辑保存密钥")
    return _out(p)


@router.put("/profiles/{name}", response_model=ProfileOut,
            dependencies=[Depends(require_token)])
def update_profile(name: str, body: ProfileUpdate):
    patch = body.model_dump(exclude_unset=True, exclude={"api_key"})
    try:
        p = ai_config.update(name, patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if body.api_key and not keychain.set_key(name, body.api_key):
        raise HTTPException(status_code=500, detail="profile 已保存，但密钥写入失败，请重新编辑保存密钥")
    return _out(p)


@router.delete("/profiles/{name}", dependencies=[Depends(require_token)])
def delete_profile(name: str):
    try:
        ai_config.delete(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


@router.post("/profiles/{name}/test", response_model=TestResult,
             dependencies=[Depends(require_token)])
def test_profile(name: str):
    p = ai_config.get(name)
    if p is None:
        raise HTTPException(status_code=404, detail=f"profile 不存在：{name}")
    key = ai_config.key_for(name)
    if not key:
        raise HTTPException(status_code=400, detail="未配置密钥")
    return TestResult(**test_connection(p, key))


@router.post("/active", response_model=ProfileList,
             dependencies=[Depends(require_token)])
def set_active(body: ActiveIn):
    try:
        ai_config.set_active(body.name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _list()   # 设默认后直接回最新列表，省一次 GET


@router.get("/templates", response_model=TemplatesOut)
def get_templates():
    """默认 8 模板全文 + 当前覆盖（规范化）+ template_hash。"""
    overrides = {k: v for k, v in (ai_config.load().get("templates") or {}).items()
                 if k in commentary.DEFAULT_TEMPLATES and isinstance(v, str) and v.strip()}
    return TemplatesOut(defaults=dict(commentary.DEFAULT_TEMPLATES),
                        overrides=overrides,
                        template_hash=commentary.template_hash())


@router.put("/templates", response_model=TemplatesSaved,
            dependencies=[Depends(require_token)])
def save_templates(body: TemplatesUpdate):
    """整 map 保存覆盖（空串 = 移除）；经 _save 钩子 mark_stale。"""
    try:
        overrides, thash = ai_config.set_templates(body.templates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TemplatesSaved(overrides=overrides, template_hash=thash)
