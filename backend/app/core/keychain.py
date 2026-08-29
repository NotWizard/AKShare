"""macOS keychain wrapper for AI profile API keys (via `security` CLI).

Secrets never touch data/ai_config.json, logs, or exception text. Every
function returns None/False on ANY failure instead of raising — keychain
hiccups must not 500 the config API.

MACRO_AI_KEYCHAIN=off → in-process dict fallback (unit tests, headless/CI).
"""

import os
import re
import subprocess

SERVICE = "macro-ai-profiles"
NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")   # 白名单：与 ai_config 共用，防 CLI 注入
_FALLBACK: dict[str, str] = {}                  # MACRO_AI_KEYCHAIN=off 时的进程内存储


def _off() -> bool:
    return os.getenv("MACRO_AI_KEYCHAIN", "").lower() == "off"


def _valid(name: str) -> bool:
    return bool(re.fullmatch(NAME_RE, name))


def set_key(name: str, key: str) -> bool:
    if not _valid(name) or not key:
        return False
    if _off():
        _FALLBACK[name] = key
        return True
    try:
        # 注：key 经 argv 传递会短暂出现在本机进程列表（man security 亦提示 -w 不安全）。
        # 单用户桌面场景可接受；多用户/服务器场景需换 stdin 方案（不在 M4a 范围）。
        # -T ""：无受信应用 → 仅创建者可访问，其他应用读取需用户逐次授权。
        r = subprocess.run(
            ["security", "add-generic-password", "-U", "-T", "",
             "-s", SERVICE, "-a", name, "-w", key],
            capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def get_key(name: str) -> str | None:
    if not _valid(name):
        return None
    if _off():
        return _FALLBACK.get(name)
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
            capture_output=True, timeout=10)
        if r.returncode != 0:
            return None
        return r.stdout.decode("utf-8", "replace").strip() or None
    except Exception:
        return None


def delete_key(name: str) -> bool:
    # 删除失败不阻断 profile 删除（孤儿 keychain 项无害，重试删除即可）——调用方忽略返回值。
    if not _valid(name):
        return False
    if _off():
        return _FALLBACK.pop(name, None) is not None
    try:
        r = subprocess.run(
            ["security", "delete-generic-password", "-s", SERVICE, "-a", name],
            capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False
