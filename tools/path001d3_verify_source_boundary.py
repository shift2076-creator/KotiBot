#!/usr/bin/env python3
"""PATH-001D.3 resolved-runtime/source-boundary verification.

Reads tracked production source and path-related environment settings only. It
never reads runtime files, credentials, logs, media, Matter state, or private
payloads, and it performs no filesystem mutation.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


DEVELOPER_CONTENT_DIRS = (
    "docs",
    "temp",
    "tests",
    "tools",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "PATH-001D.3 resolved-runtime/source-boundary verifier. "
            "Reads no runtime file contents."
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
        required=True,
        help="exact authoritative Git HEAD required before verification",
    )
    return parser


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _is_within(path: Path, parent: Path) -> bool:
    path = Path(path).resolve(strict=False)
    parent = Path(parent).resolve(strict=False)
    return path == parent or parent in path.parents


def evaluate_destinations(
    source_root: Path,
    destinations: dict[str, Path],
) -> dict[str, int]:
    source_root = Path(source_root).resolve(strict=False)
    values = [Path(value) for value in destinations.values()]
    developer_roots = tuple(
        source_root / name
        for name in DEVELOPER_CONTENT_DIRS
    )

    return {
        "resolved": len(values),
        "non_absolute": sum(
            not value.is_absolute()
            for value in values
        ),
        "inside_source": sum(
            _is_within(value, source_root)
            for value in values
        ),
        "developer_content_targets": sum(
            any(
                _is_within(value, developer_root)
                for developer_root in developer_roots
            )
            for value in values
        ),
    }


def run(args) -> int:
    root = Path(args.root).resolve(strict=False)

    if _git_head(root) != str(args.expected_head).strip():
        print(
            "PATH-001D.3 stopped: authoritative source mismatch; "
            "no runtime data read."
        )
        return 2

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from server_core.paths import build_runtime_paths
    from tools.path001d1_static_worktree_writes import scan_repository

    paths = build_runtime_paths(root)
    destination_result = evaluate_destinations(
        root,
        paths.resolved_runtime_destinations(),
    )
    static_result = scan_repository(root)
    static_violations = len(static_result["violations"])
    unresolved_writers = len(static_result["unresolved_writers"])
    blocked = any(
        (
            destination_result["non_absolute"],
            destination_result["inside_source"],
            destination_result["developer_content_targets"],
            static_violations,
            unresolved_writers,
        )
    )

    print("PATH-001D.3 source-boundary verification completed.")
    print("authoritative-head-match: yes")
    print(
        "resolved-runtime-destinations: "
        f"{destination_result['resolved']}"
    )
    print(
        "non-absolute-destinations: "
        f"{destination_result['non_absolute']}"
    )
    print(
        "destinations-inside-source: "
        f"{destination_result['inside_source']}"
    )
    print(
        "developer-content-write-targets: "
        f"{destination_result['developer_content_targets']}"
    )
    print(f"static-forbidden-sites: {static_violations}")
    print(f"static-unresolved-writers: {unresolved_writers}")
    print("runtime-file-contents-read: no")
    print("credential-values-read: no")
    print("destructive-changes-performed: no")
    print(
        "PATH-001D.3 source gate: "
        + ("BLOCKED" if blocked else "PASS")
    )
    print(
        "live-mutation-gate: "
        "tools/path001d2_live_worktree_trace.py"
    )

    return 1 if blocked else 0


def main(argv=None) -> int:
    try:
        return run(_parser().parse_args(argv))
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as exc:
        print(
            "PATH-001D.3 stopped: source-boundary verification "
            f"failed closed: {type(exc).__name__}; "
            "no runtime data read."
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
