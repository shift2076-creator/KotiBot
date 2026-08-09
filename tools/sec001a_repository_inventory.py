#!/usr/bin/env python3
"""Create the value-free SEC-001A repository/source inventory.

This scanner reads tracked source code and .gitignore only. It never opens
JSON/JSONL state, credentials, environment files, databases, media, logs, or
other runtime data. Output is limited to names, repository-relative source
locations, and operation types.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from pathlib import Path
import re
import subprocess


DEFAULT_OUTPUT = Path(
    "docs/security/SEC-001A_REPOSITORY_SOURCE_INVENTORY.md"
)
SCANNER_PATH = "tools/sec001a_repository_inventory.py"
PYTHON_SUFFIX = ".py"
TEXT_SOURCE_SUFFIXES = {
    ".html",
    ".js",
    ".kt",
    ".kts",
    ".py",
    ".xml",
}
RUNTIME_FILE_RE = re.compile(
    r"(?:^|[/\\])[^/\\]+(?:"
    r"\.jsonl?(?:\.[A-Za-z0-9_-]+)?|"
    r"\.sqlite3?|\.db|\.log|\.bak(?:\.[A-Za-z0-9_-]+)?|"
    r"\.tmp|\.pid|\.pem|\.key|\.p12|\.pfx|"
    r"\.mp4|\.m3u8|\.apk"
    r")$",
    re.IGNORECASE,
)
RUNTIME_DIRECTORY_NAMES = {
    "cache",
    "camera_hls",
    "chip_tool_storage",
    "chip_tool_subscription_storage",
    "logs",
    "recordings",
    "runtime",
    "temp",
    "tmp",
    "videos",
}
TRACKED_RUNTIME_RE = re.compile(
    r"(?:\.jsonl?(?:\..*)?|\.sqlite3?|\.db|\.log|\.bak(?:\..*)?|"
    r"\.tmp|\.pid|\.pem|\.key|\.p12|\.pfx)$",
    re.IGNORECASE,
)
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")
ENV_HELPERS = {
    "_env_bool",
    "_matter_env_bool",
    "_matter_env_seconds",
    "env_enabled",
}
READ_CALLS = {
    "from_service_account_file",
    "json_exists",
    "load",
    "loads",
    "open",
    "read_bytes",
    "read_json",
    "read_text",
}
WRITE_CALLS = {
    "chmod",
    "dump",
    "dumps",
    "mkdir",
    "open",
    "replace",
    "rename",
    "rmtree",
    "unlink",
    "write",
    "write_bytes",
    "write_json_atomic",
    "write_text",
}
BROWSER_STORAGE_RE = re.compile(
    r"\b(localStorage|sessionStorage)\."
    r"(getItem|setItem|removeItem)\(\s*(['\"])([^'\"]+)\3"
)
INDEXED_DB_RE = re.compile(
    r"\bindexedDB\.open\(\s*(['\"])([^'\"]+)\1"
)
DYNAMIC_ENVIRONMENT_NAMES = {
    "KOTIBOT_MATTER_SENSOR_SUBSCRIBE_ENABLED": (
        "subsystems/matter/matter_routes.py",
        "dynamic environment prefix",
    ),
    "KOTIBOT_MATTER_SENSOR_SUBSCRIBE_INITIAL_DELAY_SECONDS": (
        "subsystems/matter/matter_routes.py",
        "dynamic environment prefix",
    ),
    "KOTIBOT_MATTER_SENSOR_SUBSCRIBE_MAX_SECONDS": (
        "subsystems/matter/matter_routes.py",
        "dynamic environment prefix",
    ),
    "KOTIBOT_MATTER_SENSOR_SUBSCRIBE_MIN_SECONDS": (
        "subsystems/matter/matter_routes.py",
        "dynamic environment prefix",
    ),
    "KOTIBOT_MATTER_SENSOR_SUBSCRIBE_RETRY_SECONDS": (
        "subsystems/matter/matter_routes.py",
        "dynamic environment prefix",
    ),
}


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr

    return ""


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _safe_runtime_literal(
    value: str,
    *,
    allow_directory: bool = False,
) -> str | None:
    value = str(value or "").strip()

    if not value or "\n" in value or "\r" in value:
        return None

    if "://" in value:
        return None

    normalized = value.replace("\\", "/")
    path_parts = {part.lower() for part in normalized.split("/") if part}
    is_runtime_file = bool(RUNTIME_FILE_RE.search(normalized))
    is_runtime_directory = bool(
        allow_directory
        and path_parts.intersection(RUNTIME_DIRECTORY_NAMES)
    )

    if not is_runtime_file and not is_runtime_directory:
        return None

    if Path(value).is_absolute():
        return "<absolute-path-redacted>"

    return normalized


class PythonInventory(ast.NodeVisitor):
    def __init__(self, source_path: str) -> None:
        self.source_path = source_path
        self.environment_names: dict[str, set[str]] = defaultdict(set)
        self.runtime_literals: dict[str, set[str]] = defaultdict(set)
        self.operations: list[tuple[str, int, str]] = []
        self.candidate_keys: set[str] = set()
        self.schema_keys: dict[str, set[str]] = defaultdict(set)
        self.source_relative_lines: set[int] = set()

    def _location(self, node: ast.AST) -> str:
        return f"{self.source_path}:{getattr(node, 'lineno', 0)}"

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == "__file__":
            self.source_relative_lines.add(node.lineno)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            candidate = _safe_runtime_literal(node.value)

            if candidate:
                self.runtime_literals[candidate].add(
                    self._location(node)
                )
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Div):
            for child in ast.walk(node):
                value = _literal_string(child)

                if value is None:
                    continue

                candidate = _safe_runtime_literal(
                    value,
                    allow_directory=True,
                )

                if candidate:
                    self.runtime_literals[candidate].add(
                        self._location(child)
                    )

        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key in node.keys:
            value = _literal_string(key)
            if value:
                self.candidate_keys.add(value)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        value = _literal_string(node.slice)
        if value:
            self.candidate_keys.add(value)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        names = [
            target.id
            for target in node.targets
            if isinstance(target, ast.Name)
        ]

        for name in names:
            if "STATE_KEYS" not in name and not name.endswith("_KEYS"):
                continue

            for child in ast.walk(node.value):
                value = _literal_string(child)
                if value:
                    self.schema_keys[name].add(value)

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        dotted = _dotted_name(node.func)
        short_name = dotted.rsplit(".", 1)[-1]
        first = _literal_string(node.args[0]) if node.args else None

        if first and short_name in {"Path", "with_name", "with_suffix"}:
            candidate = _safe_runtime_literal(
                first,
                allow_directory=True,
            )

            if candidate:
                self.runtime_literals[candidate].add(
                    self._location(node)
                )

        if dotted in {"os.environ.get", "os.getenv"}:
            if first and ENV_NAME_RE.fullmatch(first):
                self.environment_names[first].add(self._location(node))
        elif short_name in ENV_HELPERS:
            if first and ENV_NAME_RE.fullmatch(first):
                self.environment_names[first].add(self._location(node))

        if short_name in {"get", "pop", "setdefault"} and first:
            self.candidate_keys.add(first)

        read = short_name in READ_CALLS
        write = short_name in WRITE_CALLS

        if read or write:
            operation = "read/write" if read and write else (
                "read" if read else "write"
            )
            self.operations.append((operation, node.lineno, dotted))

        self.generic_visit(node)


def _tracked_files(root: Path) -> list[str]:
    output = _git(root, "ls-files", "-z")
    return sorted(path for path in output.split("\0") if path)


def _markdown_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _join_locations(locations: set[str]) -> str:
    return ", ".join(f"`{item}`" for item in sorted(locations))


def build_inventory(root: Path) -> str:
    tracked = _tracked_files(root)
    environment_names: dict[str, set[str]] = defaultdict(set)
    runtime_literals: dict[str, set[str]] = defaultdict(set)
    operations: list[tuple[str, int, str, str]] = []
    candidate_keys: dict[str, set[str]] = defaultdict(set)
    schema_keys: dict[str, dict[str, set[str]]] = defaultdict(dict)
    source_relative: dict[str, set[int]] = defaultdict(set)
    browser_storage: list[tuple[str, str, str, int]] = []

    for relative in tracked:
        if relative == SCANNER_PATH:
            continue

        path = root / relative

        if path.suffix.lower() not in TEXT_SOURCE_SUFFIXES:
            continue

        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue

        for line_number, line in enumerate(text.splitlines(), 1):
            for match in BROWSER_STORAGE_RE.finditer(line):
                browser_storage.append((
                    match.group(1),
                    match.group(4),
                    relative,
                    line_number,
                ))

            for match in INDEXED_DB_RE.finditer(line):
                browser_storage.append((
                    "indexedDB",
                    match.group(2),
                    relative,
                    line_number,
                ))

        if path.suffix.lower() != PYTHON_SUFFIX:
            continue

        try:
            tree = ast.parse(text, filename=relative)
        except SyntaxError:
            continue

        visitor = PythonInventory(relative)
        visitor.visit(tree)

        for name, locations in visitor.environment_names.items():
            environment_names[name].update(locations)

        for literal, locations in visitor.runtime_literals.items():
            runtime_literals[literal].update(locations)

        operations.extend(
            (relative, line, operation, call)
            for operation, line, call in visitor.operations
        )

        if visitor.operations or visitor.runtime_literals:
            candidate_keys[relative].update(visitor.candidate_keys)

        if visitor.schema_keys:
            schema_keys[relative] = visitor.schema_keys

        if visitor.source_relative_lines:
            source_relative[relative].update(
                visitor.source_relative_lines
            )

    for name, (source, note) in DYNAMIC_ENVIRONMENT_NAMES.items():
        environment_names[name].add(f"{source} ({note})")

    ignored_patterns = []
    gitignore = root / ".gitignore"

    if gitignore.exists():
        ignored_patterns = [
            line.strip()
            for line in gitignore.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    head = _git(root, "rev-parse", "HEAD").strip()
    lines = [
        "# SEC-001A — Repository and source inventory",
        "",
        f"Source commit at scan time: `{head}`",
        "",
        "## Safety boundary",
        "",
        "This report was generated from tracked source code, tracked path names, "
        "and `.gitignore` patterns only. The scanner did not open runtime JSON, "
        "JSONL, environment files, credentials, databases, logs, media, archives, "
        "Matter controller storage, or virtual-environment files.",
        "",
        "All entries below are names and repository-relative source locations. "
        "Candidate lists require human review before SEC-001A is checked off.",
        "",
        "## Tracked runtime-looking paths",
        "",
    ]

    tracked_runtime = [
        path for path in tracked if TRACKED_RUNTIME_RE.search(path)
    ]

    if tracked_runtime:
        lines.extend(f"- `{path}`" for path in tracked_runtime)
    else:
        lines.append("- None detected by filename.")

    lines.extend([
        "",
        "## Ignored path patterns",
        "",
    ])
    lines.extend(f"- `{pattern}`" for pattern in ignored_patterns)

    lines.extend([
        "",
        "## Runtime path literals declared in source",
        "",
        "| Path or pattern name | Source locations |",
        "| --- | --- |",
    ])

    for literal, locations in sorted(runtime_literals.items()):
        lines.append(
            f"| `{_markdown_cell(literal)}` | "
            f"{_join_locations(locations)} |"
        )

    lines.extend([
        "",
        "## Source-relative path construction",
        "",
        "| Source file | `__file__` lines |",
        "| --- | --- |",
    ])

    for source, line_numbers in sorted(source_relative.items()):
        rendered = ", ".join(str(number) for number in sorted(line_numbers))
        lines.append(f"| `{source}` | {rendered} |")

    lines.extend([
        "",
        "## Environment-variable names",
        "",
        "| Variable name | Source locations |",
        "| --- | --- |",
    ])

    for name, locations in sorted(environment_names.items()):
        lines.append(f"| `{name}` | {_join_locations(locations)} |")

    lines.extend([
        "",
        "## Persistence-related source operations",
        "",
        "These are direct call sites. Indirect reader/writer ownership must be "
        "reconciled during human review.",
        "",
        "| Source location | Operation | Call |",
        "| --- | --- | --- |",
    ])

    for source, line, operation, call in sorted(operations):
        lines.append(
            f"| `{source}:{line}` | {operation} | `{call}` |"
        )

    lines.extend([
        "",
        "## Declared state-key groups",
        "",
    ])

    for source, groups in sorted(schema_keys.items()):
        lines.append(f"### `{source}`")
        lines.append("")

        for group, keys in sorted(groups.items()):
            rendered = ", ".join(f"`{key}`" for key in sorted(keys))
            lines.append(f"- `{group}`: {rendered or 'No literal keys.'}")

        lines.append("")

    lines.extend([
        "## Candidate persisted key names by source file",
        "",
        "This is a deliberately broad static list. Remove API-only and "
        "in-memory-only names during review; do not add values.",
        "",
    ])

    for source, keys in sorted(candidate_keys.items()):
        rendered = ", ".join(f"`{key}`" for key in sorted(keys))
        lines.append(f"### `{source}`")
        lines.append("")
        lines.append(rendered or "No literal candidate keys.")
        lines.append("")

    lines.extend([
        "## Browser storage names",
        "",
        "| Storage | Key/database name | Source location |",
        "| --- | --- | --- |",
    ])

    if browser_storage:
        for storage, key, source, line in sorted(set(browser_storage)):
            lines.append(
                f"| `{storage}` | `{_markdown_cell(key)}` | "
                f"`{source}:{line}` |"
            )
    else:
        lines.append("| — | None detected | — |")

    lines.extend([
        "",
        "## SEC-001A review gate",
        "",
        "Do not check off SEC-001A until:",
        "",
        "- Every runtime path literal is assigned to an owning subsystem.",
        "- Every direct and indirect source reader/writer is reconciled.",
        "- Candidate JSON/JSONL keys are reduced to keys actually persisted.",
        "- Browser storage names are classified for household/personal data.",
        "- Every source-relative runtime path is carried into PATH-001.",
        "- The report is manually confirmed to contain no values or personal data.",
        "",
    ])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a value-free SEC-001A repository/source inventory."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"output path relative to the repository (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output = args.output

    if not output.is_absolute():
        output = root / output

    output = output.resolve()

    try:
        output.relative_to(root)
    except ValueError as exc:
        raise SystemExit("output must remain inside the repository") from exc

    report = build_inventory(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8", newline="\n")
    print(output.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
