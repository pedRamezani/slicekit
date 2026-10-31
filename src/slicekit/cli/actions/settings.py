"""Actions that change the parameters: layout, infill preset and the full parameter editor."""

from __future__ import annotations

import dataclasses
from typing import Any

from ...axes import PLANE_NAME
from ...pipeline.params import PRESETS, KitParams
from .. import prompts
from ..options import format_value, parse_value
from ..prompts import Option
from ..session import Session


def choose_layout(s: Session) -> None:
    """Choose interlocking plates or a slice stack, then thickness, scale and (if interlocking) families and gap."""
    p = s.params
    kind = prompts.select(
        "Layout",
        [
            Option("Interlocking: slotted plates", "interlocking", "two families of plates that slide into each other"),
            Option("Stack: sagittal slices", "sagittal", "gapless slices left to right, no slots"),
            Option("Stack: coronal slices", "coronal", "gapless slices front to back, no slots"),
            Option("Stack: axial slices", "axial", "gapless slices feet to head, no slots"),
        ],
        default=PLANE_NAME[p.stack_axis] if p.stack_axis else "interlocking",
    )
    thickness = prompts.number("Plate thickness (mm)", p.thickness)
    scale = prompts.number("Model scale", p.scale)
    if kind == "interlocking":
        normals = prompts.select(
            "Plate families",
            [
                Option("axial + coronal", ("z", "y"), "coronal plates slide in left-right"),
                Option("axial + sagittal", ("z", "x"), "sagittal plates slide in front-back"),
                Option("coronal + sagittal", ("y", "x"), "sagittal plates slide in vertically"),
            ],
            default=p.normals,
        )
        gap = prompts.number("Gap between parallel plates (mm)", p.gap)
        s.params = dataclasses.replace(p, stack=None, normals=normals, gap=gap, thickness=thickness, scale=scale)
    else:
        s.params = dataclasses.replace(p, stack=kind, thickness=thickness, scale=scale)


def choose_preset(s: Session) -> None:
    """Apply one of ``PRESETS`` (it changes only the infill settings it lists)."""
    options = [
        Option(f"{name:<10} {text}", name, ", ".join(f"{k}={v}" for k, v in cfg.items()))
        for name, (text, cfg) in PRESETS.items()
    ]
    current = next(
        (n for n, (_, cfg) in PRESETS.items() if all(getattr(s.params, k) == v for k, v in cfg.items())), "photo"
    )
    name = prompts.select("Infill preset", options, default=current)
    s.params = dataclasses.replace(s.params, **PRESETS[name][1])


def edit_params(s: Session) -> None:
    """List every parameter with its value; pick one to change it, Done or left/Esc to leave.

    Raises:
        Back: The user pressed left arrow or Esc in the parameter list.
    """
    fields = {f.name: f for f in dataclasses.fields(KitParams)}
    width = max(map(len, fields))
    last = None
    while True:
        options = [Option("Done", None)]
        for name, f in fields.items():
            value = format_value(getattr(s.params, name))
            mark = "*" if getattr(s.params, name) != f.default else " "
            options.append(Option(f"{mark} {name:<{width}}  {value}", name, f.metadata.get("help", "")))
        name = prompts.select("Parameter to change (* = changed; lengths in printed mm)", options, default=last)
        if name is None:
            return
        last = name
        try:
            value = _ask_value(s.params, fields[name])
        except prompts.Back:  # back to the parameter list, not the main menu
            continue
        s.params = dataclasses.replace(s.params, **{name: value})


def _ask_value(params: KitParams, f: dataclasses.Field[Any]) -> Any:
    """Ask for a new value of one KitParams field, with a widget that fits its type."""
    current = getattr(params, f.name)
    if isinstance(f.default, bool):
        return prompts.select(f.name, [Option("yes", True), Option("no", False)], default=current)
    if "choices" in f.metadata:
        options = [Option(c, c) for c in f.metadata["choices"]]
        if f.default is None:
            options.insert(0, Option("none", None))
        return prompts.select(f.name, options, default=current)

    def check(text: str) -> str | None:
        try:
            dataclasses.replace(params, **{f.name: parse_value(f, text)})
        except (ValueError, TypeError) as err:
            return str(err)
        return None

    return parse_value(f, prompts.text(f.name, format_value(current), check))
