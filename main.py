from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from fastmcp import FastMCP


APP_ROOT = Path(__file__).resolve().parent
PROMPT_DIR = APP_ROOT / ".agent_prompts"
PROMPT_GITIGNORE = "*\n"
README_CANDIDATES = ("README.md", "README.rst", "README.txt")
KEY_CONTEXT_FILES = (
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.toml",
    "go.mod",
    "go.sum",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "composer.json",
    "Gemfile",
    "mix.exs",
    "Podfile",
    "CMakeLists.txt",
    "meson.build",
    "build.zig",
    "WORKSPACE",
    "WORKSPACE.bazel",
    "MODULE.bazel",
    "BUILD",
    "BUILD.bazel",
    "requirements.txt",
    "requirements-dev.txt",
    "setup.py",
    "setup.cfg",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".python-version",
    ".node-version",
    ".nvmrc",
    ".ruby-version",
    ".tool-versions",
)
SOURCE_FILE_SUFFIXES = (
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".rs",
    ".go",
    ".java",
    ".kt",
    ".rb",
    ".php",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".swift",
    ".scala",
    ".sh",
    ".zig",
    ".ex",
    ".exs",
    ".clj",
    ".dart",
)
ENTRYPOINT_FILE_NAMES = (
    "main.py",
    "app.py",
    "server.py",
    "main.rs",
    "lib.rs",
    "main.go",
    "server.go",
    "main.java",
    "main.kt",
    "main.cs",
    "program.cs",
    "main.swift",
    "index.ts",
    "index.tsx",
    "index.js",
    "index.jsx",
    "main.ts",
    "main.tsx",
    "main.js",
    "main.jsx",
    "manage.py",
    "application.rb",
    "config.ru",
    "mix.exs",
)
HIGH_SIGNAL_DIR_NAMES = (
    "src",
    "app",
    "apps",
    "backend",
    "frontend",
    "server",
    "api",
    "core",
    "lib",
    "pkg",
    "cmd",
    "internal",
    "services",
    "modules",
    "crates",
    "packages",
    "client",
    "web",
    "ui",
    "domain",
    "engine",
)
MAX_FILE_BYTES = 12_000
MAX_REPRESENTATIVE_FILES = 8
MAX_SYMBOLS_PER_FILE = 20
MAX_DETAILED_SOURCE_FILES = 3
IMPLEMENTATION_HEADER = "## IMPLEMENTATION PROMPT"
DEFAULT_ORCHESTRATOR_MODEL = os.getenv("BRIDGE_BUILDER_ORCHESTRATOR_MODEL", "gpt-5.4")
DEFAULT_IMPLEMENTOR_MODEL = os.getenv(
    "BRIDGE_BUILDER_IMPLEMENTOR_MODEL", "gpt-5.4"
)
DEFAULT_ORCHESTRATOR_REASONING = os.getenv(
    "BRIDGE_BUILDER_ORCHESTRATOR_REASONING", "high"
)
DEFAULT_IMPLEMENTOR_REASONING = os.getenv(
    "BRIDGE_BUILDER_IMPLEMENTOR_REASONING", "medium"
)
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("BRIDGE_BUILDER_CODEX_TIMEOUT_SECONDS", "1800"))
POST_VERIFY_ENABLED = os.getenv("BRIDGE_BUILDER_ENABLE_POST_VERIFY", "1") != "0"
POST_VERIFY_TIMEOUT_SECONDS = int(
    os.getenv("BRIDGE_BUILDER_POST_VERIFY_TIMEOUT_SECONDS", "300")
)
ALLOW_PACKAGE_SCRIPT_VERIFY = (
    os.getenv("BRIDGE_BUILDER_ALLOW_PACKAGE_SCRIPT_VERIFY", "0") == "1"
)
IMPLEMENTATION_PROMPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["implementation_prompt"],
    "properties": {
        "implementation_prompt": {
            "type": "string",
            "description": "A complete implementation prompt for a zero-context coding agent.",
        }
    },
}
IMPLEMENTATION_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "summary",
        "touched_files",
        "verification_performed",
        "remaining_risks",
    ],
    "properties": {
        "summary": {"type": "string"},
        "touched_files": {
            "type": "array",
            "items": {"type": "string"},
        },
        "verification_performed": {
            "type": "array",
            "items": {"type": "string"},
        },
        "remaining_risks": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}

