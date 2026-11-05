"""The skill taxonomy (skills/data/skills.yaml) and skill mentions in text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from clearhire.skills.matcher import Matcher, make_matcher, native_available
from clearhire.text import fold

__all__ = ["Mention", "Skill", "Taxonomy", "load_taxonomy", "native_available"]

# a list item: the text between line ends, commas, semicolons, colons, slashes, pipes, bullets or brackets
_LIST_ITEM = re.compile(r"[^\n,;:/|•·▪●()\[\]{}]+")
_ITEM_TRIM = " \t-–—*.!?"
_VERSION_SUFFIX = re.compile(r"\s+v?\d+(?:\.\d+)*\+?$")


@dataclass(frozen=True, slots=True)
class Skill:
    id: str
    name: str
    category: str
    aliases: tuple[str, ...]
    strict: tuple[str, ...]
    implies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Mention:
    """A skill named in a text: [start, end) are offsets into that text."""

    skill_id: str
    start: int
    end: int
    alias: str


class Taxonomy:
    def __init__(self, skills: list[Skill], *, native: bool | None = None) -> None:
        self.skills = {skill.id: skill for skill in skills}
        if len(self.skills) != len(skills):
            raise ValueError("duplicate skill ids in the taxonomy")
        patterns: list[str] = []
        prefix: list[bool] = []
        self._pattern_skill: list[str] = []
        owner: dict[tuple[str, bool], str] = {}
        self._strict: dict[str, str] = {}
        for skill in skills:
            unknown = [target for target in skill.implies if target not in self.skills]
            if unknown:
                raise ValueError(f"{skill.id} implies unknown skills: {unknown}")
            for alias in skill.aliases:
                is_prefix = alias.endswith("*")
                pattern = fold(alias.rstrip("*").strip())
                key = (pattern, is_prefix)
                if key in owner and owner[key] != skill.id:
                    raise ValueError(f"alias {alias!r} belongs to both {owner[key]} and {skill.id}")
                if key in owner:
                    continue
                owner[key] = skill.id
                patterns.append(pattern)
                prefix.append(is_prefix)
                self._pattern_skill.append(skill.id)
            for alias in skill.strict:
                if self._strict.get(alias, skill.id) != skill.id:
                    raise ValueError(f"strict alias {alias!r} belongs to two skills")
                self._strict[alias] = skill.id
        self.pattern_count = len(patterns)
        self._matcher: Matcher = make_matcher(patterns, prefix, native=native)

    @classmethod
    def from_yaml(cls, data: str, *, native: bool | None = None) -> Taxonomy:
        document: dict[str, Any] = yaml.safe_load(data)
        skills = [
            Skill(
                id=str(entry["id"]),
                name=str(entry["name"]),
                category=str(entry["cat"]),
                aliases=tuple(str(alias) for alias in entry.get("aka", [])),
                strict=tuple(str(alias) for alias in entry.get("strict", [])),
                implies=tuple(str(target) for target in entry.get("implies", [])),
            )
            for entry in document["skills"]
        ]
        return cls(skills, native=native)

    def find(self, text: str) -> list[Mention]:
        """Every skill mention in `text`, ordered by position."""
        folded = fold(text)
        mentions = [
            Mention(self._pattern_skill[index], start, end, text[start:end])
            for index, start, end in self._matcher.find(folded)
        ]
        mentions.extend(self._find_strict(text))
        mentions.sort(key=lambda m: (m.start, -m.end, m.skill_id))
        return mentions

    def _find_strict(self, text: str) -> list[Mention]:
        found: list[Mention] = []
        if not self._strict:
            return found
        for item in _LIST_ITEM.finditer(text):
            raw = item.group()
            stripped = raw.strip(_ITEM_TRIM)
            stripped = _VERSION_SUFFIX.sub("", stripped)
            skill_id = self._strict.get(stripped)
            if skill_id is None:
                continue
            start = item.start() + raw.index(stripped)
            found.append(Mention(skill_id, start, start + len(stripped), stripped))
        return found

    def skill_ids(self, text: str) -> set[str]:
        return {mention.skill_id for mention in self.find(text)}

    def closure(self, skill_ids: set[str] | frozenset[str]) -> set[str]:
        """The skills plus everything they imply, transitively."""
        result = set(skill_ids)
        stack = list(skill_ids)
        while stack:
            skill = self.skills.get(stack.pop())
            if skill is None:
                continue
            for target in skill.implies:
                if target not in result:
                    result.add(target)
                    stack.append(target)
        return result

    def name(self, skill_id: str) -> str:
        skill = self.skills.get(skill_id)
        return skill.name if skill else skill_id


def default_taxonomy_text() -> str:
    return resources.files("clearhire.skills").joinpath("data/skills.yaml").read_text(encoding="utf-8")


@cache
def load_taxonomy(path: str | None = None) -> Taxonomy:
    data = Path(path).read_text(encoding="utf-8") if path else default_taxonomy_text()
    return Taxonomy.from_yaml(data)
