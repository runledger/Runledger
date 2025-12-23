from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re


@dataclass(frozen=True)
class DetectedEntrypoints:
    python_project_scripts: dict[str, str] = field(default_factory=dict)
    python_poetry_scripts: dict[str, str] = field(default_factory=dict)
    node_bin: dict[str, str] = field(default_factory=dict)
    node_scripts: dict[str, str] = field(default_factory=dict)
    candidate_files: list[str] = field(default_factory=list)
    readme_commands: list[str] = field(default_factory=list)


_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".agentci",
    "runledger_out",
}

_INTERESTING_DIRS = (
    "examples",
    "example",
    "demo",
    "demos",
    "sample",
    "samples",
    "scripts",
    "cli",
    "agent",
    "agents",
    "src",
    "app",
    "apps",
)

_ENTRYPOINT_FILE_RE = re.compile(r"(?i)(agent|assistant|bot|cli|main|app|server|run).*\.(py|ts|js)$")
_TOML_SECTION_RE = re.compile(r"^\[(?P<section>[^\]]+)\]\s*$")
_TOML_KV_RE = re.compile(r'^(?P<key>[A-Za-z0-9_.-]+)\s*=\s*"(?P<val>[^"]*)"\s*$')
_TOML_KV_SQ_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.-]+)\s*=\s*'(?P<val>[^']*)'\s*$")

_SHELL_COMMAND_RE = re.compile(
    r"^(?:\$ )?(python|python3|node|npm|pnpm|yarn|bun|go|make|uv|pip|pipx)\b"
)

_PREFERRED_NODE_SCRIPTS = (
    "start",
    "dev",
    "serve",
    "run",
    "cli",
    "agent",
    "demo",
    "example",
)


def detect_entrypoints(repo_dir: Path, *, max_candidates: int = 20) -> DetectedEntrypoints:
    repo_dir = repo_dir.resolve()
    pyproject = repo_dir / "pyproject.toml"
    package_json = repo_dir / "package.json"

    python_project_scripts: dict[str, str] = {}
    python_poetry_scripts: dict[str, str] = {}
    node_bin: dict[str, str] = {}
    node_scripts: dict[str, str] = {}

    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8", errors="replace")
        python_project_scripts = _parse_simple_toml_kv(text, "project.scripts")
        python_poetry_scripts = _parse_simple_toml_kv(text, "tool.poetry.scripts")

    if package_json.exists():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            package = None
        if isinstance(package, dict):
            node_bin = _parse_package_bin(package)
            node_scripts = _parse_package_scripts(package, limit=12)

    candidate_files = _find_candidate_files(repo_dir, limit=max_candidates)
    readme_commands = _extract_readme_commands(repo_dir, limit=12)

    return DetectedEntrypoints(
        python_project_scripts=python_project_scripts,
        python_poetry_scripts=python_poetry_scripts,
        node_bin=node_bin,
        node_scripts=node_scripts,
        candidate_files=candidate_files,
        readme_commands=readme_commands,
    )


def render_entrypoints_markdown(hints: DetectedEntrypoints) -> str:
    sections: list[str] = []

    node_bits: list[str] = []
    if hints.node_scripts:
        node_bits.append("### Node scripts (from `package.json`)\n")
        node_bits.extend([f"- `npm run {k}`" for k in sorted(hints.node_scripts.keys())])
    if hints.node_bin:
        node_bits.append("\n### Node CLI bins (from `package.json`)\n")
        for name, path in sorted(hints.node_bin.items()):
            node_bits.append(f"- `{name}` -> `{path}`")
    if node_bits:
        sections.append("\n".join(node_bits).rstrip())

    python_bits: list[str] = []
    if hints.python_project_scripts:
        python_bits.append("### Python project scripts (from `pyproject.toml`)\n")
        for name, target in sorted(hints.python_project_scripts.items()):
            python_bits.append(f"- `{name}` = `{target}`")
    if hints.python_poetry_scripts:
        python_bits.append("\n### Python Poetry scripts (from `pyproject.toml`)\n")
        for name, target in sorted(hints.python_poetry_scripts.items()):
            python_bits.append(f"- `{name}` = `{target}`")
    if python_bits:
        sections.append("\n".join(python_bits).rstrip())

    if hints.readme_commands:
        bits = ["### Commands found in README\n"]
        bits.extend([f"- `{cmd}`" for cmd in hints.readme_commands])
        sections.append("\n".join(bits).rstrip())

    if hints.candidate_files:
        bits = ["### Entry-point-like files found\n"]
        bits.extend([f"- `{path}`" for path in hints.candidate_files])
        sections.append("\n".join(bits).rstrip())

    if not sections:
        return "- No obvious entrypoints found (please point RunLedger at your preferred agent/example command).\n"

    return "\n\n".join(sections).rstrip() + "\n"


