"""
Code-based evaluators for the Draft Brief output.

REVISION HISTORY / IMPORTANT CONTEXT: the first version of this file was
designed against exactly one real sample (sample_brief_hp01.txt, execution
153), which happened to use footnote-style citations ([^label] / [^label]:
url) and the exact header phrase "Competitive Comparison". Running it against
the real 40-case baseline exposed that this was NOT representative -- the
agent's output format varies noticeably run to run:
    - hp01: footnote-style citations; header "## 2. Competitive Comparison"
    - hp02: inline URLs in 【...】 brackets, no footnotes; header
      "## 2. Competitor Comparison"
    - ec10: 【sourceN】 markers referencing a separate numbered "**Sources**:"
      list at the bottom; header "## 2. Competitive Landscape (...)"
This inconsistency in the agent's own output format is itself a real finding
worth flagging for Phase 3 (a reliable brief generator probably shouldn't
vary citation style and headers run to run) -- but the evaluators below were
rewritten to be format-tolerant so they measure actual content quality
instead of penalizing valid-but-differently-formatted output.

Two evaluators, matching the eval plan's "code-based checks for structural
completeness and citation presence":
    - check_structural_completeness(text)
    - check_citation_presence(text)

Each returns a dict: {"passed": bool, "score": float 0-1, "details": {...}}
so results can be aggregated numerically or inspected case by case.
"""

import re

# Section keywords matched loosely against markdown header LINES (lines
# starting with 1-4 "#" characters), not the exact surrounding phrase --
# tolerant of "Competitor Comparison" / "Competitive Comparison" /
# "Competitive Landscape", "Key Gaps" / "Gaps & Opportunities", etc.
REQUIRED_SECTIONS = [
    ("executive_summary", r"executive\s+summary"),
    ("competitor_section", r"competit\w*"),  # Comparison / Landscape / Analysis / etc.
    ("key_gaps", r"key\s+gaps|gaps?\s*(&|and)?\s*opportunit"),
    ("recommendation", r"recommendation"),
]

HEADER_LINE_RE = re.compile(r"^\s{0,3}#{1,4}[^\n]*$", re.MULTILINE)

# A markdown table row: at least 2 pipe characters with content between them.
TABLE_ROW_RE = re.compile(r"^\s*\|.+\|.+\|.*$", re.MULTILINE)
# The header/separator row of a markdown table, e.g. |---|---|---|
TABLE_SEP_RE = re.compile(r"^\s*\|[\s:-]+\|[\s:-]+\|", re.MULTILINE)

# All observed citation marker styles across real runs (expanded Sept 7
# evening after diagnosing 3 real failing cases -- hp07, hp02, kf03 -- which
# surfaced two more real styles the original 3 patterns didn't cover:
#   [^label]          -- markdown footnote reference
#   【anything】        -- CJK-bracket inline marker (raw URL OR a source label
#                          like "source1", both seen in real data)
#   [1], [12]          -- plain numeric bracket reference NOT followed by "("
#                          (to avoid conflating with a markdown link)
#   [1](https://...)   -- numbered markdown-link citation with a real URL
#                          (seen in hp07's Sources line) -- counts as a valid
#                          marker only when the href is non-empty; see
#                          BROKEN_CITATION_RE below for the empty-href case,
#                          which is a real agent bug, not a formatting choice.
#   <https://...>      -- angle-bracket-wrapped raw URL (seen throughout
#                          kf03, both in its Sources list and inline in Key
#                          Gaps table cells)
FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]]+)\](?!:)")
CJK_BRACKET_RE = re.compile(r"【([^】]+)】")
NUMERIC_BRACKET_RE = re.compile(r"(?<!\[)\[(\d{1,3})\](?!\()")  # avoid matching markdown links [text](url)
MARKDOWN_LINK_CITATION_RE = re.compile(r"\[(\d{1,3})\]\((https?://[^\s)]+)\)")
ANGLE_URL_RE = re.compile(r"<(https?://[^\s>]+)>")

# NOT a valid marker -- a numbered citation with an EMPTY href, e.g. "[1]()".
# Seen in hp07's Sources line ("Dating After Divorce [1](), ..."): the agent
# fabricates the visual appearance of a citation without an actual source.
# This is worse than no citation at all (looks sourced, isn't) and is
# tracked separately in check_citation_presence's details as a real,
# agent-side content bug -- not something loosening the regex should paper
# over.
BROKEN_CITATION_RE = re.compile(r"\[(\d{1,3})\]\(\s*\)")

URL_RE = re.compile(r"https?://\S+")


