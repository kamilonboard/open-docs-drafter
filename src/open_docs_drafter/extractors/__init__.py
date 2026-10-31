"""Fact extractors. Each reads one kind of source file and returns exact, cited facts.

A project profile chooses which extractor reads which files. Extractors are plain code.
"""

from collections.abc import Callable

from open_docs_drafter.extractors import json_defaults, swift, trio
from open_docs_drafter.facts import Fact

Extractor = Callable[[str, str], list[Fact]]  # (path, text) -> facts

EXTRACTORS: dict[str, Extractor] = {
    "swift_struct_defaults": swift.struct_defaults,
    "swift_coding_keys": swift.coding_keys,
    "json_defaults": json_defaults.extract,
    "trio_picker_settings": trio.picker_settings,
    "trio_setting_views": trio.setting_views,
}
