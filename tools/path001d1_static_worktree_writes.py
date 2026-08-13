#!/usr/bin/env python3
"""PATH-001D.1 recursive static inventory of production filesystem writers.

Reads tracked Python source only. It never reads runtime state, credentials,
logs, media, caches, environment-file contents, or protected data.

The scan inventories direct filesystem mutation sites and subprocess boundaries,
and fails closed when a production write path is statically derived from the
source tree (``__file__``), the process launch directory, or a relative runtime
literal. Source-relative READ paths are intentionally allowed.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys


PRODUCTION_PREFIXES = (
    "server_core/",
    "subsystems/",
)
PRODUCTION_ROOT_FILES = {
    "kotibot_server.py",
    "wsgi.py",
}

WRITE_METHODS = {
    "chmod",
    "hardlink_to",
    "mkdir",
    "rename",
    "replace",
    "rmdir",
    "symlink_to",
    "touch",
    "unlink",
    "write_bytes",
    "write_text",
}

WRITE_HELPERS = {
    "_write_text_atomic",
    "write_json_atomic",
    "write_json_atomic_sync",
}

QUALIFIED_WRITE_FUNCTIONS = {
    "os.chmod": (0,),
    "os.makedirs": (0,),
    "os.mkdir": (0,),
    "os.remove": (0,),
    "os.rename": (0, 1),
    "os.replace": (0, 1),
    "os.rmdir": (0,),
    "os.unlink": (0,),
    "shutil.copy": (0, 1),
    "shutil.copy2": (0, 1),
    "shutil.copyfile": (0, 1),
    "shutil.move": (0, 1),
    "shutil.rmtree": (0,),
}

SUBPROCESS_FUNCTIONS = {
    "call",
    "check_call",
    "check_output",
    "Popen",
    "run",
}

RUNTIME_LITERAL_RE = re.compile(
    r"(?:^|[/\\])[^/\\]+(?:"
    r"\.jsonl?(?:\.[A-Za-z0-9_-]+)?|"
    r"\.sqlite3?|\.db|\.log|\.bak(?:\.[A-Za-z0-9_-]+)?|"
    r"\.tmp|\.pid|\.pem|\.key|\.p12|\.pfx|"
    r"\.mp4|\.m3u8|\.ts|\.apk"
    r")$",
    re.IGNORECASE,
)

RUNTIME_DIRECTORY_NAMES = {
    "cache",
    "camera-hls",
    "camera_hls",
    "chip_tool_storage",
    "chip_tool_subscription_storage",
    "logs",
    "recordings",
    "runtime",
    "state",
    "temp",
    "tmp",
    "videos",
}

SOURCE_TAINT = "source-tree"
LAUNCH_TAINT = "launch-directory"
RELATIVE_RUNTIME_TAINT = "relative-runtime-literal"


@dataclass(frozen=True)
class Site:
    path: str
    line: int
    kind: str
    origin: str

    def render(self) -> str:
        return (
            f"{self.path}:{self.line} "
            f"kind={self.kind} origin={self.origin}"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "PATH-001D.1 static production-write inventory. "
            "Reads tracked source only; never runtime data."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository root (default: current directory)",
    )
    parser.add_argument(
        "--expected-head",
        help="optional exact Git HEAD required before scanning",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="print every inventoried writer and subprocess boundary",
    )
    return parser


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


def tracked_production_python(root: Path) -> list[str]:
    tracked = _git(root, "ls-files").splitlines()
    result = []

    for raw in tracked:
        path = raw.strip()

        if not path.endswith(".py"):
            continue

        if (
            path in PRODUCTION_ROOT_FILES
            or path.startswith(PRODUCTION_PREFIXES)
        ):
            result.append(path)

    return sorted(result)


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


def _is_relative_runtime_literal(value: str) -> bool:
    value = str(value or "").strip()

    if not value or "://" in value:
        return False

    path = Path(value)

    if path.is_absolute():
        return False

    normalized = value.replace("\\", "/")
    parts = {part.lower() for part in normalized.split("/") if part}

    return bool(
        RUNTIME_LITERAL_RE.search(normalized)
        or parts.intersection(RUNTIME_DIRECTORY_NAMES)
    )


def _direct_taints(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()

    taints = set()

    for item in ast.walk(node):
        if isinstance(item, ast.Name) and item.id == "__file__":
            taints.add(SOURCE_TAINT)

        if isinstance(item, ast.Call):
            name = _dotted_name(item.func)

            if name in {
                "Path.cwd",
                "os.getcwd",
                "getcwd",
            }:
                taints.add(LAUNCH_TAINT)

            if (
                name == "Path"
                and not item.args
                and not item.keywords
            ):
                taints.add(LAUNCH_TAINT)

            if name == "Path" and item.args:
                literal = _literal_string(item.args[0])

                if literal in {"", "."}:
                    taints.add(LAUNCH_TAINT)

    # A relative literal is only a launch-directory risk when it is itself
    # used as a filesystem path. Do not taint every string nested inside a
    # larger expression: runtime-safe joins such as
    # ``stream_dir / "seg_%05d.ts"`` would otherwise become false positives.
    if isinstance(node, ast.Call):
        name = _dotted_name(node.func)

        if name == "Path" and node.args:
            literal = _literal_string(node.args[0])

            if literal and not Path(literal).is_absolute():
                taints.add(LAUNCH_TAINT)

    return taints


def _dependency_names(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()

    dependencies = set()

    for item in ast.walk(node):
        if isinstance(item, ast.Name) and item.id != "__file__":
            dependencies.add(item.id)
        elif isinstance(item, ast.Attribute):
            dotted = _dotted_name(item)

            if dotted:
                dependencies.add(dotted)

    return dependencies


def _target_names(target: ast.AST) -> set[str]:
    if isinstance(target, (ast.Name, ast.Attribute)):
        dotted = _dotted_name(target)
        return {dotted} if dotted else set()

    if isinstance(target, (ast.Tuple, ast.List)):
        names = set()

        for item in target.elts:
            names.update(_target_names(item))

        return names

    return set()


class _ScopeAssignmentCollector(ast.NodeVisitor):
    """Collect assignments in one lexical scope, excluding nested scopes."""

    def __init__(self) -> None:
        self.assignments: dict[str, list[ast.AST]] = {}

    def _record(self, target: ast.AST, value: ast.AST | None) -> None:
        if value is None:
            return

        for name in _target_names(target):
            self.assignments.setdefault(name, []).append(value)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._record(target, node.value)

        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._record(node.target, node.value)

        if node.value is not None:
            self.visit(node.value)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._record(node.target, node.value)
        self.visit(node.value)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return


def _scope_assignments(scope: ast.AST) -> dict[str, list[ast.AST]]:
    collector = _ScopeAssignmentCollector()

    body = getattr(scope, "body", [])

    if isinstance(body, list):
        for statement in body:
            collector.visit(statement)

    return collector.assignments


def _resolve_assignment_taints(
    assignments: dict[str, list[ast.AST]],
    inherited: dict[str, set[str]] | None = None,
) -> dict[str, set[str]]:
    taints = {
        name: set(values)
        for name, values in (inherited or {}).items()
    }

    for name, values in assignments.items():
        taints.setdefault(name, set()).update(
            taint
            for value in values
            for taint in _direct_taints(value)
        )

    changed = True

    while changed:
        changed = False

        for name, values in assignments.items():
            combined = set(taints.get(name, set()))

            for value in values:
                combined.update(_direct_taints(value))

                for dependency in _dependency_names(value):
                    combined.update(taints.get(dependency, set()))

            if combined != taints.get(name, set()):
                taints[name] = combined
                changed = True

    return taints


def _scope_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents = {}

    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    return parents


def _nearest_scope(
    node: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> ast.AST:
    current = node

    while current in parents:
        current = parents[current]

        if isinstance(
            current,
            (
                ast.Module,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            return current

    return current


def _scope_taints(tree: ast.Module) -> dict[int, dict[str, set[str]]]:
    module_taints = _resolve_assignment_taints(
        _scope_assignments(tree)
    )
    result = {id(tree): module_taints}

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            continue

        # Module assignments are visible in nested scopes. This is intentionally
        # conservative: false-positive taint is preferable to missing a
        # source-derived runtime write.
        result[id(node)] = _resolve_assignment_taints(
            _scope_assignments(node),
            inherited=module_taints,
        )

    return result


def expression_taints(
    node: ast.AST | None,
    tainted_names: dict[str, set[str]],
) -> set[str]:
    taints = _direct_taints(node)

    if node is None:
        return taints

    for name in _dependency_names(node):
        taints.update(tainted_names.get(name, set()))

    return taints


def _write_mode(call: ast.Call) -> bool:
    mode = None

    if len(call.args) >= 2:
        mode = _literal_string(call.args[1])

    for keyword in call.keywords:
        if keyword.arg == "mode":
            mode = _literal_string(keyword.value)

    if mode is None:
        return False

    return any(character in mode for character in "wax+")


def _looks_pathish_expression(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        name = _dotted_name(node.func)

        if name in {"Path", "PurePath"}:
            return True

        if isinstance(node.func, ast.Attribute):
            if node.func.attr in {
                "resolve",
                "with_name",
                "with_suffix",
                "joinpath",
            }:
                return True

    dotted = _dotted_name(node)

    if dotted:
        segments = dotted.split(".")

        for segment in segments:
            lowered = segment.lower()

            if (
                lowered in {
                    "path",
                    "file",
                    "directory",
                    "dir",
                    "root",
                    "target",
                    "source",
                    "destination",
                    "playlist",
                }
                or lowered.endswith(
                    (
                        "_path",
                        "_file",
                        "_dir",
                        "_root",
                        "_directory",
                    )
                )
            ):
                return True

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return True

    if isinstance(node, ast.Attribute):
        return _looks_pathish_expression(node.value)

    return False


def _direct_relative_path_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value.strip()

        if not value or "://" in value:
            return False

        return not Path(value).is_absolute()

    if isinstance(node, ast.Call) and _dotted_name(node.func) == "Path":
        if not node.args:
            return True

        literal = _literal_string(node.args[0])

        if literal is not None:
            return not Path(literal).is_absolute()

    return False


def _method_write_path_nodes(call: ast.Call) -> list[ast.AST]:
    if not isinstance(call.func, ast.Attribute):
        return []

    method = call.func.attr

    if method == "open":
        if not _write_mode(call):
            return []

        return [call.func.value]

    if method not in WRITE_METHODS:
        return []

    # str.replace() is extremely common in production source. Path.replace()
    # and Path.rename() are only treated as filesystem mutations when their
    # receiver is path-shaped.
    if method in {"rename", "replace"}:
        if not _looks_pathish_expression(call.func.value):
            return []

    nodes = [call.func.value]

    if method in {"rename", "replace", "hardlink_to", "symlink_to"}:
        if call.args:
            nodes.append(call.args[0])

    return nodes


def _function_write_path_nodes(call: ast.Call) -> list[ast.AST]:
    name = _dotted_name(call.func)

    if name == "open":
        if not _write_mode(call) or not call.args:
            return []

        return [call.args[0]]

    if name in WRITE_HELPERS:
        if not call.args:
            return []

        return [call.args[0]]

    indexes = QUALIFIED_WRITE_FUNCTIONS.get(name)

    if indexes is None:
        return []

    return [
        call.args[index]
        for index in indexes
        if len(call.args) > index
    ]


def _origin_for(
    node: ast.AST,
    tainted_names: dict[str, set[str]],
) -> str:
    taints = expression_taints(node, tainted_names)

    if SOURCE_TAINT in taints:
        return SOURCE_TAINT

    if LAUNCH_TAINT in taints:
        return LAUNCH_TAINT

    if _direct_relative_path_literal(node):
        return LAUNCH_TAINT

    if RELATIVE_RUNTIME_TAINT in taints:
        return RELATIVE_RUNTIME_TAINT

    dotted = {
        _dotted_name(item)
        for item in ast.walk(node)
        if isinstance(item, (ast.Name, ast.Attribute))
    }

    if any(
        name.startswith(("paths.", "runtime_paths."))
        or name in {"paths", "runtime_paths"}
        for name in dotted
    ):
        return "runtime-path-resolver"

    if dotted:
        return "path-variable"

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if Path(node.value).is_absolute():
            return "absolute-path-literal"

    return "unresolved"


def scan_python_source(
    source: str,
    source_path: str,
) -> tuple[list[Site], list[Site]]:
    tree = ast.parse(source, filename=source_path)
    parents = _scope_parent_map(tree)
    taints_by_scope = _scope_taints(tree)
    writer_sites = []
    subprocess_sites = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        scope = _nearest_scope(node, parents)
        tainted_names = taints_by_scope.get(
            id(scope),
            taints_by_scope[id(tree)],
        )
        method_nodes = _method_write_path_nodes(node)
        function_nodes = _function_write_path_nodes(node)

        seen_ids = set()

        for path_node in [*method_nodes, *function_nodes]:
            marker = id(path_node)

            if marker in seen_ids:
                continue

            seen_ids.add(marker)

            name = _dotted_name(node.func)
            kind = (
                name.rsplit(".", 1)[-1]
                or type(node.func).__name__
            )
            writer_sites.append(
                Site(
                    path=source_path,
                    line=int(getattr(node, "lineno", 0) or 0),
                    kind=kind,
                    origin=_origin_for(path_node, tainted_names),
                )
            )

        call_name = _dotted_name(node.func)
        leaf = call_name.rsplit(".", 1)[-1]

        if leaf in SUBPROCESS_FUNCTIONS:
            origin = "unresolved"

            if node.args:
                command_taints = expression_taints(
                    node.args[0],
                    tainted_names,
                )

                if SOURCE_TAINT in command_taints:
                    origin = SOURCE_TAINT
                elif LAUNCH_TAINT in command_taints:
                    origin = LAUNCH_TAINT
                elif RELATIVE_RUNTIME_TAINT in command_taints:
                    origin = RELATIVE_RUNTIME_TAINT

            for keyword in node.keywords:
                if keyword.arg == "cwd":
                    cwd_taints = expression_taints(
                        keyword.value,
                        tainted_names,
                    )

                    if SOURCE_TAINT in cwd_taints:
                        origin = SOURCE_TAINT
                    elif LAUNCH_TAINT in cwd_taints:
                        origin = LAUNCH_TAINT

            subprocess_sites.append(
                Site(
                    path=source_path,
                    line=int(getattr(node, "lineno", 0) or 0),
                    kind=f"subprocess:{leaf}",
                    origin=origin,
                )
            )

    return writer_sites, subprocess_sites


def scan_repository(root: Path) -> dict:
    root = Path(root).resolve()
    source_paths = tracked_production_python(root)
    writers = []
    subprocesses = []

    for relative in source_paths:
        source = (root / relative).read_text(
            encoding="utf-8",
        )
        found_writers, found_subprocesses = scan_python_source(
            source,
            relative,
        )
        writers.extend(found_writers)
        subprocesses.extend(found_subprocesses)

    forbidden_origins = {
        SOURCE_TAINT,
        LAUNCH_TAINT,
        RELATIVE_RUNTIME_TAINT,
    }
    violations = [
        site
        for site in [*writers, *subprocesses]
        if site.origin in forbidden_origins
    ]
    unresolved_writers = [
        site
        for site in writers
        if site.origin == "unresolved"
    ]

    return {
        "production_python_files": len(source_paths),
        "writer_sites": writers,
        "subprocess_sites": subprocesses,
        "violations": violations,
        "unresolved_writers": unresolved_writers,
    }


def render_summary(result: dict) -> list[str]:
    writers = list(result["writer_sites"])
    subprocesses = list(result["subprocess_sites"])
    violations = list(result["violations"])
    unresolved_writers = list(
        result.get("unresolved_writers", [])
    )

    writer_origins = Counter(site.origin for site in writers)
    subprocess_origins = Counter(
        site.origin
        for site in subprocesses
    )

    return [
        "PATH-001D.1 static production-write inventory completed.",
        (
            "production-python-files: "
            f"{int(result['production_python_files'])}"
        ),
        f"direct-writer-sites: {len(writers)}",
        f"subprocess-boundaries: {len(subprocesses)}",
        (
            "writer-origins: "
            f"runtime-path-resolver={writer_origins['runtime-path-resolver']} "
            f"path-variable={writer_origins['path-variable']} "
            f"unresolved={writer_origins['unresolved']} "
            f"source-tree={writer_origins[SOURCE_TAINT]} "
            f"launch-directory={writer_origins[LAUNCH_TAINT]} "
            f"relative-runtime-literal="
            f"{writer_origins[RELATIVE_RUNTIME_TAINT]}"
        ),
        (
            "subprocess-origins: "
            f"unresolved={subprocess_origins['unresolved']} "
            f"source-tree={subprocess_origins[SOURCE_TAINT]} "
            f"launch-directory={subprocess_origins[LAUNCH_TAINT]} "
            f"relative-runtime-literal="
            f"{subprocess_origins[RELATIVE_RUNTIME_TAINT]}"
        ),
        f"forbidden-worktree-derivation-sites: {len(violations)}",
        f"unresolved-writer-sites: {len(unresolved_writers)}",
        (
            "PATH-001D.1 static gate: "
            + ("PASS" if not violations else "BLOCKED")
        ),
        "runtime-data-read: no",
        "destructive-changes-performed: no",
    ]


def run(args) -> int:
    root = Path(args.root).resolve()

    if args.expected_head:
        actual = _git(root, "rev-parse", "HEAD").strip()

        if actual != str(args.expected_head).strip():
            print(
                "PATH-001D.1 stopped: authoritative source mismatch; "
                "no runtime data read."
            )
            return 2

    result = scan_repository(root)

    for line in render_summary(result):
        print(line)

    if args.details:
        for site in result["writer_sites"]:
            print("writer-site:", site.render())

        for site in result["subprocess_sites"]:
            print("subprocess-site:", site.render())

    if result["violations"]:
        for site in result["violations"]:
            print("BLOCKED:", site.render())

    if result.get("unresolved_writers") and args.details:
        for site in result["unresolved_writers"]:
            print("UNRESOLVED-WRITER:", site.render())

    if result["violations"]:
        return 1

    return 0


def main(argv=None) -> int:
    try:
        return run(_parser().parse_args(argv))
    except (
        OSError,
        UnicodeError,
        SyntaxError,
        subprocess.CalledProcessError,
    ) as exc:
        print(
            "PATH-001D.1 stopped: static source inventory failed: "
            f"{type(exc).__name__}; no runtime data read."
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
