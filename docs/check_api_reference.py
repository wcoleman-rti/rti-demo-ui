"""Verify that generated API references match the supported public surfaces."""

from __future__ import annotations

import argparse
import inspect
from collections.abc import Container
from html.parser import HTMLParser
from pathlib import Path

import rti_demo_ui


CPP_PUBLIC_SYMBOLS = {
    "Badge",
    "Card",
    "CardArea",
    "CommandConfirmation",
    "CommandHandler",
    "CommandSchema",
    "Component",
    "CustomComponent",
    "DemoUiApp",
    "Freshness",
    "GridBounds",
    "Json",
    "Layout",
    "Log",
    "Metric",
    "ReadyInfo",
    "Scene2DViewport",
    "Scene3DViewport",
    "Severity",
    "Table",
    "Text",
    "Theme",
    "TimerHandle",
    "freshness_opacity",
    "to_string",
}

CPP_INTERNAL_SYMBOLS = {
    "ModelTestAccess",
    "SseManager",
    "added_locked",
    "sse_manager_",
    "to_json_locked",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _page_text(path: Path) -> tuple[str, str]:
    source = path.read_text(encoding="utf-8")
    parser = _TextExtractor()
    parser.feed(source)
    return source, " ".join(parser.parts)


def _require_symbols(kind: str, symbols: set[str], available: Container[str]) -> None:
    missing = sorted(symbol for symbol in symbols if symbol not in available)
    if missing:
        raise RuntimeError(f"{kind} reference is missing: {', '.join(missing)}")


def _require_python_docstrings() -> None:
    missing: list[str] = []
    for class_name in rti_demo_ui.__all__:
        class_value = getattr(rti_demo_ui, class_name)
        if not inspect.isclass(class_value):
            continue
        if not inspect.getdoc(class_value):
            missing.append(class_name)
        for member_name, member in vars(class_value).items():
            if member_name.startswith("_"):
                continue
            if inspect.isfunction(member) or isinstance(member, property):
                if not inspect.getdoc(member):
                    missing.append(f"{class_name}.{member_name}")
    if missing:
        raise RuntimeError(
            f"Python public API is missing docstrings: {', '.join(sorted(missing))}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("html_dir", type=Path)
    args = parser.parse_args()

    python_source, _ = _page_text(args.html_dir / "reference" / "python.html")
    python_symbols = set(rti_demo_ui.__all__)
    python_targets = {
        name for name in python_symbols if f'id="rti_demo_ui.{name}"' in python_source
    }
    _require_symbols("Python", python_symbols, python_targets)
    _require_python_docstrings()

    cpp_source, cpp_text = _page_text(args.html_dir / "reference" / "cpp.html")
    _require_symbols("C++", CPP_PUBLIC_SYMBOLS, cpp_text)
    leaked = sorted(symbol for symbol in CPP_INTERNAL_SYMBOLS if symbol in cpp_source)
    if leaked:
        raise RuntimeError(
            f"C++ reference exposes internal symbols: {', '.join(leaked)}"
        )

    print(
        f"Verified {len(python_symbols)} Python exports and "
        f"{len(CPP_PUBLIC_SYMBOLS)} C++ public symbols."
    )


if __name__ == "__main__":
    main()
