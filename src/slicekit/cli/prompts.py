"""Prompts for the interactive menu.

On a terminal, choices are arrow-key menus (questionary): up/down to move, Enter to
confirm, left arrow or Esc to go back (raises ``Back``), Ctrl-C to cancel. When stdin
is not a terminal (piped input, CI), the same calls fall back to numbered rich prompts
so the menu stays scriptable.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.prompt import Confirm, Prompt
from typing_extensions import Sentinel

if TYPE_CHECKING:
    from types import ModuleType

    from prompt_toolkit.styles import Style
    from questionary import Question

console = Console()

STYLE = [
    ("qmark", "fg:#5f87ff bold"),
    ("question", "bold"),
    ("pointer", "fg:#00afaf bold"),
    ("highlighted", "fg:#00afaf bold"),
    ("selected", "fg:#00afaf"),
    ("answer", "fg:#00afaf bold"),
    ("instruction", "fg:#808080 italic"),
    ("disabled", "fg:#6c6c6c italic"),
]


class Back(Exception):
    """The user pressed left arrow or Esc: return to the previous menu.

    Raised by the prompt functions; caught by whoever owns "the previous menu" (the
    main loop, or the parameter editor's list).
    """


# Sentinels (PEP 661): unique markers where None is already a valid value.
_BACK = Sentinel("_BACK")  # what the left/Esc key binding ends a prompt with
_NO_DEFAULT = Sentinel("_NO_DEFAULT")  # select() called without a default


@dataclass
class Option:
    """One entry of a ``select`` menu.

    Attributes:
        label: Text shown in the menu.
        value: Returned when the option is chosen (any value, including None).
        help: Description shown under the menu while the option is highlighted.
        disabled: If set, the option is shown greyed out with this reason and cannot be chosen.
    """

    label: str
    value: Any
    help: str = ""
    disabled: str | None = None


def interactive() -> bool:
    """Whether stdin and stdout are a terminal (arrow-key menus) rather than pipes."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _questionary() -> tuple[ModuleType, Style]:
    import questionary
    from prompt_toolkit.styles import Style

    return questionary, Style(STYLE)


def _with_back_keys(question: Question, keys: Sequence[str]) -> Question:
    """Let ``keys`` end the prompt with the back marker, reacting to Esc without delay."""
    from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings

    bindings = KeyBindings()
    for key in keys:
        # eager: a lone Esc is also the prefix of built-in Esc-<key> shortcuts, so without
        # it prompt_toolkit keeps waiting for a second key. Arrow keys arrive as complete
        # escape sequences and are decoded before this binding is considered.
        bindings.add(key, eager=True)(_exit_back)
    app = question.application
    # Merged last, so these win over questionary's catch-all binding.
    existing = [app.key_bindings] if app.key_bindings is not None else []
    app.key_bindings = merge_key_bindings([*existing, bindings])
    app.ttimeoutlen = 0.05  # how long a lone Esc waits for a possible escape sequence
    return question


def _exit_back(event: Any) -> None:
    """Key binding handler: end the prompt with the back marker."""
    event.app.exit(result=_BACK)


def _ask(question: Question) -> Any:
    """Run a prompt; turn the back marker into ``Back`` (Ctrl-C raises KeyboardInterrupt)."""
    result = question.unsafe_ask()
    if result is _BACK:
        raise Back
    return result


def select(message: str, options: Sequence[Option], default: Any | _NO_DEFAULT = _NO_DEFAULT, back: bool = True) -> Any:
    """Arrow-key menu (numbered prompt when not on a terminal).

    Args:
        message: Question shown above the options.
        options: Menu entries; at least one must be enabled.
        default: Value of the option the cursor starts on (None is a valid value).
            Without it, or if no enabled option has that value, the first enabled
            option is used.
        back: Let left arrow and Esc leave the menu.

    Returns:
        The chosen option's ``value``.

    Raises:
        Back: The user pressed left arrow or Esc (only with ``back=True``).
        KeyboardInterrupt: The user pressed Ctrl-C.
    """
    enabled = [i for i, o in enumerate(options) if not o.disabled]
    matches = [] if default is _NO_DEFAULT else [i for i in enabled if options[i].value == default]
    start = matches[0] if matches else enabled[0]
    if interactive():
        q, style = _questionary()
        # Pass indices, not our values: questionary replaces a None value with the title.
        choices = [q.Choice(o.label, i, disabled=o.disabled, description=o.help or None) for i, o in enumerate(options)]
        hint = "(up/down, Enter" + (", left/Esc back)" if back else ")")
        question = q.select(message, choices, default=choices[start], style=style, instruction=hint, use_jk_keys=False)
        # ``default`` also marks the choice as checked (checkbox-style), which questionary
        # draws as a fixed highlight; keep only the cursor position.
        for control in question.application.layout.find_all_controls():
            if hasattr(control, "selected_options"):
                control.selected_options.clear()
        index = _ask(_with_back_keys(question, ["left", "escape"]) if back else question)
        return options[index].value

    for i, o in enumerate(options, 1):
        note = f" [dim]({o.disabled})[/]" if o.disabled else ""
        console.print(f"  [cyan]{i}[/] {o.label}{note}")
    keys = [str(i + 1) for i in enabled]
    return options[int(Prompt.ask(message, choices=keys, default=str(start + 1), console=console)) - 1].value


def text(message: str, default: str = "", validate: Callable[[str], str | None] | None = None) -> str:
    """Free-text input.

    Args:
        message: Question shown before the input.
        default: Pre-filled text.
        validate: Called with the text on Enter; returns an error message to show, or
            None to accept.

    Returns:
        The accepted text.

    Raises:
        Back: The user pressed Esc (left arrow moves the text cursor here).
        KeyboardInterrupt: The user pressed Ctrl-C.
    """
    if interactive():
        q, style = _questionary()
        check = (lambda value: validate(value) or True) if validate else None
        # Left arrow moves the text cursor here, so only Esc goes back.
        return str(_ask(_with_back_keys(q.text(message, default=default, validate=check, style=style), ["escape"])))
    while True:
        answer = Prompt.ask(message, default=default, console=console)
        error = validate(answer) if validate else None
        if not error:
            return answer
        console.print(f"[red]{error}")


def number(message: str, default: float, minimum: float | None = 0.0) -> float:
    """Number input, re-asked until the text is a valid number.

    Args:
        message: Question shown before the input.
        default: Pre-filled value.
        minimum: The number must be greater than this; None = no limit.

    Returns:
        The number.

    Raises:
        Back: The user pressed Esc.
        KeyboardInterrupt: The user pressed Ctrl-C.
    """

    def check(value: str) -> str | None:
        try:
            number = float(value)
        except ValueError:
            return "Enter a number"
        if minimum is not None and number <= minimum:
            return f"Must be greater than {minimum:g}"
        return None

    return float(text(message, f"{default:g}", check))


def confirm(message: str, default: bool = True) -> bool:
    """Yes/no question.

    Args:
        message: Question to ask.
        default: Answer when the user just presses Enter.

    Returns:
        True for yes.

    Raises:
        Back: The user pressed left arrow or Esc.
        KeyboardInterrupt: The user pressed Ctrl-C.
    """
    if interactive():
        q, style = _questionary()
        return bool(_ask(_with_back_keys(q.confirm(message, default=default, style=style), ["left", "escape"])))
    return Confirm.ask(message, default=default, console=console)