def extract_brief_text(stage_output) -> str:
    """
    Normalizes whatever shape the Draft Brief stage's output list came in
    (see harness.extract_node_runs -- a list of {"text": "..."} dicts in the
    real data we've seen) into a single string of the brief's markdown.
    """
    if stage_output is None:
        return ""
    if isinstance(stage_output, str):
        return stage_output
    if isinstance(stage_output, list):
        parts = []
        for item in stage_output:
            if isinstance(item, dict):
                parts.append(item.get("text") or item.get("output") or "")
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(p for p in parts if p)
    return str(stage_output)


def check_structural_completeness(text: str) -> dict:
    """
    Code-based check (pass bar: 100% -- every case must have all 4 sections
    plus a real comparison table, per the eval plan's structural-completeness
    metric). Section keywords are matched against header lines only (lines
    starting with markdown "#"), tolerant of the header wording varying
    between runs (see module docstring).
    """
    header_lines = "\n".join(HEADER_LINE_RE.findall(text)).lower()
    # Fall back to scanning the whole document if no "#" headers were found
    # at all (defensive -- every real sample so far has had them).
    haystack = header_lines if header_lines.strip() else text.lower()

    section_found = {}
    for key, pattern in REQUIRED_SECTIONS:
        section_found[key] = bool(re.search(pattern, haystack))

    has_table_row = bool(TABLE_ROW_RE.search(text))
    has_table_sep = bool(TABLE_SEP_RE.search(text))
    has_comparison_table = has_table_row and has_table_sep

    all_sections_present = all(section_found.values())
    passed = all_sections_present and has_comparison_table

    n_checks = len(REQUIRED_SECTIONS) + 1  # +1 for the table
    n_passed = sum(section_found.values()) + (1 if has_comparison_table else 0)

    return {
        "passed": passed,
        "score": n_passed / n_checks,
        "details": {
            **{f"has_{k}": v for k, v in section_found.items()},
            "has_comparison_table": has_comparison_table,
        },
    }


def check_citation_presence(text: str, min_citations: int = 1) -> dict:
    """
    Code-based check (format-tolerant across the 3 citation styles observed
    in real baseline data -- see module docstring). Rather than requiring one
    specific marker-to-definition resolution scheme (which doesn't
    generalize across the agent's varying output format), this checks two
    more fundamental things:
        1. Are there actual URLs present anywhere in the brief (real
           evidence of sourcing, regardless of how they're formatted)?
        2. Are those URLs actually attached to the brief via SOME recognized
           inline citation marker (footnote, CJK-bracket, or numeric-bracket
           style) -- i.e. not just a brief that happens to mention a URL in
           passing with no citation apparatus at all?
    """
    urls = set(URL_RE.findall(text))

    footnote_refs = FOOTNOTE_REF_RE.findall(text)
    cjk_refs = CJK_BRACKET_RE.findall(text)
    numeric_refs = NUMERIC_BRACKET_RE.findall(text)
    markdown_link_refs = MARKDOWN_LINK_CITATION_RE.findall(text)  # [(num, url), ...]
    angle_url_refs = ANGLE_URL_RE.findall(text)
    broken_refs = BROKEN_CITATION_RE.findall(text)  # empty-href "[N]()" -- flagged, not counted

    n_inline_markers = (
        len(footnote_refs) + len(cjk_refs) + len(numeric_refs)
        + len(markdown_link_refs) + len(angle_url_refs)
    )

    has_min_citations = len(urls) >= min_citations
    has_inline_markers = n_inline_markers >= min_citations

    passed = has_min_citations and has_inline_markers

    n_checks = 2
    n_passed = sum([has_min_citations, has_inline_markers])

    return {
        "passed": passed,
        "score": n_passed / n_checks,
        "details": {
            "n_urls": len(urls),
            "n_footnote_refs": len(set(footnote_refs)),
            "n_cjk_bracket_refs": len(set(cjk_refs)),
            "n_numeric_bracket_refs": len(set(numeric_refs)),
            "n_markdown_link_refs": len(set(markdown_link_refs)),
            "n_angle_url_refs": len(set(angle_url_refs)),
            "n_broken_empty_href_citations": len(broken_refs),
        },
    }


if __name__ == "__main__":
    # Quick self-test against real samples, if present in this folder.
    import sys
    import json

    paths = sys.argv[1:] if len(sys.argv) > 1 else [
        "sample_brief_hp01.txt", "sample_brief_hp02.txt", "sample_brief_ec10.txt",
    ]
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            print(f"(skipping {path} -- not found)")
            continue
        text = extract_brief_text(raw)
        print(f"=== {path} ===")
        print("Structural completeness:", json.dumps(check_structural_completeness(text)))
        print("Citation presence:      ", json.dumps(check_citation_presence(text)))
        print()
