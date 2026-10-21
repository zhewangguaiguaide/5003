"""配置读取：config.yaml -> 数据类。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List

from .crawler import ColumnSpec

DEFAULT_CONFIG = "config.yaml"


def load_config(path: str = DEFAULT_CONFIG) -> Dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("缺少 PyYAML，请先 pip install -r requirements.txt") from exc

    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_columns(config: Dict[str, Any]) -> List[ColumnSpec]:
    limits = config.get("limits") or {}
    default_max = int(limits.get("max_pages_per_column", 20))
    columns = []
    for item in config.get("columns") or []:
        columns.append(ColumnSpec(
            name=item["name"],
            topic=item.get("topic", ""),
            seeds=list(item.get("seeds") or []),
            include=list(item.get("include") or []),
            exclude=list(item.get("exclude") or []),
            max_pages=int(item.get("max_pages", default_max)),
            capture_seeds=bool(item.get("capture_seeds", False)),
        ))
    return columns


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
