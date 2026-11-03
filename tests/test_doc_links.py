"""Every relative link in the README, changelog and docs/ points to a file that exists.

Links to headings (``file.md#section`` or ``#section``) must also match a heading
in the target file, using GitHub's rule for turning a heading into an anchor.
"""

import os
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "README.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").glob("*.md"))]

# [text](target) and [text](target "title"); images ![alt](target) are matched too.
LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
# [label]: target reference definitions
REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)", re.M)
FENCE = re.compile(r"^(```|~~~).*?^\1", re.M | re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)
EXTERNAL = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)  # http:, https:, mailto:, ...


def _strip_code(text: str) -> str:
    return INLINE_CODE.sub("", FENCE.sub("", text))


def github_anchor(heading: str) -> str:
    """Anchor GitHub gives a heading: lower case, punctuation removed, spaces to hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # keep link text only
    text = re.sub(r"[`*_]", "", text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    seen: dict[str, int] = {}
    out = set()
    for heading in HEADING.findall(_strip_code(path.read_text(encoding="utf-8"))):
        slug = github_anchor(heading)
        n = seen.get(slug, 0)
        out.add(slug if n == 0 else f"{slug}-{n}")
        seen[slug] = n + 1
    out.update(re.findall(r"<a\s+(?:name|id)=\"([^\"]+)\"", path.read_text(encoding="utf-8")))
    return out


def relative_links(path: Path) -> list[str]:
    text = _strip_code(path.read_text(encoding="utf-8"))
    targets = LINK.findall(text) + REF_DEF.findall(text)
    return [t for t in targets if not EXTERNAL.match(t)]


def broken_links(path: Path) -> list[str]:
    problems = []
    for target in relative_links(path):
        file_part, _, anchor = target.partition("#")
        dest = (path.parent / unquote(file_part)).resolve() if file_part else path
        if not dest.exists():
            problems.append(f"{target}: no such file")
        elif anchor and dest.suffix == ".md" and unquote(anchor).lower() not in anchors(dest):
            problems.append(f"{target}: no heading #{anchor} in {os.path.relpath(dest, path.parent)}")
    return problems


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_resolve(doc):
    assert broken_links(doc) == []


def test_docs_have_links_to_check():
    # Guards against the pattern silently matching nothing.
    assert len(relative_links(ROOT / "README.md")) >= 10


def test_checker_catches_broken_links(tmp_path):
    (tmp_path / "other.md").write_text("# Some Section: here\n\n## Repeat\n\n## Repeat\n")
    doc = tmp_path / "doc.md"
    doc.write_text(
        "[ok](other.md) [ok](other.md#some-section-here) [ok](other.md#repeat-1)\n"
        "[ext](https://example.org/missing.md) [mail](mailto:a@b.c)\n"
        "`[code](missing-in-code.md)`\n"
        "```\n[fenced](missing-in-fence.md)\n```\n"
        "[bad](missing.md) [bad](other.md#nope) [bad](#also-nope)\n"
        "[ref]: gone.md\n"
    )
    assert broken_links(doc) == [
        "missing.md: no such file",
        "other.md#nope: no heading #nope in other.md",
        "#also-nope: no heading #also-nope in doc.md",
        "gone.md: no such file",
    ]
