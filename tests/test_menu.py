import dataclasses

import pytest

from slicekit import KitParams
from slicekit.cli import prompts
from slicekit.cli.actions import ACTIONS
from slicekit.cli.actions.settings import edit_params
from slicekit.cli.options import format_value, parse_value
from slicekit.cli.session import Session

FIELDS = {f.name: f for f in dataclasses.fields(KitParams)}


@pytest.mark.parametrize(
    "name, text, expected",
    [
        ("normals", "x z", ("x", "z")),
        ("normals", "('x', 'z')", ("x", "z")),
        ("hu_range", "-900, 400", (-900.0, 400.0)),
        ("hu_range", "none", None),
        ("perceptual", "no", False),
        ("pitch", "3.5", 3.5),
        ("stack", "coronal", "coronal"),
    ],
)
def test_parse_value(name, text, expected):
    assert parse_value(FIELDS[name], text) == expected


def test_every_default_round_trips():
    """Pressing Enter at a prompt re-parses the shown default."""
    params = KitParams()
    for name, f in FIELDS.items():
        value = getattr(params, name)
        assert parse_value(f, format_value(value)) == value, name


def test_invalid_choice_rejected():
    with pytest.raises(ValueError):
        parse_value(FIELDS["infill"], "stripes")


def scripted(monkeypatch, answers):
    """Replace the prompt functions with a queue of answers (an exception class is raised)."""
    queue = list(answers)

    def answer(*args, **kwargs):
        value = queue.pop(0)
        if isinstance(value, type) and issubclass(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(prompts, "select", answer)
    monkeypatch.setattr(prompts, "text", answer)
    return queue


def test_edit_params_back_from_input_returns_to_list(monkeypatch):
    session = Session()
    # thickness -> Esc in its input -> thickness again -> "2.5" -> infill (choice list) -> lines -> Done
    queue = scripted(monkeypatch, ["thickness", prompts.Back, "thickness", "2.5", "infill", "lines", None])
    edit_params(session)
    assert queue == []
    assert session.params.thickness == 2.5
    assert session.params.infill == "lines"


def test_edit_params_back_from_list_leaves_editor(monkeypatch):
    session = Session()
    scripted(monkeypatch, [prompts.Back])
    with pytest.raises(prompts.Back):
        edit_params(session)


def test_select_default_none_vs_no_default(monkeypatch):
    """None is a real option value ("Back", "none"); omitting default means the first option."""
    options = [prompts.Option("folder", "a"), prompts.Option("Back", None)]
    monkeypatch.setattr(prompts, "interactive", lambda: False)
    monkeypatch.setattr(prompts.Prompt, "ask", lambda *a, default=None, **k: default)
    assert prompts.select("Pick", options) == "a"
    assert prompts.select("Pick", options, default=None) is None
    assert prompts.select("Pick", options, default="missing") == "a"


def test_actions_menu_order_and_quit():
    labels = [a.label for a in ACTIONS]
    assert labels[0] == "Select a local DICOM series"
    assert labels[-1] == "Quit" and ACTIONS[-1].run is None
    assert len(set(labels)) == len(labels)
    # Output actions need a series; choosing and configuring do not.
    assert all(
        a.needs_series for a in ACTIONS if a.label in {"Preview", "Build & export STL/STEP", "Show in ocp_vscode"}
    )
    assert not any(a.needs_series for a in ACTIONS[:5])
