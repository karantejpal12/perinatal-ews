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


def core_indicators(config: dict[str, Any]) -> list[str]:
    """The original four indicators (no `set`, or `set: core`).

    The next-year forecast, county types, unusual-record checks, need-and-access review
    and backtest were built and validated on these four, so they use only these; the
    other indicators (`set: more`) get detection, persistent burden, state patterns and
    the similar-county comparison until they have been validated for the rest.
    """
    return [k for k, v in config["indicators"].items() if v.get("set", "core") == "core"]
