"""Configuration loading."""
from __future__ import annotations

import copy
from importlib import resources
from pathlib import Path
from typing import Any

import yaml


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the packaged default config, optionally overridden by a user YAML file."""
    default_text = resources.files("perinatal_ews").joinpath("default_config.yaml").read_text()
    config = yaml.safe_load(default_text)
    if path:
        with open(path) as fh:
            config = _deep_merge(config, yaml.safe_load(fh) or {})
    return config