ORCHESTRATOR_SYSTEM_PROMPT = f"""You are an orchestration agent preparing work for a separate implementation agent.

Your job is to analyze the user's request using the repository context provided, identify ambiguity, and produce a self-contained implementation prompt for another Codex run with zero prior context.

Requirements:
- Think from the repository context only. Do not assume access to prior conversation.
- Treat this as a general-purpose software repository. Infer the stack, build system, and language conventions from the provided files instead of assuming Python, JavaScript, or any single ecosystem.
- Start the implementation prompt with a line in exactly this format: "Repository root: <absolute-path>".
- If the request is ambiguous, include a short "Clarifying Questions" subsection inside the implementation prompt, followed by a concrete "Assumptions If Unanswered" subsection so execution can still proceed.
- The implementation prompt must be technically precise and self-contained.
- Include relevant file paths, modules/packages/crates/namespaces as appropriate for the detected stack, concrete symbols to change where possible, interfaces, constraints, and expected behavior.
- Include a concrete implementation plan, verification steps, and acceptance criteria.
- Optimize for a strong coding agent that will edit files directly and verify its work.
- Do not refer to "the user said", "earlier context", "above", or "this conversation".
- Return valid JSON only, with one key: "implementation_prompt".
- The value of "implementation_prompt" must include a section exactly named "{IMPLEMENTATION_HEADER}" and only the implementation prompt content after that header.
"""

IMPLEMENTOR_INSTRUCTIONS = """You are the implementation agent.

Operate with zero prior context beyond the prompt you receive.

Execution rules:
- Treat the provided prompt as the full source of truth.
- If the prompt contains "Clarifying Questions", continue using "Assumptions If Unanswered" unless the prompt explicitly blocks implementation.
- Prefer direct code changes over broad discussion.
- Verify the implementation where practical.
- Return valid JSON only with exactly these keys:
  - summary: concise summary of the implementation outcome
  - touched_files: repository-relative file paths changed or intentionally inspected for edits
  - verification_performed: commands run, checks performed, or concise verification notes
  - remaining_risks: concise residual risks or follow-up gaps
"""


mcp = FastMCP("bridge-builder")


def _repo_readme(repo_path: Path) -> str:
    for candidate in README_CANDIDATES:
        path = repo_path / candidate
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _repo_tree(repo_path: Path, max_depth: int = 3) -> str:
    lines: list[str] = [f"{repo_path.name}/"]

    def walk(current: Path, prefix: str, depth: int) -> None:
        if depth >= max_depth:
            return

        entries = sorted(
            (
                entry
                for entry in current.iterdir()
                if entry.name not in {".git", ".venv", "__pycache__"}
            ),
            key=lambda item: (not item.is_dir(), item.name.lower()),
        )

        for entry in entries:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{prefix}{entry.name}{suffix}")
            if entry.is_dir():
                walk(entry, f"{prefix}  ", depth + 1)

    walk(repo_path, "  ", 0)
    return "\n".join(lines)


def _read_text_file(path: Path, max_bytes: int = MAX_FILE_BYTES) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="utf-8", errors="replace")
    if len(content.encode("utf-8")) <= max_bytes:
        return content
    encoded = content.encode("utf-8")[:max_bytes]
    return encoded.decode("utf-8", errors="ignore") + "\n...[truncated]"


def _safe_json_loads(text: str) -> dict[str, Any] | list[Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _safe_toml_loads(text: str) -> dict[str, Any] | None:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None


def _safe_xml_root(text: str) -> ET.Element | None:
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        return None


def _extract_key_value_lines(text: str, keys: tuple[str, ...]) -> list[str]:
    matched: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(f"{key} ") or stripped.startswith(f"{key}=") for key in keys):
            matched.append(stripped)
    return matched


def _xml_find_text(root: ET.Element, tag_name: str) -> str | None:
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1] == tag_name and elem.text:
            return elem.text.strip()
    return None


def _yaml_top_level_keys(text: str, limit: int = 8) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not line or line.startswith(" ") or line.startswith("\t"):
            continue
        if line.lstrip().startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*:", line)
        if not match:
            continue
        key = match.group(1)
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)
        if len(keys) >= limit:
            break
    return keys


