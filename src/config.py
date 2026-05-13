"""
Project-level configuration for docu-galaxy-linker.

Reads `.docu-galaxy.toml` from the project root (or a parent directory). CLI
flags always win over the config file; the file's job is to remove the need
to remember --source-base / --render-base / etc on every invocation.

Schema (everything optional):

    docs_dir         = "docs"
    source_base      = "https://github.com/foo/bar/blob/main/docs/"
    render_base      = "https://docs.example.com/"
    redirects_file   = "docs/redirects.txt"     # Sphinx-style mappings
    sphinx_conf      = "docs/conf.py"           # parsed via AST
    codeowners       = ".github/CODEOWNERS"     # auto-detected if omitted
    ignore           = ["**/.venv/**", "reuse/**"]
    known_external_prefixes = ["ubuntu/", "pro/"]  # treat as external, not broken

    [diataxis_prefixes]
    tutorial    = ["tutorial", "tutorials", "getting-started"]
    how-to      = ["how-to", "how-to-guides", "guides"]
    reference   = ["reference", "references"]
    explanation = ["explanation", "explanations"]

    [external_check]
    timeout_seconds = 5
    parallelism     = 8
    cache_ttl_days  = 7

    [ci]
    fail_on_orphan_increase     = 0
    fail_on_broken_doc_increase = 0
    fail_on_broken_lbl_increase = 0
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


CONFIG_FILENAMES = ('.docu-galaxy.toml', 'docu-galaxy.toml')


@dataclass
class ExternalCheckConfig:
    timeout_seconds: float = 5.0
    parallelism:     int   = 8
    cache_ttl_days:  int   = 7


@dataclass
class CIConfig:
    fail_on_orphan_increase:     int = 0
    fail_on_broken_doc_increase: int = 0
    fail_on_broken_lbl_increase: int = 0


@dataclass
class Config:
    """Merged project configuration. All fields are optional."""
    project_root:    Optional[Path] = None
    config_path:     Optional[Path] = None

    docs_dir:        Optional[str] = None
    source_base:     Optional[str] = None
    render_base:     Optional[str] = None
    redirects_file:  Optional[str] = None
    sphinx_conf:     Optional[str] = None
    codeowners:      Optional[str] = None
    ignore:          list[str] = field(default_factory=list)
    known_external_prefixes: list[str] = field(default_factory=list)
    diataxis_prefixes: dict[str, list[str]] = field(default_factory=dict)

    external_check:  ExternalCheckConfig = field(default_factory=ExternalCheckConfig)
    ci:              CIConfig            = field(default_factory=CIConfig)

    @classmethod
    def empty(cls) -> 'Config':
        return cls()


def find_config_file(start: Path) -> Optional[Path]:
    """Walk up from `start` looking for a config file. Returns None if none."""
    start = start.resolve()
    for parent in (start, *start.parents):
        for name in CONFIG_FILENAMES:
            candidate = parent / name
            if candidate.is_file():
                return candidate
    return None


def load_config(start: Optional[Path] = None) -> Config:
    """Load and parse the nearest config file. Returns an empty Config if
    none is found."""
    if start is None:
        start = Path.cwd()
    path = find_config_file(start)
    if not path:
        return Config(project_root=start.resolve())
    try:
        raw = tomllib.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:  # noqa: BLE001
        print(f'WARNING: failed to parse {path}: {exc}', file=sys.stderr)
        return Config(project_root=path.parent, config_path=path)

    cfg = Config(project_root=path.parent, config_path=path)
    cfg.docs_dir       = raw.get('docs_dir')
    cfg.source_base    = raw.get('source_base')
    cfg.render_base    = raw.get('render_base')
    cfg.redirects_file = raw.get('redirects_file')
    cfg.sphinx_conf    = raw.get('sphinx_conf')
    cfg.codeowners     = raw.get('codeowners')
    cfg.ignore                  = list(raw.get('ignore', []))
    cfg.known_external_prefixes = list(raw.get('known_external_prefixes', []))
    cfg.diataxis_prefixes       = dict(raw.get('diataxis_prefixes', {}))

    ec = raw.get('external_check', {})
    if isinstance(ec, dict):
        cfg.external_check = ExternalCheckConfig(
            timeout_seconds=float(ec.get('timeout_seconds', 5)),
            parallelism=int(ec.get('parallelism', 8)),
            cache_ttl_days=int(ec.get('cache_ttl_days', 7)),
        )

    ci = raw.get('ci', {})
    if isinstance(ci, dict):
        cfg.ci = CIConfig(
            fail_on_orphan_increase=int(ci.get('fail_on_orphan_increase', 0)),
            fail_on_broken_doc_increase=int(ci.get('fail_on_broken_doc_increase', 0)),
            fail_on_broken_lbl_increase=int(ci.get('fail_on_broken_lbl_increase', 0)),
        )
    return cfg


def merged(cfg: Config, **cli_overrides: Any) -> Config:
    """Return a copy of cfg with CLI overrides applied (non-None CLI wins)."""
    out = Config(**{**cfg.__dict__})
    for key, val in cli_overrides.items():
        if val is not None and hasattr(out, key):
            setattr(out, key, val)
    return out


# ---------------------------------------------------------------------------
# Redirects (Sphinx / sphinx-reredirects style)
# ---------------------------------------------------------------------------

def load_redirects(path: Path) -> dict[str, str]:
    """Parse a redirects file. Format is either:
        old/path.html new/path.html
    or
        old/path.html new/path.html 301
    Each non-empty, non-comment line is one mapping.
    Returns dict mapping normalised paths (without .html extension) → target.
    """
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        src, dst = parts[0], parts[1]
        out[_normalise_redirect_key(src)] = _normalise_redirect_key(dst)
    return out


def _normalise_redirect_key(p: str) -> str:
    """Drop .html, leading ./ and /."""
    p = p.strip().lstrip('./').lstrip('/')
    for ext in ('.html', '.htm'):
        if p.endswith(ext):
            p = p[: -len(ext)]
            break
    return p


# ---------------------------------------------------------------------------
# Sphinx conf.py (read minimal info via AST, do NOT execute)
# ---------------------------------------------------------------------------

def load_sphinx_conf(path: Path) -> dict[str, Any]:
    """Extract a few well-known names from a Sphinx conf.py using `ast`.

    Today we extract:
      - exclude_patterns: list[str]   (gitignore-style patterns)
      - redirects:        dict[str, str]
    Anything we can't statically evaluate is silently skipped.
    """
    if not path.is_file():
        return {}
    import ast
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except SyntaxError:
        return {}

    wanted = {'exclude_patterns', 'redirects'}
    out: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if not isinstance(tgt, ast.Name) or tgt.id not in wanted:
                continue
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                continue
            out[tgt.id] = value
    return out
