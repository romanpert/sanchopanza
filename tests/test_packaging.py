"""What leaves the repository in a release, checked without building or touching the network.

A PyPI upload cannot be withdrawn, only yanked, and a yanked file stays downloadable. So the
build config is pinned here (review of 2026-09-25): the sdist must not carry the session
handoffs (local paths, sibling repositories, commands that read another project's `.env`)
or the raw agent transcripts under `docs/results/**/runs*/` (thinking-block signatures that
embed a constant identifier), and it must carry the MIT notice of the AgentDojo material it
redistributes. The release workflow is pinned too: actions by commit, least privilege.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
SDIST = PYPROJECT["tool"]["hatch"]["build"]["targets"]["sdist"]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_the_sdist_leaves_out_handoffs_and_raw_transcripts():
    exclude = set(SDIST.get("exclude", []))
    assert "docs/HANDOFF-*.md" in exclude
    assert "docs/results/**/runs/" in exclude
    assert "docs/results/**/runs-*/" in exclude
    assert "benchmarks/**/runs/" in exclude


def test_the_sdist_carries_the_third_party_notices():
    assert "THIRD_PARTY_NOTICES" in SDIST["include"]
    notices = (ROOT / "THIRD_PARTY_NOTICES").read_text(encoding="utf-8")
    assert "AgentDojo" in notices and "MIT License" in notices
    assert "Copyright (c) 2024 Edoardo Debenedetti" in notices
    assert "The above copyright notice and this permission notice shall be included" in notices


def test_install_hints_name_the_distribution_that_is_ours():
    # `sancho` on PyPI belongs to someone else: `pip install sancho[jev]` installs their code.
    stale = re.compile(r"(?<![\w-])sancho\[")
    offenders = [
        f"{path.relative_to(ROOT)}:{n}"
        for path in (ROOT / "src").rglob("*.py")
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if stale.search(line)
    ]
    assert offenders == []


def _uses(workflow: str) -> list[str]:
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    return re.findall(r"^\s*-?\s*uses:\s*(\S+.*)$", text, flags=re.MULTILINE)


def test_every_action_is_pinned_to_a_commit():
    for workflow in ("release.yml", "ci.yml"):
        assert _uses(workflow), workflow
        for use in _uses(workflow):
            pinned = r"[\w.-]+/[\w./-]+@[0-9a-f]{40}\s+#\s*v\d\S*.*"
            assert re.fullmatch(pinned, use), (workflow, use)


def test_the_release_workflow_grants_the_least_it_can():
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    top = text.split("\njobs:", 1)[0]
    assert re.search(r"^permissions:\s*\n\s+contents:\s*read\s*$", top, flags=re.MULTILINE)
    assert text.count("id-token: write") == 1 and text.count("contents: write") == 1
    assert text.count("persist-credentials: false") == text.count("actions/checkout@")
    # the Trusted Publisher is bound to this job's environment name
    assert re.search(r"environment:\s*\n\s+name:\s*pypi\b", text)
    # nothing is built before the checks ran
    for check in ("ruff check", "pytest", "sanchopanza bench"):
        assert text.index(check) < text.index("python -m build")


def test_the_only_console_command_is_sanchopanza():
    # `sancho` is taken on PyPI (a unit-testing framework, 0.11); a second console command
    # of that name would shadow or be shadowed by its install.
    import tomllib

    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "scripts"
    ]
    assert scripts == {"sanchopanza": "sanchopanza.cli:main"}