def _extract_manifest_file_hints(repo_path: Path) -> set[Path]:
    hints: set[Path] = set()

    def add_if_file(candidate: Path) -> None:
        resolved = candidate.resolve()
        if resolved.exists() and resolved.is_file() and (
            resolved == repo_path or repo_path in resolved.parents
        ):
            hints.add(resolved)

    package_json = repo_path / "package.json"
    if package_json.is_file():
        data = _safe_json_loads(_read_text_file(package_json))
        if isinstance(data, dict):
            scripts = data.get("scripts") or {}
            if isinstance(scripts, dict):
                for command in scripts.values():
                    if not isinstance(command, str):
                        continue
                    for match in re.findall(
                        r"(?<![A-Za-z0-9_./-])([A-Za-z0-9_./-]+\.(?:js|jsx|ts|tsx|mjs|cjs))",
                        command,
                    ):
                        add_if_file(repo_path / match)

    pyproject = repo_path / "pyproject.toml"
    if pyproject.is_file():
        data = _safe_toml_loads(_read_text_file(pyproject))
        if isinstance(data, dict):
            project = data.get("project") or {}
            scripts = project.get("scripts") or {}
            for target in scripts.values() if isinstance(scripts, dict) else []:
                if not isinstance(target, str) or ":" not in target:
                    continue
                module = target.split(":", 1)[0].replace(".", "/")
                add_if_file(repo_path / f"{module}.py")
                add_if_file(repo_path / module / "__init__.py")

    cargo_toml = repo_path / "Cargo.toml"
    if cargo_toml.is_file():
        data = _safe_toml_loads(_read_text_file(cargo_toml))
        if isinstance(data, dict):
            bins = data.get("bin") or []
            if isinstance(bins, list):
                for item in bins:
                    if isinstance(item, dict) and isinstance(item.get("path"), str):
                        add_if_file(repo_path / item["path"])
            lib = data.get("lib") or {}
            if isinstance(lib, dict) and isinstance(lib.get("path"), str):
                add_if_file(repo_path / lib["path"])
            else:
                add_if_file(repo_path / "src/lib.rs")
            add_if_file(repo_path / "src/main.rs")

    go_mod = repo_path / "go.mod"
    if go_mod.is_file():
        add_if_file(repo_path / "main.go")
        cmd_dir = repo_path / "cmd"
        if cmd_dir.is_dir():
            for path in cmd_dir.rglob("*.go"):
                add_if_file(path)

    pom_xml = repo_path / "pom.xml"
    if pom_xml.is_file():
        for source_root in (repo_path / "src/main/java", repo_path / "src/main/kotlin"):
            if source_root.is_dir():
                for path in source_root.rglob("*"):
                    if path.is_file() and path.suffix.lower() in SOURCE_FILE_SUFFIXES:
                        add_if_file(path)

    return hints


