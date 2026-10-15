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
# What follows "## <version>" in a dated CHANGELOG heading, as release.yml extracts it.
NOTES_TAIL = r" \(\d{4}-\d{2}-\d{2}\)\n(.*?)(?=^## |\Z)"


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


def _job(text: str, name: str) -> str:
    """The block of one job in a workflow, up to the next job or the end."""
    match = re.search(rf"^  {name}:\n(.*?)(?=^  \S|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(1)


def test_a_tag_push_never_publishes_to_pypi():
    # Pushing a v* tag cuts the GitHub release; PyPI only by hand (workflow_dispatch on the
    # tag), because the `pypi` environment admits v* tags with no required reviewer.
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    on = text.split("\npermissions:", 1)[0]
    assert "workflow_dispatch:" in on and re.search(r"tags:\s*\n\s+- \"v\*\.\*\.\*\"", on)
    pypi = _job(text, "publish-pypi")
    assert "github.event_name == 'workflow_dispatch'" in pypi
    assert "startsWith(github.ref, 'refs/tags/v')" in pypi
    release = _job(text, "github-release")
    assert "github.event_name == 'push'" in release and "publish-pypi" not in release


def test_the_github_release_carries_the_changelog_section_of_its_tag():
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    build, release = _job(text, "build"), _job(text, "github-release")
    assert "release-notes.md" in build and "CHANGELOG.md" in build
    assert "body_path: release-notes.md" in release
    assert "generate_release_notes: true" not in release


def test_the_changelog_section_for_the_version_is_dated_before_a_tag():
    # The workflow refuses a tag whose CHANGELOG section still says "unreleased"; this is the
    # same extraction, run here on a dated section.
    sample = "# Changelog\n\n## 9.9.9 (2026-10-15)\n\nNotes.\n\n## 9.9.8 (2026-01-01)\n\nOld.\n"
    pattern = r"^## " + re.escape("9.9.9") + NOTES_TAIL
    match = re.search(pattern, sample, re.M | re.S)
    assert match and match.group(1).strip() == "Notes."
    assert not re.search(pattern, sample.replace("(2026-10-15)", "(unreleased)"), re.M | re.S)
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert f'NOTES_TAIL = r"{NOTES_TAIL}"' in text


def test_the_changelog_has_a_section_for_the_package_version_that_fits_a_release():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = rf"^## {re.escape(version)} \((unreleased|\d{{4}}-\d{{2}}-\d{{2}})\)$"
    assert re.search(heading, text, re.M), version
    match = re.search(r"^## " + re.escape(version) + NOTES_TAIL, text, re.M | re.S)
    if match:  # dated: the GitHub release body takes at most 125,000 characters
        assert len(match.group(1).strip()) < 125_000


def test_the_only_console_command_is_sanchopanza():
    # `sancho` is taken on PyPI (a unit-testing framework, 0.11); a second console command
    # of that name would shadow or be shadowed by its install.
    import tomllib

    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "scripts"
    ]
    assert scripts == {"sanchopanza": "sanchopanza.cli:main"}