def _parse_simple_toml_kv(text: str, target_section: str) -> dict[str, str]:
    current_section: str | None = None
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        section_match = _TOML_SECTION_RE.match(line)
        if section_match:
            current_section = section_match.group("section").strip()
            continue
        if current_section != target_section:
            continue
        kv_match = _TOML_KV_RE.match(line) or _TOML_KV_SQ_RE.match(line)
        if kv_match:
            result[kv_match.group("key")] = kv_match.group("val")
    return result


def _parse_package_bin(package: dict) -> dict[str, str]:
    bin_value = package.get("bin")
    if isinstance(bin_value, str):
        return {package.get("name", "<bin>"): bin_value}
    if isinstance(bin_value, dict):
        out: dict[str, str] = {}
        for key, value in bin_value.items():
            if isinstance(key, str) and isinstance(value, str):
                out[key] = value
        return out
    return {}


def _parse_package_scripts(package: dict, *, limit: int) -> dict[str, str]:
    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        return {}

    picked: dict[str, str] = {}
    for key in _PREFERRED_NODE_SCRIPTS:
        value = scripts.get(key)
        if isinstance(value, str):
            picked[key] = value
    if picked:
        return picked

    for key in sorted(scripts.keys()):
        if len(picked) >= limit:
            break
        value = scripts.get(key)
        if isinstance(key, str) and isinstance(value, str):
            picked[key] = value
    return picked


def _find_candidate_files(repo_dir: Path, *, limit: int) -> list[str]:
    candidates: list[str] = []

    # First: top-level obvious entrypoints.
    for path in sorted(repo_dir.glob("*")):
        if path.is_file() and _ENTRYPOINT_FILE_RE.match(path.name):
            candidates.append(path.name)
            if len(candidates) >= limit:
                return candidates

    # Then: shallow scan in common example/cli directories only.
    for dirname in _INTERESTING_DIRS:
        root = repo_dir / dirname
        if not root.exists() or not root.is_dir():
            continue
        for rel_path in _walk_entrypoint_like_files(root, max_depth=4, limit=limit - len(candidates)):
            candidates.append(f"{dirname}/{rel_path}")
            if len(candidates) >= limit:
                return candidates
    return candidates


def _walk_entrypoint_like_files(root: Path, *, max_depth: int, limit: int) -> list[str]:
    found: list[str] = []
    root = root.resolve()
    for dirpath, dirs, files in os.walk(root):
        rel_dir = Path(dirpath).resolve().relative_to(root)
        depth = len(rel_dir.parts)
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        if depth >= max_depth:
            dirs[:] = []
        for filename in sorted(files):
            if len(found) >= limit:
                return found
            if not _ENTRYPOINT_FILE_RE.match(filename):
                continue
            file_rel = (rel_dir / filename).as_posix()
            found.append(file_rel)
    return found


def _extract_readme_commands(repo_dir: Path, *, limit: int) -> list[str]:
    readme = _find_readme(repo_dir)
    if readme is None:
        return []
    text = readme.read_text(encoding="utf-8", errors="replace")
    commands: list[str] = []

    in_fence = False
    fence_lang = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            if not in_fence:
                in_fence = True
                fence_lang = line.strip().lstrip("`").strip()
            else:
                in_fence = False
                fence_lang = ""
            continue
        if not in_fence:
            continue
        if fence_lang and fence_lang not in {"bash", "sh", "shell", "console", "text"}:
            continue
        snippet = line.strip()
        if not snippet or snippet.startswith("#"):
            continue
        if not _SHELL_COMMAND_RE.match(snippet):
            continue
        commands.append(snippet.lstrip("$ ").strip())
        if len(commands) >= limit:
            break

    return commands


def _find_readme(repo_dir: Path) -> Path | None:
    for name in ("README.md", "README.rst", "README.txt"):
        path = repo_dir / name
        if path.exists():
            return path
    for path in sorted(repo_dir.glob("README.*")):
        if path.is_file():
            return path
    return None