def _summarize_manifest(path: Path, repo_path: Path) -> str:
    rel = path.relative_to(repo_path)
    raw = _read_text_file(path)
    name = path.name

    if name == "package.json":
        data = _safe_json_loads(raw)
        if isinstance(data, dict):
            scripts = sorted((data.get("scripts") or {}).keys())
            deps = sorted((data.get("dependencies") or {}).keys())
            dev_deps = sorted((data.get("devDependencies") or {}).keys())
            parts = [
                f"{rel}: package={data.get('name', '[unknown]')}",
                f"scripts={', '.join(scripts[:8]) or '[none]'}",
                f"deps={', '.join(deps[:8]) or '[none]'}",
                f"devDeps={', '.join(dev_deps[:8]) or '[none]'}",
            ]
            return "; ".join(parts)

    if name in {"tsconfig.json", "deno.json", "deno.jsonc"}:
        data = _safe_json_loads(raw)
        if isinstance(data, dict):
            compiler_options = sorted((data.get("compilerOptions") or {}).keys())
            return (
                f"{rel}: compilerOptions={', '.join(compiler_options[:8]) or '[none]'}; "
                f"include={data.get('include', '[none]')}; exclude={data.get('exclude', '[none]')}"
            )

    if name == "pyproject.toml":
        data = _safe_toml_loads(raw)
        if isinstance(data, dict):
            project = data.get("project") or {}
            scripts = data.get("project", {}).get("scripts") or {}
            return (
                f"{rel}: name={project.get('name', '[unknown]')}; "
                f"version={project.get('version', '[unknown]')}; "
                f"requires-python={project.get('requires-python', '[unknown]')}; "
                f"dependencies={len(project.get('dependencies') or [])}; "
                f"scripts={', '.join(sorted(scripts.keys())[:8]) or '[none]'}"
            )
        lines = _extract_key_value_lines(
            raw, ("name", "version", "requires-python", "dependencies", "build-backend")
        )
        return f"{rel}: " + ("; ".join(lines[:8]) if lines else "Python project metadata detected")

    if name == "Cargo.toml":
        data = _safe_toml_loads(raw)
        if isinstance(data, dict):
            package = data.get("package") or {}
            deps = data.get("dependencies") or {}
            workspace = data.get("workspace") or {}
            bins = data.get("bin") or []
            return (
                f"{rel}: package={package.get('name', '[unknown]')}; "
                f"edition={package.get('edition', '[unknown]')}; "
                f"targets={len(bins) or ('lib' if 'lib' in data else '[default]')}; "
                f"dependencies={len(deps)}; "
                f"workspace-members={len(workspace.get('members') or [])}"
            )

    if name == "pom.xml":
        root = _safe_xml_root(raw)
        if root is not None:
            artifact_id = _xml_find_text(root, "artifactId")
            group_id = _xml_find_text(root, "groupId")
            version = _xml_find_text(root, "version")
            packaging = _xml_find_text(root, "packaging")
            modules = [
                elem.text.strip()
                for elem in root.iter()
                if elem.tag.rsplit("}", 1)[-1] == "module" and elem.text
            ]
            return (
                f"{rel}: groupId={group_id or '[unknown]'}; "
                f"artifactId={artifact_id or '[unknown]'}; "
                f"version={version or '[unknown]'}; "
                f"packaging={packaging or '[default]'}; "
                f"modules={', '.join(modules[:8]) or '[none]'}"
            )

    if name == "go.mod":
        module_name = None
        go_version = None
        requires = 0
        in_require_block = False
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("module "):
                module_name = stripped.split(" ", 1)[1]
            elif stripped.startswith("go "):
                go_version = stripped.split(" ", 1)[1]
            elif stripped == "require (":
                in_require_block = True
            elif in_require_block and stripped == ")":
                in_require_block = False
            elif stripped.startswith("require "):
                requires += 1
            elif in_require_block and stripped and not stripped.startswith("//"):
                requires += 1
        return (
            f"{rel}: module={module_name or '[unknown]'}; "
            f"go={go_version or '[unknown]'}; dependencies={requires}"
        )

    if name == "composer.json":
        data = _safe_json_loads(raw)
        if isinstance(data, dict):
            require = data.get("require") or {}
            require_dev = data.get("require-dev") or {}
            return (
                f"{rel}: package={data.get('name', '[unknown]')}; "
                f"php={require.get('php', '[unspecified]')}; "
                f"require={', '.join(sorted(require.keys())[:8]) or '[none]'}; "
                f"require-dev={', '.join(sorted(require_dev.keys())[:8]) or '[none]'}"
            )

    if name in {"docker-compose.yml", "docker-compose.yaml"}:
        services: list[str] = []
        in_services = False
        for line in raw.splitlines():
            if re.match(r"^services\s*:\s*$", line):
                in_services = True
                continue
            if in_services:
                if re.match(r"^[A-Za-z0-9_.-]+\s*:\s*$", line):
                    break
                match = re.match(r"^\s{2}([A-Za-z0-9_.-]+)\s*:\s*$", line)
                if match:
                    services.append(match.group(1))
        top_level = _yaml_top_level_keys(raw)
        return (
            f"{rel}: top-level={', '.join(top_level) or '[none]'}; "
            f"services={', '.join(services[:8]) or '[none]'}"
        )

    if name in {"Cargo.toml", "go.mod", "pom.xml", "composer.json", "Gemfile", "mix.exs"}:
        preview = "\n".join(raw.splitlines()[:20]).strip()
        return f"{rel}:\n{preview or '[empty]'}"

    if name in {
        "Makefile",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "CMakeLists.txt",
        "meson.build",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "WORKSPACE",
        "WORKSPACE.bazel",
        "MODULE.bazel",
        "BUILD",
        "BUILD.bazel",
    }:
        preview = "\n".join(raw.splitlines()[:25]).strip()
        return f"{rel}:\n{preview or '[empty]'}"

    return f"{rel}: manifest/config file present"


