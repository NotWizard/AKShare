"""AI profile config store — data/ai_config.json + COMMENTARY_* env fallback.

Plain JSON, no secrets (keys live in the keychain, core/keychain.py).
ponytail: whole-file read/write per op — profiles are few, edits rare.
"""

import json
import os
import re
import threading
from pathlib import Path

from backend.app.core import keychain

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "data" / "ai_config.json"   # 测试 monkeypatch 此常量
NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")
_lock = threading.Lock()   # ponytail: 全局单锁；profile 编辑是低频人工操作，无并发压力

_DEFAULT = {"active_profile": None, "profiles": []}


def load() -> dict:
    """文件缺失/损坏 → 默认结构（自愈，不 500）。"""
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict) or not isinstance(cfg.get("profiles"), list):
            return dict(_DEFAULT, profiles=[], templates={})
        cfg.setdefault("active_profile", None)
        cfg.setdefault("templates", {})   # M4b：模板覆盖存储结构（编辑器与写入路径 M4c）
        return cfg
    except Exception:
        return dict(_DEFAULT, profiles=[], templates={})


def _save(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)   # 原子，防半截文件丢配置
    try:
        from backend.app.core import commentary   # 延迟 import：ai_config ↔ commentary 循环防护
        commentary.mark_stale()                   # ponytail: 配置变更只标 stale，重生成由用户/refresh 触发
    except Exception:
        pass


def env_profile() -> dict | None:
    """三件 COMMENTARY_* env 全部非空时合成只读 profile「env」（不落盘）。

    每次动态读 env（与 commentary.py 的 import 期读取解耦，测试可 monkeypatch）。
    """
    base_url = os.getenv("COMMENTARY_BASE_URL", "")
    api_key = os.getenv("COMMENTARY_API_KEY", "")
    model = os.getenv("COMMENTARY_MODEL", "")
    if not (base_url and api_key and model):
        return None
    return {"name": "env", "source": "env", "preset": "custom",
            "endpoint": "chat_completions", "base_url": base_url,
            "model": model, "temperature": 0.3}


def list_profiles() -> dict:
    """{"active_profile": 有效值, "profiles": [user... + env?]}。

    active 指向不存在的 profile 时回退 env 再回退 null（现状不破坏：
    没有任何 profile 时 active 解析落到 env —— 即今天 commentary 的行为）。
    """
    with _lock:
        cfg = load()
    profiles = [dict(p, source="user") for p in cfg["profiles"]]
    env = env_profile()
    if env:
        profiles.append(env)
    names = {p["name"] for p in profiles}
    active = cfg.get("active_profile")
    if active not in names:
        active = "env" if env else None
    return {"active_profile": active, "profiles": profiles}


def get(name: str) -> dict | None:
    if name == "env":
        return env_profile()
    with _lock:
        cfg = load()
    for p in cfg["profiles"]:
        if p.get("name") == name:
            return dict(p, source="user")
    return None


def create(p: dict) -> dict:
    """重名（含内置 env）→ ValueError（路由转 409）。"""
    name = p["name"]
    if not re.fullmatch(NAME_RE, name):
        raise ValueError(f"非法 name：{name}")
    with _lock:
        cfg = load()
        if name == "env" or any(x.get("name") == name for x in cfg["profiles"]):
            raise ValueError(f"profile 已存在：{name}")
        row = {"name": name, "preset": p.get("preset", "custom"),
               "endpoint": p.get("endpoint", "chat_completions"),
               "base_url": p["base_url"], "model": p["model"],
               "temperature": p.get("temperature", 0.3)}
        cfg["profiles"].append(row)
        _save(cfg)
    return dict(row, source="user")


def update(name: str, patch: dict) -> dict:
    """name=="env" / 不存在 → ValueError（路由转 400）。"""
    if name == "env":
        raise ValueError("env profile 只读（来自 COMMENTARY_* 环境变量）")
    with _lock:
        cfg = load()
        for row in cfg["profiles"]:
            if row.get("name") == name:
                # None == 未设（全可选 patch）；拦在落盘口防显式 null 写坏配置
                row.update({k: v for k, v in patch.items() if v is not None})
                _save(cfg)
                return dict(row, source="user")
    raise ValueError(f"profile 不存在：{name}")


def delete(name: str) -> None:
    """连带 keychain.delete_key(name)；删的是 active → active 置 null。"""
    if name == "env":
        raise ValueError("env profile 只读（来自 COMMENTARY_* 环境变量）")
    with _lock:
        cfg = load()
        before = len(cfg["profiles"])
        cfg["profiles"] = [p for p in cfg["profiles"] if p.get("name") != name]
        if len(cfg["profiles"]) == before:
            raise ValueError(f"profile 不存在：{name}")
        if cfg.get("active_profile") == name:
            cfg["active_profile"] = None
        _save(cfg)
    keychain.delete_key(name)   # 失败不阻断（孤儿 keychain 项无害）


def set_active(name: str) -> dict:
    """必须存在（user 或 env），否则 ValueError（路由转 404）。"""
    if get(name) is None:
        raise ValueError(f"profile 不存在：{name}")
    with _lock:
        cfg = load()
        cfg["active_profile"] = name
        _save(cfg)
    return cfg


def set_templates(overrides: dict) -> tuple[dict, str]:
    """整 map 替换 templates{}：空串/纯空白 = 移除该覆盖；未知键/非字符串 → ValueError。

    返回 (规范化后的 overrides, 新 template_hash)；经 _save 钩子自动 mark_stale。
    """
    from backend.app.core import commentary   # 延迟 import：同 _save，循环防护
    known = set(commentary.DEFAULT_TEMPLATES)
    clean = {}
    for k, v in overrides.items():
        if k not in known:
            raise ValueError(f"未知模板键：{k}")
        if not isinstance(v, str):
            raise ValueError(f"模板值须为字符串：{k}")
        if v.strip():
            clean[k] = v
    with _lock:
        cfg = load()
        existing = {k: v for k, v in cfg.get("templates", {}).items()
                    if isinstance(v, str) and v.strip()}
        if existing != clean:                        # 规范化后等同 → 跳过写入，防假 stale
            cfg["templates"] = clean
            _save(cfg)                               # 钩子自动 mark_stale
    return clean, commentary.template_hash()


def key_for(name: str) -> str | None:
    """env → COMMENTARY_API_KEY；否则 keychain.get_key(name)。"""
    if name == "env":
        return os.getenv("COMMENTARY_API_KEY") or None
    return keychain.get_key(name)


def resolve_active() -> dict | None:
    """active_profile 有效 → 之；否则 env_profile()；否则 None。

    M4b 生成链路的唯一取配置入口（commentary._configured() 经此取 profile）。
    """
    cfg = load()
    active = cfg.get("active_profile")
    p = get(active) if active else None
    return p or env_profile()
