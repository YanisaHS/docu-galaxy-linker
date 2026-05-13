"""
Parse GitHub-style CODEOWNERS files and answer "who owns this path?".

CODEOWNERS syntax (per GitHub docs):
    # comment
    <gitignore-style pattern>   @owner1 @owner2 @org/team

Rules apply in order; the LAST matching pattern wins. A pattern with no
owners explicitly "unowns" matching paths. Patterns understand a small
gitignore-like subset: `*`, `**`, leading `/`, trailing `/` (directory).
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_LOCATIONS = (
    '.github/CODEOWNERS',
    'CODEOWNERS',
    'docs/CODEOWNERS',
)


@dataclass(frozen=True)
class _Rule:
    raw_pattern: str
    regex: re.Pattern
    owners: tuple[str, ...]
    directory_only: bool


class CodeOwners:
    """A parsed CODEOWNERS file. Use `owners_for(path)` to look up owners."""

    def __init__(self, rules: list[_Rule]) -> None:
        self._rules = rules

    @classmethod
    def from_file(cls, path: Path) -> 'CodeOwners':
        text = path.read_text(encoding='utf-8', errors='replace')
        return cls.from_text(text)

    @classmethod
    def from_text(cls, text: str) -> 'CodeOwners':
        rules: list[_Rule] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            parts = stripped.split()
            pattern = parts[0]
            owners = tuple(p for p in parts[1:] if p.startswith('@') or '@' in p)
            directory_only = pattern.endswith('/')
            if directory_only:
                pattern = pattern.rstrip('/')
            regex = _pattern_to_regex(pattern)
            rules.append(_Rule(
                raw_pattern=parts[0],
                regex=regex,
                owners=owners,
                directory_only=directory_only,
            ))
        return cls(rules)

    def owners_for(self, path: str) -> list[str]:
        """Return the owners for `path`. Empty list if no rule matches.

        Last matching rule wins (matches CODEOWNERS semantics). An empty
        owners tuple unowns the path.
        """
        norm = path.lstrip('./').lstrip('/').replace('\\', '/')
        matched: Optional[_Rule] = None
        for rule in self._rules:
            if rule.regex.match(norm):
                matched = rule
        return list(matched.owners) if matched and matched.owners else []


def _pattern_to_regex(pattern: str) -> re.Pattern:
    """Translate a (gitignore-ish) CODEOWNERS pattern into a regex.

    Supported tokens:
      `**`              → match any number of path segments
      `*`               → match within one path segment
      leading `/`       → anchor at root
      no leading `/`    → match anywhere in path
      trailing `/`      → directory (handled at the rule level)
    """
    p = pattern
    anchored = p.startswith('/')
    if anchored:
        p = p.lstrip('/')

    # Escape regex special chars except for * and /
    out: list[str] = []
    i = 0
    while i < len(p):
        c = p[i]
        if c == '*':
            if i + 1 < len(p) and p[i + 1] == '*':
                # ** → match anything including '/'
                out.append('.*')
                i += 2
                # consume an optional trailing slash
                if i < len(p) and p[i] == '/':
                    i += 1
                continue
            out.append('[^/]*')
            i += 1
            continue
        if c == '/':
            out.append('/')
            i += 1
            continue
        out.append(re.escape(c))
        i += 1

    body = ''.join(out)
    prefix = '^' if anchored else '^(?:.*/)?'
    # Allow trailing path under the pattern (so 'docs/' matches 'docs/foo.md')
    suffix = '(?:$|/.*$)'
    return re.compile(prefix + body + suffix)


def find_codeowners(project_root: Path,
                    override: Optional[str] = None) -> Optional[Path]:
    """Locate a CODEOWNERS file; honour an explicit override first."""
    if override:
        p = Path(override)
        if not p.is_absolute():
            p = project_root / p
        return p if p.is_file() else None
    # Also check the parent dir (docs is often nested under the repo)
    candidates = []
    for base in (project_root, project_root.parent):
        for rel in DEFAULT_LOCATIONS:
            candidates.append(base / rel)
    for c in candidates:
        if c.is_file():
            return c
    return None


def load_codeowners(project_root: Path,
                    override: Optional[str] = None) -> Optional[CodeOwners]:
    path = find_codeowners(project_root, override)
    if path is None:
        return None
    try:
        return CodeOwners.from_file(path)
    except Exception:  # noqa: BLE001
        return None
