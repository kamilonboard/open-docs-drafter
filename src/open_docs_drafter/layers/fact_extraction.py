"""Layer 3: Fact extraction.

Pulls setting names, defaults, ranges, steps, units, JSON keys, on-screen labels and help
text defaults from source files, each with its exact file, line and source text. These
facts are the only place later layers may take numbers and names from.

On failure: a fact that can't be read exactly is kept with value None and a reason, which
later layers treat as "needs human". Nothing is guessed.

Plain code; no AI.
"""

from collections.abc import Iterable, Mapping
from fnmatch import fnmatchcase

from open_docs_drafter.extractors import EXTRACTORS
from open_docs_drafter.facts import Fact, FactChange, FactSet, diff
from open_docs_drafter.profile import Profile

LAYER = 3
AI_INVOLVED = False


def fact_paths(profile: Profile, all_paths: Iterable[str]) -> list[str]:
    """The files in a codebase that the profile's extractors read."""
    patterns = [p for source in profile.facts for p in source.paths]
    return sorted(p for p in all_paths if any(fnmatchcase(p, pat) for pat in patterns))


def extract_facts(profile: Profile, files: Mapping[str, str]) -> FactSet:
    """Run each configured extractor over the files it is set up to read."""
    facts: list[Fact] = []
    for source in profile.facts:
        extractor = EXTRACTORS[source.extractor]
        for path in sorted(files):
            if any(fnmatchcase(path, pattern) for pattern in source.paths):
                facts.extend(extractor(path, files[path]))
    return FactSet(facts)


def fact_changes(
    profile: Profile, base_files: Mapping[str, str], head_files: Mapping[str, str]
) -> list[FactChange]:
    """What a change does to the facts: values added, removed or changed."""
    return diff(extract_facts(profile, base_files), extract_facts(profile, head_files))
