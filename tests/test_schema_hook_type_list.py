"""``@type`` given as a list, in the JSON-LD validation hook.

Schema.org allows ``@type`` to be a single string or an array of strings, and
multi-typed nodes such as ``["Organization", "ProfessionalService"]`` are what
real sites ship. The validator treated ``@type`` as a hashable key, so an array
raised ``TypeError: unhashable type: 'list'`` and the *entire* validation
returned nothing — every placeholder, deprecated and retired check was skipped
for that block. The host hook runner is fail-open, so the failure was silent in
production: no error surfaced, the schema feedback simply disappeared.

The tests below pin both directions: an array of valid types is clean, and the
detections still fire when the offending type sits inside an array.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "validate-schema.py"

TYPE_LIST_VALID = (
    '{"@context":"https://schema.org",'
    '"@type":["Organization","ProfessionalService"],"name":"Example"}'
)
TYPE_LIST_RETIRED = (
    '{"@context":"https://schema.org",'
    '"@type":["Organization","ClaimReview"],"name":"Example"}'
)
TYPE_LIST_PLACEHOLDER = (
    '{"@context":"https://schema.org",'
    '"@type":["LocalBusiness","Organization"],"name":"[Business Name]"}'
)


def _run(tmp_path: Path, filename: str, head: str) -> subprocess.CompletedProcess:
    target = tmp_path / filename
    target.write_text(f"<html><head>{head}</head><body></body></html>", encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(HOOK), str(target)],
        capture_output=True, encoding="utf-8", errors="replace",
    )


def _warnings(result: subprocess.CompletedProcess) -> str:
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def _clean(result: subprocess.CompletedProcess) -> bool:
    return result.returncode == 0 and result.stdout == "" and result.stderr == ""


def test_type_array_with_valid_types_passes(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "page.html",
        f'<script type="application/ld+json">{TYPE_LIST_VALID}</script>',
    )
    assert _clean(result), f"exit={result.returncode} stderr={result.stderr!r}"


def test_retired_type_inside_array_is_reported(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "page.html",
        f'<script type="application/ld+json">{TYPE_LIST_RETIRED}</script>',
    )
    assert result.returncode == 2, result.stderr
    assert "ClaimReview" in result.stderr


def test_placeholder_inside_array_is_reported(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "page.html",
        f'<script type="application/ld+json">{TYPE_LIST_PLACEHOLDER}</script>',
    )
    assert result.returncode == 2, result.stderr
    assert "placeholder" in result.stderr.lower()


def test_non_string_type_values_do_not_crash(tmp_path: Path) -> None:
    """A malformed ``@type`` must degrade, not raise: the hook runs fail-open."""
    result = _run(
        tmp_path,
        "page.html",
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":123,"name":"Example"}'
        "</script>",
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
