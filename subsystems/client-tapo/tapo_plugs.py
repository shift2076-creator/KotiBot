from __future__ import annotations


def plug_control_methods(model: str) -> list[str]:
    methods: list[str] = []
    clean = str(model or "").strip().lower().split("(", 1)[0]
    clean = "".join(ch for ch in clean if ch.isalnum())

    for value in (clean, "p125", "p115", "p110", "p105", "p100"):
        if value and value not in methods:
            methods.append(value)

    return methods