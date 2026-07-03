#!/usr/bin/env python3
"""Deterministic spec linter for spec-harden Step 0.
Emits JSON findings for mechanical defects. Exit 0 = clean, 1 = findings."""
import sys, json, re

PLACEHOLDER_RE = re.compile(r'(?<![A-Za-z])(TBD|TODO|FIXME|XXX|\?\?\?)(?![A-Za-z])')


def _finding(sev, lens, loc, issue, suggestion):
    return {"severity": sev, "lens": lens, "location": loc,
            "issue": issue, "suggestion": suggestion}


def _heading_level(line):
    s = line.lstrip()
    if not s.startswith('#'):
        return 0
    return len(s) - len(s.lstrip('#'))


def _fence_flags(lines):
    """True for lines that are inside (or mark) a fenced code block."""
    flags, in_fence = [], False
    for line in lines:
        s = line.lstrip()
        if s.startswith("```") or s.startswith("~~~"):
            flags.append(True)      # the fence marker line itself is code
            in_fence = not in_fence
        else:
            flags.append(in_fence)
    return flags


def lint(text):
    findings = []
    lines = text.splitlines()
    in_code = _fence_flags(lines)

    # 1. placeholder tokens — skip fenced code lines and inline `code` spans
    #    so a spec that DOCUMENTS tokens (e.g. `TBD`) is not falsely flagged.
    for i, line in enumerate(lines, 1):
        if in_code[i - 1]:
            continue
        scan = re.sub(r'`[^`]*`', '  ', line)  # blank inline-code spans
        for m in PLACEHOLDER_RE.finditer(scan):
            findings.append(_finding(
                "major", "completeness", f"line {i}",
                f"Placeholder token '{m.group(0)}' left in spec",
                "Replace with the real decision"))

    # 2. empty sections (heading with no body AND next heading not deeper).
    #    A '#' inside a fenced block is not a heading; fenced code counts as body content.
    headings = [(i, l) for i, l in enumerate(lines)
                if _heading_level(l) > 0 and not in_code[i]]
    for idx, (i, h) in enumerate(headings):
        level = _heading_level(h)
        start = i + 1
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        next_level = _heading_level(lines[end]) if end < len(lines) else 0
        # a parent heading whose next heading is DEEPER is legitimately "empty" of direct body
        if not body and not (next_level > level):
            title = h.strip('# ').strip()
            findings.append(_finding(
                "major", "completeness", f"line {i + 1}",
                f"Section '{title}' has no content",
                "Fill in the section or remove it"))

    # 3. duplicate headings
    seen = {}
    for i, h in headings:
        key = h.strip('# ').strip().lower()
        if key in seen:
            findings.append(_finding(
                "minor", "ambiguity", f"line {i + 1}",
                f"Duplicate heading '{h.strip('# ').strip()}' (also at line {seen[key] + 1})",
                "Rename or merge the duplicate section"))
        else:
            seen[key] = i

    return findings


def main():
    if len(sys.argv) != 2:
        print("usage: lint.py <spec.md>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as fh:
        findings = lint(fh.read())
    print(json.dumps(findings, indent=2, ensure_ascii=False))
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
