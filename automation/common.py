from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys

try:
    import yaml
except ImportError as exc:  # pragma: no cover - runtime guard
    raise SystemExit(
        "PyYAML is required for automation scripts. Install with: python -m pip install pyyaml"
    ) from exc


@dataclass
class Config:
    data: dict
    path: Path


def load_config(path: str | Path) -> Config:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise SystemExit(f"Config not found: {cfg_path}")
    payload = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return Config(data=payload, path=cfg_path)


def ensure_tool(cmd: str, args: list[str] | None = None) -> None:
    candidates = [args] if args else [["--version"], ["-V"], ["--help"]]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            result = subprocess.run(
                [cmd, *candidate],
                capture_output=True,
                text=True,
            )
        except OSError:
            continue
        if result.returncode == 0:
            return
    raise SystemExit(f"Required tool not found or unusable: {cmd}")


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, capture_output=True)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
