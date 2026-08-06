from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


_NAME_SEPARATOR_RE = re.compile(r"[-_.]+")


def _normalized_name(name: str) -> str:
    """Normalize distribution names for duplicate detection."""
    return _NAME_SEPARATOR_RE.sub("-", name).lower()


def _load_exact_pins(
    requirements_file: Path,
) -> tuple[tuple[str, str], ...]:
    """Load active Package==version entries from requirements.txt."""
    try:
        lines = requirements_file.read_text(
            encoding="utf-8-sig",
        ).splitlines()
    except OSError as exc:
        raise RuntimeError(
            f"Unable to read runtime requirements: {requirements_file}"
        ) from exc

    pins = {}
    errors = []

    for line_number, raw_line in enumerate(lines, 1):
        # requirements.txt currently contains exact production pins.
        line = raw_line.split("#", 1)[0].strip()

        if not line:
            continue

        if line.count("==") != 1:
            errors.append(
                f"line {line_number}: expected Package==version"
            )
            continue

        package_name, required_version = (
            part.strip()
            for part in line.split("==", 1)
        )

        if not package_name or not required_version:
            errors.append(
                f"line {line_number}: expected Package==version"
            )
            continue

        normalized = _normalized_name(package_name)

        if normalized in pins:
            errors.append(
                f"line {line_number}: duplicate package {package_name}"
            )
            continue

        pins[normalized] = (
            package_name,
            required_version,
        )

    if errors:
        raise RuntimeError(
            "Invalid runtime requirements:\n- "
            + "\n- ".join(errors)
        )

    if not pins:
        raise RuntimeError(
            "requirements.txt contains no runtime requirements"
        )

    return tuple(pins.values())


def validate_requirements() -> None:
    """Fail before importing server.py if the environment has drifted."""
    requirements_file = (
        Path(__file__).resolve().parent
        / "requirements.txt"
    )
    failures = []

    for package_name, required_version in _load_exact_pins(
        requirements_file
    ):
        try:
            installed_version = version(package_name)
        except PackageNotFoundError:
            failures.append(
                f"{package_name}: required {required_version}, "
                "not installed"
            )
            continue

        if installed_version != required_version:
            failures.append(
                f"{package_name}: required {required_version}, "
                f"installed {installed_version}"
            )

    if failures:
        raise RuntimeError(
            "Runtime requirements are not satisfied:\n- "
            + "\n- ".join(failures)
        )