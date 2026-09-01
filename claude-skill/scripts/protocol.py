#!/usr/bin/env python3
"""spec-harden protocol helpers: parse critique files, headers, STATUS.md, convergence."""
import sys, os, re, json

SEVERITIES = {"blocker", "major", "minor", "nit"}
# "design" is used only in --depth design (challenge-the-approach) mode; harmless elsewhere.
LENSES = {"completeness", "testability", "ambiguity", "assumptions", "scope", "design"}

_FIND_RE = re.compile(
    r'\[SEVERITY:\s*(?P<sev>[^\]]+)\]\s*\n'
    r'LENS:\s*(?P<lens>[^\n]+)\n'
    r'LOCATION:\s*(?P<loc>[^\n]+)\n'
    r'ISSUE:\s*(?P<issue>[^\n]+)\n'
    r'SUGGESTION:\s*(?P<sug>[^\n]+)',
    re.MULTILINE)


def parse_findings(text):
    findings, errors = [], []
    for m in _FIND_RE.finditer(text):
        sev = m.group("sev").strip().lower()
        lens = m.group("lens").strip().lower()
        findings.append({
            "severity": sev, "lens": lens,
            "location": m.group("loc").strip(),
            "issue": m.group("issue").strip(),
            "suggestion": m.group("sug").strip(),
        })
        if sev not in SEVERITIES:
            errors.append(f"bad severity: {sev}")
        if lens not in LENSES:
            errors.append(f"bad lens: {lens}")
    n_markers = text.count("[SEVERITY")
    if n_markers != len(findings):
        errors.append(f"{n_markers} SEVERITY markers but parsed {len(findings)} block(s) — malformed")
    return findings, errors


def parse_header(text):
    h = {}
    for key in ("ROUND", "AUTHOR", "READS", "VERDICT", "OPEN_BLOCKERS", "OPEN_MAJORS"):
        m = re.search(rf'^{key}:\s*(.+)$', text, re.MULTILINE)
        if m:
            h[key] = m.group(1).strip()
    return h


def is_converged(text):
    h = parse_header(text)
    try:
        ob = int(h.get("OPEN_BLOCKERS", "1"))
        om = int(h.get("OPEN_MAJORS", "1"))
    except ValueError:
        return False
    return h.get("VERDICT", "").lower() == "converged" and ob == 0 and om == 0


def read_status(d):
    p = os.path.join(d, "STATUS.md")
    s = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if ":" in line:
                    k, v = line.split(":", 1)
                    s[k.strip().lower()] = v.strip()
    return s


def write_status(d, turn, round_, converged, target_spec_path=None):
    # preserve an existing target_spec_path when the caller doesn't pass one
    if target_spec_path is None:
        target_spec_path = read_status(d).get("target_spec_path")
    lines = [f"turn: {turn}", f"round: {round_}", f"converged: {str(converged).lower()}"]
    if target_spec_path:
        lines.append(f"target_spec_path: {target_spec_path}")
    with open(os.path.join(d, "STATUS.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


FINALIZATION_BASES = ("protocol-clean", "author-judgment", "cap-hit")


def mark_finalized(d, basis):
    """Stamp a run terminal so dispatch never re-loops it. Basis records HOW it ended."""
    if basis not in FINALIZATION_BASES:
        raise ValueError("basis must be one of %s" % (FINALIZATION_BASES,))
    s = read_status(d)
    s["finalized"] = "true"
    s["finalization_basis"] = basis
    order = ["turn", "round", "converged", "finalized", "finalization_basis", "target_spec_path"]
    lines = [f"{k}: {s[k]}" for k in order if k in s]
    lines += [f"{k}: {v}" for k, v in s.items() if k not in order]
    with open(os.path.join(d, "STATUS.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def summary_check(d):
    """Return a list of missing required SUMMARY.md pieces (empty = OK). Enforces the
    finalize contract mechanically instead of trusting the author to remember it."""
    p = os.path.join(d, "SUMMARY.md")
    if not os.path.exists(p):
        return ["SUMMARY.md is missing"]
    t = open(p, encoding="utf-8").read().lower()
    missing = []
    if "basis" not in t:
        missing.append("finalization basis line (protocol-clean | author-judgment | cap-hit)")
    if "spec quality only" not in t:
        missing.append("closing caveat line ('... spec quality only, not implementation correctness ...')")
    return missing


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "findings":
        with open(sys.argv[2], encoding="utf-8") as fh:
            f, e = parse_findings(fh.read())
        print(json.dumps({"findings": f, "errors": e}, indent=2, ensure_ascii=False))
        sys.exit(1 if e else 0)
    elif cmd == "converged":
        with open(sys.argv[2], encoding="utf-8") as fh:
            sys.exit(0 if is_converged(fh.read()) else 1)
    elif cmd == "status-read":
        print(json.dumps(read_status(sys.argv[2]), ensure_ascii=False))
    elif cmd == "status-write":
        # status-write <dir> <turn> <round> <converged> [target_spec_path]
        tsp = sys.argv[6] if len(sys.argv) > 6 else None
        write_status(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], tsp)
    elif cmd == "finalize-status":
        # finalize-status <dir> <protocol-clean|author-judgment|cap-hit>
        try:
            mark_finalized(sys.argv[2], sys.argv[3])
        except ValueError as e:
            print(e, file=sys.stderr)
            sys.exit(2)
    elif cmd == "summary-check":
        # summary-check <dir> — exit 1 (and list) if the SUMMARY is missing required pieces
        missing = summary_check(sys.argv[2])
        if missing:
            print("\n".join("missing: " + m for m in missing))
            sys.exit(1)
    else:
        print("usage: protocol.py findings|converged|status-read|status-write|"
              "finalize-status|summary-check ...", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
