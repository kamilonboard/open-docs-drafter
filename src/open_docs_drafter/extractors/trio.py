"""Trio-specific extractors.

- picker_settings: `var name = PickerSetting(value:, step:, min:, max:, type:)` in
  DecimalPickerSettings.swift, giving the picker default, range, step and unit.
- setting_views: `SettingInputSection(...)` calls in settings screens, giving each
  setting's on-screen label and the "Default: ..." text in its help.
"""

import re

from open_docs_drafter.extractors.swift_scan import (
    balanced_args,
    line_of,
    line_text,
    literal,
    named_args,
    render_string,
    string_literal,
)
from open_docs_drafter.facts import Fact, Kind

# PickerSettingType -> unit as stored. Glucose is stored in mg/dL and converted for display.
UNITS = {
    ".glucose": "mg/dL",
    ".factor": "factor",
    ".gram": "g",
    ".insulinUnit": "U",
    ".insulinUnitPerHour": "U/h",
    ".minute": "min",
    ".hour": "h",
}

_PICKER = re.compile(r"\bvar\s+(\w+)\s*=\s*PickerSetting\s*\(")
_SECTION = re.compile(r"\bSettingInputSection\s*\(")
_TYPE_KEY = re.compile(r'^\.(?:decimal|conditionalDecimal)\(\s*"(\w+)"\s*\)$')
_STATE_BINDING = re.compile(r"^\$state\.(\w+)$")
_LOCALIZED = re.compile(r'^String\(\s*localized:\s*"((?:[^"\\]|\\.)*)"')
# Text("Default: ...") or Text(\n "Default: ..."), including interpolated strings.
_HINT_START = re.compile(r'Text\(\s*"Default:')


def picker_settings(path: str, text: str) -> list[Fact]:
    facts: list[Fact] = []
    for m in _PICKER.finditer(text):
        name = m.group(1)
        open_paren = m.end() - 1
        args = balanced_args(text, open_paren)
        if args is None:
            continue
        parsed = named_args(args)
        unit_raw = parsed.get("type", ("", 0))[0].split("PickerSettingType")[-1]
        unit = UNITS.get(unit_raw if unit_raw.startswith(".") else "." + unit_raw.lstrip("."))
        for arg, kind in (
            ("value", Kind.PICKER_DEFAULT),
            ("min", Kind.MIN),
            ("max", Kind.MAX),
            ("step", Kind.STEP),
        ):
            if arg not in parsed:
                continue
            raw, offset = parsed[arg]
            line = line_of(text, open_paren + 1 + offset)
            value = literal(raw)
            facts.append(
                Fact(
                    setting=name,
                    kind=kind,
                    value=value,
                    path=path,
                    line=line,
                    source=line_text(text, line),
                    unit=unit,
                    needs_human=None if value is not None else f"{arg} is not a literal: {raw}",
                )
            )
        if "type" in parsed:
            raw, offset = parsed["type"]
            line = line_of(text, open_paren + 1 + offset)
            facts.append(
                Fact(
                    setting=name,
                    kind=Kind.UNIT,
                    value=unit,
                    path=path,
                    line=line,
                    source=line_text(text, line),
                    unit=unit,
                    needs_human=None if unit else f"unknown picker type: {raw}",
                )
            )
    return facts


def setting_views(path: str, text: str) -> list[Fact]:
    facts: list[Fact] = []
    for m in _SECTION.finditer(text):
        open_paren = m.end() - 1
        args = balanced_args(text, open_paren)
        if args is None:
            continue
        parsed = named_args(args)
        setting = _setting_name(parsed)
        if setting is None:
            continue
        if "label" in parsed:
            raw, offset = parsed["label"]
            line = line_of(text, open_paren + 1 + offset)
            loc = _LOCALIZED.match(raw)
            value = loc.group(1) if loc else literal(raw)
            facts.append(
                Fact(
                    setting=setting,
                    kind=Kind.LABEL,
                    value=value,
                    path=path,
                    line=line,
                    source=line_text(text, line),
                    needs_human=None if value is not None else f"label is not a literal: {raw}",
                )
            )
        for hint in _HINT_START.finditer(args):
            quote = args.index('"', hint.start())
            parsed_string = string_literal(args, quote)
            if parsed_string is None:
                continue
            shown, problem = render_string(parsed_string[0])
            if not shown.startswith("Default:"):
                continue
            line = line_of(text, open_paren + 1 + quote)  # The string's line, not `Text(`.
            facts.append(
                Fact(
                    setting=setting,
                    kind=Kind.HINT_DEFAULT,
                    value=None if problem else shown,
                    path=path,
                    line=line,
                    source=line_text(text, line),
                    needs_human=problem,
                )
            )
    return facts


def _setting_name(parsed: dict[str, tuple[str, int]]) -> str | None:
    type_raw = parsed.get("type", ("", 0))[0]
    key = _TYPE_KEY.match(type_raw)
    if key:
        return key.group(1)
    if type_raw == ".boolean":
        binding = _STATE_BINDING.match(parsed.get("booleanValue", ("", 0))[0])
        if binding:
            return binding.group(1)
    return None
