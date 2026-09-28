"""人设注册表：内置预设 + 用户自定义（存 ``sessions/personas.json``）。

为什么要有这个模块：人设以前散在三处硬编码——接口 ``/accounts/personas`` 一份中文描述、
``persistent_chat_demo.py`` 一份英文预设、``tasks.py`` 里还有一段兜底默认值。
结果就是"界面里选的人设根本传不到对话引擎"，更谈不上自定义。

现在三处统一从这里取：

* 接口：列表 / 新增 / 删除（``app/api/routes.py``）
* 任务流水线：``app/workers/tasks.py``
* Telegram 常驻守护进程：``persistent_chat_demo.py``

条目字段：``key / name / desc / tone(界面显示) / style(给模型的风格) / age /
occupation / location / backstory``，其中 ``builtin`` 标出哪些是内置的（不可删）。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.core.session_paths import SESSION_DIR

logger = logging.getLogger(__name__)

CUSTOM_FILE = SESSION_DIR / "personas.json"

# 内置预设：desc/tone 是界面文案，style 等是喂给对话引擎的字段
BUILTIN_PERSONAS: dict[str, dict[str, Any]] = {
    "designer": {
        "name": "Nguyen Van A",
        "desc": "自由设计师，28岁，胡志明市",
        "tone": "随和友好",
        "style": "casual, friendly, slightly naive",
        "age": 28,
        "occupation": "Freelance graphic designer",
        "location": "Ho Chi Minh City",
        "backstory": "在胡志明市做自由设计师3年，经常需要换汇和找外包合作。",
    },
    "trader": {
        "name": "Tran Minh Duc",
        "desc": "加密货币交易员，32岁，河内",
        "tone": "自信专业",
        "style": "confident, knowledgeable, direct",
        "age": 32,
        "occupation": "Crypto trader",
        "location": "Hanoi",
        "backstory": "做了5年加密货币交易，熟悉OTC场外交易和各种换汇渠道。",
    },
    "student": {
        "name": "Le Thi Mai",
        "desc": "大学生，22岁，岘港",
        "tone": "好奇礼貌",
        "style": "curious, polite, eager to learn",
        "age": 22,
        "occupation": "University student",
        "location": "Da Nang",
        "backstory": "大四学生，学国际贸易，想找兼职和实习机会。",
    },
    "business": {
        "name": "Pham Hoang Nam",
        "desc": "进出口贸易老板，35岁，胡志明市",
        "tone": "稳重可信",
        "style": "professional, experienced, trustworthy",
        "age": 35,
        "occupation": "Import-export business owner",
        "location": "Ho Chi Minh City",
        "backstory": "经营进出口贸易公司8年，需要频繁跨境支付和换汇。",
    },
}

DEFAULT_PERSONA: dict[str, Any] = {
    "name": "User",
    "age": 28,
    "occupation": "freelancer",
    "location": "Ho Chi Minh City",
    "backstory": "Freelance designer looking for opportunities",
    "tone": "casual, friendly",
}

_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")


def _normalize(entry: dict[str, Any], key: str, *, builtin: bool) -> dict[str, Any]:
    """补齐字段并标注来源，保证前端拿到的结构一致。"""
    normalized = {
        "key": key,
        "name": str(entry.get("name") or key),
        "desc": str(entry.get("desc") or ""),
        "tone": str(entry.get("tone") or entry.get("style") or ""),
        "style": str(entry.get("style") or entry.get("tone") or ""),
        "age": entry.get("age"),
        "occupation": str(entry.get("occupation") or ""),
        "location": str(entry.get("location") or ""),
        "backstory": str(entry.get("backstory") or ""),
        "builtin": builtin,
    }
    return normalized


def load_custom_personas() -> dict[str, dict[str, Any]]:
    """读自定义人设；文件不存在/坏掉都当作空（不影响内置预设）。"""
    try:
        data = json.loads(Path(CUSTOM_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("自定义人设文件读不出来，已忽略：%s", CUSTOM_FILE, exc_info=True)
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: value
        for key, value in data.items()
        if isinstance(value, dict) and _KEY_RE.match(str(key))
    }


def _write_custom_personas(data: dict[str, dict[str, Any]]) -> None:
    Path(CUSTOM_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(CUSTOM_FILE).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def list_personas() -> list[dict[str, Any]]:
    """内置在前、自定义在后；同 key 时自定义覆盖内置。"""
    merged: dict[str, dict[str, Any]] = {
        key: _normalize(value, key, builtin=True) for key, value in BUILTIN_PERSONAS.items()
    }
    for key, value in load_custom_personas().items():
        # 来自 personas.json 的一律算"自定义"（能删）：删掉只是去掉覆盖，内置还在
        merged[key] = _normalize(value, key, builtin=False)
    return list(merged.values())


def get_persona(key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    return next((p for p in list_personas() if p["key"] == key), None)


def resolve_persona_config(key: str | None) -> dict[str, Any]:
    """给对话引擎的人设字段；找不到时回落到默认人设。"""
    persona = get_persona(key)
    if persona is None:
        return dict(DEFAULT_PERSONA)
    return {
        "name": persona.get("name") or DEFAULT_PERSONA["name"],
        "age": persona.get("age") or DEFAULT_PERSONA["age"],
        "occupation": persona.get("occupation") or DEFAULT_PERSONA["occupation"],
        "location": persona.get("location") or DEFAULT_PERSONA["location"],
        "backstory": persona.get("backstory") or DEFAULT_PERSONA["backstory"],
        "tone": persona.get("style") or persona.get("tone") or DEFAULT_PERSONA["tone"],
    }


def persona_key_for_account(account_name: str) -> str | None:
    """从 ``sessions/<name>_meta.json`` 里读该账号选的人设 key。"""
    if not account_name:
        return None
    meta_file = SESSION_DIR / f"{account_name}_meta.json"
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    key = meta.get("persona") if isinstance(meta, dict) else None
    return str(key) if key else None


def slugify_key(name: str) -> str:
    """把人设名转成 key（中文名会退化成 custom-<n>，由调用方去重）。"""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    slug = slug[:40]
    return slug if slug and _KEY_RE.match(slug) else ""


def upsert_custom_persona(payload: dict[str, Any]) -> dict[str, Any]:
    """新建/更新一个自定义人设，返回归一化后的条目。"""
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("人设名不能为空")

    key = str(payload.get("key") or "").strip()
    custom = load_custom_personas()
    if not key or key in BUILTIN_PERSONAS:
        base = slugify_key(name) or "custom"
        key, index = base, 1
        while key in BUILTIN_PERSONAS or key in custom:
            index += 1
            key = f"{base}-{index}"
    elif not _KEY_RE.match(key):
        raise ValueError("人设 key 只能用 1-48 位小写字母、数字、下划线或短横线")

    entry = {
        "name": name,
        "desc": str(payload.get("desc") or "").strip(),
        "tone": str(payload.get("tone") or "").strip(),
        "style": str(payload.get("style") or payload.get("tone") or "").strip(),
        "age": payload.get("age"),
        "occupation": str(payload.get("occupation") or "").strip(),
        "location": str(payload.get("location") or "").strip(),
        "backstory": str(payload.get("backstory") or "").strip(),
    }
    custom[key] = entry
    _write_custom_personas(custom)
    return _normalize(entry, key, builtin=False)


def delete_custom_persona(key: str) -> bool:
    """只能删自定义的；内置预设删不了。"""
    custom = load_custom_personas()
    if key not in custom:
        return False
    custom.pop(key)
    _write_custom_personas(custom)
    return True