def _extract_symbols(path: Path) -> list[str]:
    content = _read_text_file(path)
    suffix = path.suffix.lower()
    patterns: list[re.Pattern[str]] = []

    if suffix == ".py":
        patterns = [
            re.compile(r"(?m)^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
            re.compile(r"(?m)^\s*async\s+def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
        ]
    elif suffix in {".js", ".jsx", ".ts", ".tsx"}:
        patterns = [
            re.compile(r"(?m)^\s*export\s+(?:default\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*export\s+(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
            re.compile(r"(?m)^\s*(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
            re.compile(r"(?m)^\s*export\s+const\s+([A-Za-z_][A-Za-z0-9_]*)\s*="),
            re.compile(r"(?m)^\s*const\s+([A-Za-z_][A-Za-z0-9_]*)\s*="),
            re.compile(r"(?m)^\s*interface\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s*="),
        ]
    elif suffix == ".rs":
        patterns = [
            re.compile(r"(?m)^\s*pub\s+struct\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*struct\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*pub\s+enum\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*enum\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*pub\s+trait\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*trait\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*pub\s+fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
            re.compile(r"(?m)^\s*fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
        ]
    elif suffix == ".go":
        patterns = [
            re.compile(r"(?m)^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s+struct\b"),
            re.compile(r"(?m)^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s+interface\b"),
            re.compile(r"(?m)^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\("),
        ]
    elif suffix in {".java", ".kt", ".scala"}:
        patterns = [
            re.compile(r"(?m)^\s*(?:public\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*(?:public\s+)?interface\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*(?:public\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*(?:public\s+)?(?:static\s+)?(?:suspend\s+)?fun\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
            re.compile(r"(?m)^\s*(?:public|private|protected)?\s*(?:static\s+)?[\w<>\[\]?]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
            re.compile(r"(?m)^\s*object\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ]
    elif suffix == ".cs":
        patterns = [
            re.compile(r"(?m)^\s*(?:public|internal|private|protected)?\s*(?:sealed\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*(?:public|internal|private|protected)?\s*interface\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*(?:public|internal|private|protected)?\s*enum\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*(?:public|private|protected|internal)?\s*(?:static\s+)?(?:async\s+)?[\w<>\[\],?]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
        ]
    elif suffix in {".rb", ".php", ".swift", ".ex", ".exs", ".clj", ".dart", ".zig"}:
        patterns = [
            re.compile(r"(?m)^\s*(?:class|module|struct|enum|protocol|trait)\s+([A-Za-z_][A-Za-z0-9_:]*)"),
            re.compile(r"(?m)^\s*(?:def|func|fn)\s+([A-Za-z_][A-Za-z0-9_!?]*)\s*(?:\(|$)"),
        ]
    elif suffix in {".c", ".cc", ".cpp", ".h", ".hpp"}:
        patterns = [
            re.compile(r"(?m)^\s*(?:class|struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)"),
            re.compile(r"(?m)^\s*[\w\*\s]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{"),
        ]
    elif suffix == ".sh":
        patterns = [
            re.compile(r"(?m)^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{"),
            re.compile(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{"),
        ]

    symbols: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in pattern.findall(content):
            symbol = match if isinstance(match, str) else match[0]
            if symbol in seen:
                continue
            seen.add(symbol)
            symbols.append(symbol)
            if len(symbols) >= MAX_SYMBOLS_PER_FILE:
                return symbols
    return symbols


def _collect_key_files(repo_path: Path) -> list[Path]:
    files: list[Path] = []
    for name in KEY_CONTEXT_FILES:
        path = repo_path / name
        if path.is_file():
            files.append(path)
    return files


def _collect_representative_source_files(repo_path: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in sorted(repo_path.rglob("*"), key=lambda item: str(item).lower()):
        if not path.is_file():
            continue
        if any(part in {".git", ".venv", "__pycache__", "node_modules"} for part in path.parts):
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in SOURCE_FILE_SUFFIXES:
            continue
        candidates.append(path)

    changed_files = {path.resolve() for path in _git_changed_files(repo_path)}
    manifest_hints = _extract_manifest_file_hints(repo_path)

    def score(path: Path) -> tuple[int, int, int, int, str]:
        rel = path.relative_to(repo_path)
        parts = rel.parts
        depth = len(parts)
        stem_lower = path.stem.lower()
        name_lower = path.name.lower()
        parent_names = {part.lower() for part in parts[:-1]}

        entrypoint_score = 1 if name_lower in ENTRYPOINT_FILE_NAMES else 0
        root_score = 1 if depth == 1 else 0
        high_signal_dir_score = 1 if parent_names.intersection(HIGH_SIGNAL_DIR_NAMES) else 0
        name_signal_score = 1 if stem_lower in {
            "main",
            "app",
            "server",
            "api",
            "core",
            "index",
            "lib",
            "program",
            "application",
        } else 0
        changed_score = 1 if path.resolve() in changed_files else 0
        manifest_hint_score = 1 if path.resolve() in manifest_hints else 0

        return (
            changed_score,
            manifest_hint_score,
            entrypoint_score + name_signal_score,
            high_signal_dir_score,
            root_score,
            str(rel).lower(),
        )

    scored_candidates = [(score(path), path) for path in candidates]
    ranked = sorted(
        scored_candidates,
        key=lambda item: (
            -item[0][0],
            -item[0][1],
            -item[0][2],
            -item[0][3],
            -item[0][4],
            item[0][5],
        ),
    )
    return [path for _, path in ranked[:MAX_REPRESENTATIVE_FILES]]


def _format_file_section(repo_path: Path, paths: list[Path], title: str) -> str:
    if not paths:
        return f"{title}:\n[None found]"

    sections: list[str] = [f"{title}:"]
    for path in paths:
        rel = path.relative_to(repo_path)
        sections.append(f"--- {rel} ---")
        sections.append(_read_text_file(path))
    return "\n".join(sections)


def _format_symbol_section(repo_path: Path, paths: list[Path], title: str) -> str:
    if not paths:
        return f"{title}:\n[None found]"

    sections: list[str] = [f"{title}:"]
    for path in paths:
        rel = path.relative_to(repo_path)
        symbols = _extract_symbols(path)
        rendered = ", ".join(symbols) if symbols else "[No symbols detected]"
        sections.append(f"{rel}: {rendered}")
    return "\n".join(sections)


def _format_manifest_summary_section(repo_path: Path, paths: list[Path], title: str) -> str:
    if not paths:
        return f"{title}:\n[None found]"

    sections: list[str] = [f"{title}:"]
    for path in paths:
        sections.append(_summarize_manifest(path, repo_path))
    return "\n".join(sections)


def _select_detailed_source_files(paths: list[Path]) -> list[Path]:
    detailed: list[Path] = []
    for path in paths:
        symbols = _extract_symbols(path)
        include = False
        if not symbols:
            include = True
        elif path.name.lower() in ENTRYPOINT_FILE_NAMES:
            include = True
        elif len(symbols) <= 3:
            include = True

        if include:
            detailed.append(path)
        if len(detailed) >= MAX_DETAILED_SOURCE_FILES:
            break

    if detailed:
        return detailed
    return paths[:MAX_DETAILED_SOURCE_FILES]


def _git_status(repo_path: Path) -> str:
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        return "[Not a git repository]"
    try:
        return _run_codex_command(
            ["git", "status", "--short", "--branch"],
            cwd=repo_path,
        )
    except Exception:
        return "[Git status unavailable]"


def _git_changed_files(repo_path: Path) -> list[Path]:
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        return []
    try:
        output = _run_codex_command(["git", "status", "--short"], cwd=repo_path)
    except Exception:
        return []

    changed: list[Path] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        candidate = line[3:]
        if " -> " in candidate:
            candidate = candidate.split(" -> ", 1)[1]
        path = (repo_path / candidate).resolve()
        if path.exists() and path.is_file():
            changed.append(path)
    return changed


def _build_repo_context(repo_path: Path, request: str) -> str:
    readme = _repo_readme(repo_path)
    key_files = _collect_key_files(repo_path)
    representative_files = _collect_representative_source_files(repo_path)
    detailed_source_files = _select_detailed_source_files(representative_files)
    sections = [
        f"Repository path:\n{repo_path}",
        f"Repository tree (max depth 3):\n{_repo_tree(repo_path)}",
        f"Git status:\n{_git_status(repo_path)}",
        f"README contents:\n{readme or '[No README found]'}",
        _format_manifest_summary_section(repo_path, key_files, "Manifest and build summaries"),
        _format_file_section(repo_path, key_files, "Key project files"),
        _format_symbol_section(
            repo_path,
            representative_files,
            f"Representative file symbols (up to {MAX_REPRESENTATIVE_FILES} files)",
        ),
        _format_file_section(
            repo_path,
            detailed_source_files,
            f"Detailed source files (up to {MAX_DETAILED_SOURCE_FILES})",
        ),
        f"Request to analyze:\n{request}",
    ]
    return "\n\n".join(sections)


def _run_codex_command(
    args: list[str],
    *,
    prompt: str | None = None,
    cwd: Path | None = None,
) -> str:
    result = subprocess.run(
        args,
        input=prompt,
        text=True,
        capture_output=True,
        cwd=str(cwd) if cwd else None,
        check=False,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "Unknown Codex subprocess error"
        raise RuntimeError(stderr)
    return result.stdout.strip()


def _run_local_command(args: list[str], cwd: Path) -> tuple[int, str, str]:
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        cwd=str(cwd),
        check=False,
        timeout=POST_VERIFY_TIMEOUT_SECONDS,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _snapshot_repo_files(repo_root: Path) -> dict[Path, tuple[int, int]]:
    snapshot: dict[Path, tuple[int, int]] = {}
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", ".venv", "__pycache__", "node_modules"} for part in path.parts):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot[path.resolve()] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _detect_snapshot_changes(
    before: dict[Path, tuple[int, int]],
    after: dict[Path, tuple[int, int]],
) -> list[Path]:
    changed: list[Path] = []
    for path, metadata in after.items():
        if before.get(path) != metadata:
            changed.append(path)
    return sorted(changed)


def _extract_implementation_prompt(text: str) -> str:
    pattern = rf"(?ims)^\s*{re.escape(IMPLEMENTATION_HEADER)}\s*$\n?(.*)$"
    match = re.search(pattern, text)
    if not match:
        raise ValueError(
            f'Codex output did not include the required "{IMPLEMENTATION_HEADER}" section.'
        )
    return match.group(1).strip()


def _prompt_audit_path() -> Path:
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    gitignore_path = PROMPT_DIR / ".gitignore"
    if not gitignore_path.exists() or gitignore_path.read_text(encoding="utf-8") != PROMPT_GITIGNORE:
        gitignore_path.write_text(PROMPT_GITIGNORE, encoding="utf-8")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return PROMPT_DIR / f"{timestamp}.md"


def _save_prompt(prompt: str) -> Path:
    path = _prompt_audit_path()
    path.write_text(prompt, encoding="utf-8")
    return path


def _extract_repo_root(prompt: str) -> Path | None:
    match = re.search(r"(?im)^Repository root:\s*(.+?)\s*$", prompt)
    if not match:
        return None
    return Path(match.group(1)).expanduser().resolve()


def _render_implementation_result(payload: dict[str, Any]) -> str:
    sections: list[str] = [payload["summary"].strip()]
    touched_files = payload.get("touched_files") or []
    verification = payload.get("verification_performed") or []
    risks = payload.get("remaining_risks") or []

    if touched_files:
        sections.append("Touched files: " + ", ".join(touched_files))
    if verification:
        sections.append("Verification: " + "; ".join(verification))
    if risks:
        sections.append("Remaining risks: " + "; ".join(risks))
    return "\n".join(sections)


def _normalize_touched_files(repo_root: Path | None, touched_files: list[str]) -> list[Path]:
    if repo_root is None:
        return []
    normalized: list[Path] = []
    seen: set[Path] = set()
    for item in touched_files:
        path = (repo_root / item).resolve()
        if not path.exists() or not path.is_file():
            continue
        if repo_root not in path.parents and path != repo_root:
            continue
        if path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return normalized


def _merge_touched_files(
    repo_root: Path | None,
    reported_files: list[str],
    detected_files: list[Path],
) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    for rel_path in reported_files:
        if rel_path not in seen:
            seen.add(rel_path)
            merged.append(rel_path)

    if repo_root is None:
        return merged

    for path in detected_files:
        try:
            rel_path = str(path.relative_to(repo_root))
        except ValueError:
            continue
        if rel_path in seen:
            continue
        seen.add(rel_path)
        merged.append(rel_path)

    return merged


def _package_json_data(repo_root: Path) -> dict[str, Any] | None:
    path = repo_root / "package.json"
    if not path.is_file():
        return None
    data = _safe_json_loads(_read_text_file(path))
    return data if isinstance(data, dict) else None


def _safe_post_verify_commands(repo_root: Path, touched_files: list[Path]) -> list[list[str]]:
    commands: list[list[str]] = []

    if any(path.suffix.lower() == ".py" for path in touched_files):
        commands.append(["python3", "-m", "py_compile", *[str(path) for path in touched_files if path.suffix.lower() == ".py"]])

    if (repo_root / "Cargo.toml").is_file() and shutil.which("cargo"):
        commands.append(["cargo", "check"])

    if (repo_root / "go.mod").is_file() and shutil.which("go"):
        commands.append(["go", "test", "./..."])

    if ALLOW_PACKAGE_SCRIPT_VERIFY:
        package_data = _package_json_data(repo_root)
        scripts = package_data.get("scripts") if isinstance(package_data, dict) else {}
        if isinstance(scripts, dict) and "typecheck" in scripts and shutil.which("npm"):
            commands.append(["npm", "run", "typecheck"])

    return commands


def _post_verify(repo_root: Path | None, touched_files: list[str]) -> list[dict[str, Any]]:
    if not POST_VERIFY_ENABLED or repo_root is None:
        return []

    normalized_files = _normalize_touched_files(repo_root, touched_files)
    commands = _safe_post_verify_commands(repo_root, normalized_files)
    results: list[dict[str, Any]] = []
    for command in commands:
        exit_code, stdout, stderr = _run_local_command(command, cwd=repo_root)
        results.append(
            {
                "command": shlex.join(command),
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "success": exit_code == 0,
            }
        )
    return results


def _common_codex_exec_args(model: str, reasoning_effort: str, cwd: Path | None) -> list[str]:
    args = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "--color",
        "never",
        "--model",
        model,
        "-c",
        f'reasoning_effort="{reasoning_effort}"',
    ]
    if cwd:
        args.extend(["--cd", str(cwd)])
    return args


def _run_codex_exec_capture_last_message(
    *,
    model: str,
    reasoning_effort: str,
    prompt: str,
    cwd: Path | None = None,
    sandbox: str | None = None,
    output_schema: dict[str, Any] | None = None,
) -> str:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        last_message_path = temp_path / "last_message.txt"
        args = _common_codex_exec_args(model, reasoning_effort, cwd)
        if sandbox:
            args.extend(["--sandbox", sandbox])
        if output_schema is not None:
            schema_path = temp_path / "output_schema.json"
            schema_path.write_text(json.dumps(output_schema), encoding="utf-8")
            args.extend(["--output-schema", str(schema_path)])
        args.extend(["--output-last-message", str(last_message_path), "-"])
        _run_codex_command(args, prompt=prompt, cwd=cwd)
        return last_message_path.read_text(encoding="utf-8").strip()


@mcp.tool()
def analyze_request(request: str, repo_path: str) -> str:
    """Analyze a request and return only the generated implementation prompt."""
    repo = Path(repo_path).expanduser().resolve()
    if not repo.exists():
        raise FileNotFoundError(f"Repository path does not exist: {repo}")
    if not repo.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {repo}")

    repo_context = _build_repo_context(repo, request)

    full_prompt = (
        f"<system>\n{ORCHESTRATOR_SYSTEM_PROMPT}\n</system>\n\n"
        f"<user>\n{repo_context}\n</user>\n"
    )
    output = _run_codex_exec_capture_last_message(
        model=DEFAULT_ORCHESTRATOR_MODEL,
        reasoning_effort=DEFAULT_ORCHESTRATOR_REASONING,
        prompt=full_prompt,
        cwd=repo,
        sandbox="read-only",
        output_schema=IMPLEMENTATION_PROMPT_SCHEMA,
    )
    payload = json.loads(output)
    return _extract_implementation_prompt(payload["implementation_prompt"])


@mcp.tool()
def implement(prompt: str) -> str:
    """Run the implementation agent with zero prior context."""
    payload = _run_implementation_agent(prompt)
    return _render_implementation_result(payload)


def _run_implementation_agent(prompt: str) -> dict[str, Any]:
    repo_root = _extract_repo_root(prompt)
    if repo_root is None:
        raise ValueError(
            'Implementation prompt must include a line like "Repository root: /absolute/path".'
        )
    implementation_prompt = (
        f"<system>\n{IMPLEMENTOR_INSTRUCTIONS}\n</system>\n\n"
        f"<user>\n{prompt}\n</user>\n"
    )
    output = _run_codex_exec_capture_last_message(
        model=DEFAULT_IMPLEMENTOR_MODEL,
        reasoning_effort=DEFAULT_IMPLEMENTOR_REASONING,
        prompt=implementation_prompt,
        cwd=repo_root,
        sandbox="workspace-write",
        output_schema=IMPLEMENTATION_RESULT_SCHEMA,
    )
    payload = json.loads(output)
    return payload


@mcp.tool()
def run_pipeline(request: str, repo_path: str) -> dict[str, Any]:
    """Generate an implementation prompt, save it, then run the implementation agent."""
    generated_prompt = analyze_request(request=request, repo_path=repo_path)
    _save_prompt(generated_prompt)
    repo_root = _extract_repo_root(generated_prompt)
    before_snapshot = _snapshot_repo_files(repo_root) if repo_root else {}
    implementation_payload = _run_implementation_agent(generated_prompt)
    after_snapshot = _snapshot_repo_files(repo_root) if repo_root else {}
    detected_changed_files = _detect_snapshot_changes(before_snapshot, after_snapshot)
    merged_touched_files = _merge_touched_files(
        repo_root,
        implementation_payload.get("touched_files") or [],
        detected_changed_files,
    )
    implementation_payload["touched_files"] = merged_touched_files
    implementation_result = _render_implementation_result(implementation_payload)
    post_verification = _post_verify(
        repo_root,
        merged_touched_files,
    )
    response = {
        "generated_prompt": generated_prompt,
        "implementation_result": implementation_result,
    }
    if post_verification:
        response["post_verification"] = post_verification
    return response


@mcp.resource("prompts://history")
def prompt_history() -> list[dict[str, str]]:
    """Return metadata and contents for the last 10 saved implementation prompts."""
    if not PROMPT_DIR.exists():
        return []

    prompt_files = sorted(PROMPT_DIR.glob("*.md"), reverse=True)[:10]
    history: list[dict[str, str]] = []
    for path in prompt_files:
        history.append(
            {
                "timestamp": path.stem,
                "path": str(path),
                "prompt": path.read_text(encoding="utf-8"),
            }
        )
    return history


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
