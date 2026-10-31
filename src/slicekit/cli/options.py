"""KitParams <-> text: CLI flags, menu input and the docs' Parameters table.

Everything that turns the ``KitParams`` field metadata into something a person types or
reads lives here, so the CLI, the menu and the docs cannot disagree.
"""

from __future__ import annotations

import argparse
import dataclasses
from typing import Any

from ..pipeline.params import KitParams


def cli_flag(name: str) -> str:
    """Command-line flag of a KitParams field, e.g. ``hu_range`` -> ``--hu-range``."""
    return "--" + name.replace("_", "-")


def add_param_arguments(parser: argparse.ArgumentParser) -> None:
    """One option per KitParams field, so the dataclass stays the single source of truth."""
    for f in dataclasses.fields(KitParams):
        flag = cli_flag(f.name)
        default: Any = f.default
        help_text = f"{f.metadata.get('help', '')} (default: {default})"
        if isinstance(default, bool):
            parser.add_argument(flag, action=argparse.BooleanOptionalAction, default=default, help=help_text)
        elif isinstance(default, tuple) or "nargs" in f.metadata:
            nargs = f.metadata.get("nargs") or len(default)
            parser.add_argument(
                flag, nargs=nargs, type=float if default is None else type(default[0]), default=default, help=help_text
            )
        else:
            parser.add_argument(
                flag,
                type=f.metadata.get("type", type(default)),
                choices=f.metadata.get("choices"),
                default=default,
                help=help_text,
            )


def params_from_args(args: argparse.Namespace) -> KitParams:
    """KitParams from the generated options (argparse gives lists for nargs; KitParams uses tuples)."""
    values: dict[str, Any] = {}
    for f in dataclasses.fields(KitParams):
        value = getattr(args, f.name)
        values[f.name] = tuple(value) if isinstance(value, list) else value
    return KitParams(**values)


def format_value(value: object) -> str:
    """Prompt-friendly text for a parameter value, which ``parse_value`` reads back.

    Args:
        value: A KitParams field value.

    Returns:
        The text; tuples are space separated and None is ``"none"``.
    """
    if isinstance(value, tuple):
        return " ".join(str(v) for v in value)
    return "none" if value is None else str(value)


def parse_value(f: dataclasses.Field[Any], text: str) -> Any:
    """Parse a typed answer for a KitParams field.

    Args:
        f: The field, whose default and metadata give the type and allowed choices.
        text: The answer; tuples as space or comma separated values, ``none`` for None.

    Returns:
        The value; ``KitParams`` itself still validates it.

    Raises:
        ValueError: The text is not a valid value for the field.
    """
    default: Any = f.default
    text = text.strip()
    if default is None and text.lower() in ("", "none"):
        return None
    if isinstance(default, bool):
        return text.lower() in ("1", "true", "yes", "y", "on")
    if isinstance(default, tuple) or "nargs" in f.metadata:
        kind = float if default is None else type(default[0])
        separators = ",()[]'\""
        cleaned = text.translate(str.maketrans(separators, " " * len(separators)))
        return tuple(kind(x) for x in cleaned.split())
    value = f.metadata.get("type", type(default))(text)
    if "choices" in f.metadata and value not in f.metadata["choices"]:
        raise ValueError(f"choose one of {', '.join(f.metadata['choices'])}")
    return value


def _markdown_cell(value: object) -> str:
    """Text for a Markdown table cell (``|`` would end the cell)."""
    return str(value).replace("|", "\\|")


def parameter_table() -> str:
    """Markdown table of every KitParams field, generated from the field metadata.

    Used by the documentation's Parameters page, so the docs show exactly the help
    texts, defaults and choices of the CLI and the menu.

    Returns:
        A Markdown table with one row per field: name, CLI flag, default, allowed
        values and description.
    """
    rows = [
        "| Parameter | CLI flag | Default | Allowed values | Description |",
        "| --- | --- | --- | --- | --- |",
    ]
    for f in dataclasses.fields(KitParams):
        default: Any = f.default
        flag = cli_flag(f.name)
        if isinstance(default, bool):
            flag = f"{flag} / --no-{flag[2:]}"
        choices = ", ".join(f"`{c}`" for c in f.metadata.get("choices", ()))
        cells = [
            f"`{f.name}`",
            f"`{flag}`",
            f"`{format_value(default)}`",
            choices,
            _markdown_cell(f.metadata.get("help", "")),
        ]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)
