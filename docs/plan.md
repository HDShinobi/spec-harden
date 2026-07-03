# spec-harden Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `spec-harden` — a cross-tool adversarial spec-review loop where Claude (author) and Gemini-in-Antigravity (primary critic) exchange files in a `harden/` folder until no new blocker/major finding remains, then Claude promotes the hardened draft to the real spec on user confirmation.

**Architecture:** Source-of-truth lives in-repo at `tools/spec-harden/`; deployed by a symlink installer to `~/.claude/skills/spec-harden` (Claude author skill) and `<repo>/.agents/skills/spec-harden` (Gemini critic skill). Two stdlib-only Python helpers give the loop its deterministic, testable core: `lint.py` (mechanical spec defects) and `protocol.py` (parse critique files / STATUS.md / convergence). The `SKILL.md` files and `PROTOCOL.md` are prose contracts verified by dry-runs and a parser round-trip.

**Tech Stack:** Python 3 (stdlib only — `unittest`, `re`, `json`), Bash (installer), Markdown (skills + protocol). No third-party dependencies.

## Global Constraints

- Critic must be a **different model family** than the author where possible: **Gemini = primary critic** (leads the loop, run manually in Antigravity); a **fresh Claude subagent = secondary critic** (auto pre-pass only, model chosen via `--critic-model {opus|sonnet|haiku|fable}`; omitting the flag skips the pre-pass).
- **Real spec is NEVER edited during the loop.** All debate happens on `draft.md`; the real spec is overwritten only in `finalize`, on explicit user confirmation.
- Severity tiers: `blocker`, `major` (both block convergence), `minor`, `nit` (logged only).
- Five review lenses: `completeness`, `testability`, `ambiguity`, `assumptions`, `scope`.
- Convergence = a Gemini round with `OPEN_BLOCKERS: 0` and `OPEN_MAJORS: 0` AND no newly-accepted blocker/major that round. Circuit-breaker: same blocker/major recurring 2 rounds unresolved → stop for user arbitration. `MAX_ROUNDS = 4` hard cap (hitting it with open majors is NOT "converged" — surface them).
- Calibration guards in every critic prompt: **anti-perfectionism** (a low/no-finding round is a valid convergence signal — do not invent blockers) and **high-confidence bias** (only raise blocker/major when confident).
- Python helpers: stdlib only, no external deps. Both tools must be able to run them with `python3`.
- Finding block format (exact, machine-parseable):
  ```
  [SEVERITY: blocker|major|minor|nit]
  LENS: completeness|testability|ambiguity|assumptions|scope
  LOCATION: <section / quote>
  ISSUE: <what is wrong or missing>
  SUGGESTION: <concrete fix>
  ```
- File header (exact) on every `rN.*.md` exchange file:
  ```
  ROUND: <int>
  AUTHOR: gemini | claude
  READS: <files this response is based on>
  VERDICT: needs-work | converged
  OPEN_BLOCKERS: <int>
  OPEN_MAJORS: <int>
  ```

**Spec:** `docs/superpowers/specs/2026-07-01-spec-harden-design.md`

## File Structure

```
tools/spec-harden/
  claude-skill/
    SKILL.md                 # Claude author/orchestrator (init/respond/finalize)
    scripts/lint.py          # deterministic spec linter (Step 0)
    scripts/protocol.py      # parse findings / header / STATUS.md / convergence
    references/PROTOCOL.md    # shared contract (copied into each project's harden/ on init)
  gemini-skill/
    SKILL.md                 # Gemini/Antigravity critic
  tests/
    test_lint.py             # unittest for lint.py
    test_protocol.py         # unittest for protocol.py
  install.sh                 # symlink deploy + CLAUDE.md hook
```

Deployed by `install.sh`:
- `~/.claude/skills/spec-harden`      → symlink → `tools/spec-harden/claude-skill`
- `<repo>/.agents/skills/spec-harden` → symlink → `tools/spec-harden/gemini-skill`
- append the auto-hook rule to `~/.claude/CLAUDE.md`

Run tests with: `python3 tools/spec-harden/tests/test_lint.py -v` and `python3 tools/spec-harden/tests/test_protocol.py -v`.

---

### Task 1: Deterministic spec linter (`lint.py`)

**Files:**
- Create: `tools/spec-harden/claude-skill/scripts/lint.py`
- Test: `tools/spec-harden/tests/test_lint.py`

**Interfaces:**
- Produces: module `lint` with `lint(text: str) -> list[dict]` (each dict: `severity, lens, location, issue, suggestion`); CLI `python3 lint.py <spec.md>` prints JSON list, exits `0` if clean else `1`.
- Detects: placeholder tokens (`TBD|TODO|FIXME|XXX|???`), truly-empty sections (heading with no body and next heading not deeper), duplicate headings. Does NOT check links (out of scope — path resolution is error-prone).

- [ ] **Step 1: Write the failing test**

`tools/spec-harden/tests/test_lint.py`:
```python
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "claude-skill", "scripts"))
import lint

class TestLint(unittest.TestCase):
    def test_placeholder_detected(self):
        f = lint.lint("# Spec\n\nThe timeout is TBD seconds.\n")
        self.assertTrue(any("TBD" in x["issue"] and x["severity"] == "major" for x in f))

    def test_todo_and_qqq_detected(self):
        f = lint.lint("# S\n\nTODO: decide.\n\n## X\n\n???\n")
        issues = " ".join(x["issue"] for x in f)
        self.assertIn("TODO", issues)
        self.assertIn("???", issues)

    def test_empty_section_detected(self):
        # "## Empty" has no body and is followed by a same-level heading
        f = lint.lint("# Spec\n\nbody\n\n## Empty\n\n## Next\n\nmore\n")
        self.assertTrue(any("Empty" in x["issue"] and x["severity"] == "major" for x in f))

    def test_parent_heading_with_subsections_not_flagged(self):
        # "# Parent" has no direct body but a deeper "## Child" follows — legitimate
        f = lint.lint("# Parent\n\n## Child\n\nreal content here\n")
        self.assertFalse(any("Parent" in x["issue"] for x in f))

    def test_duplicate_heading(self):
        f = lint.lint("# Spec\n\na\n\n## Design\n\nx\n\n## Design\n\ny\n")
        self.assertTrue(any("Duplicate" in x["issue"] for x in f))

    def test_clean_spec_no_findings(self):
        clean = "# Spec\n\nThe timeout is 30 seconds.\n\n## Design\n\nConcrete detail.\n"
        self.assertEqual(lint.lint(clean), [])

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tools/spec-harden/tests/test_lint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lint'`.

- [ ] **Step 3: Write minimal implementation**

`tools/spec-harden/claude-skill/scripts/lint.py`:
```python
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


def lint(text):
    findings = []
    lines = text.splitlines()

    # 1. placeholder tokens
    for i, line in enumerate(lines, 1):
        for m in PLACEHOLDER_RE.finditer(line):
            findings.append(_finding(
                "major", "completeness", f"line {i}",
                f"Placeholder token '{m.group(0)}' left in spec",
                "Replace with the real decision"))

    # 2. empty sections (heading with no body AND next heading not deeper)
    headings = [(i, l) for i, l in enumerate(lines) if _heading_level(l) > 0]
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tools/spec-harden/tests/test_lint.py -v`
Expected: PASS (6 tests OK).

- [ ] **Step 5: Commit**

```bash
git add tools/spec-harden/claude-skill/scripts/lint.py tools/spec-harden/tests/test_lint.py
git commit -m "feat(spec-harden): deterministic spec linter (Step 0)"
```

---

### Task 2: Protocol helper (`protocol.py`)

**Files:**
- Create: `tools/spec-harden/claude-skill/scripts/protocol.py`
- Test: `tools/spec-harden/tests/test_protocol.py`

**Interfaces:**
- Produces:
  - `parse_findings(text) -> (list[dict], list[str])` — findings + error strings (bad severity/lens, unparsed `[SEVERITY` blocks).
  - `parse_header(text) -> dict` — keys `ROUND, AUTHOR, READS, VERDICT, OPEN_BLOCKERS, OPEN_MAJORS`.
  - `is_converged(text) -> bool` — `VERDICT==converged` and `OPEN_BLOCKERS==0` and `OPEN_MAJORS==0`.
  - `read_status(dir) -> dict`, `write_status(dir, turn, round_, converged)`.
  - CLI: `protocol.py findings <file>` (JSON `{findings, errors}`, exit 1 if errors), `protocol.py converged <file>` (exit 0 if converged), `protocol.py status-read <dir>`, `protocol.py status-write <dir> <turn> <round> <converged>`.

- [ ] **Step 1: Write the failing test**

`tools/spec-harden/tests/test_protocol.py`:
```python
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "claude-skill", "scripts"))
import protocol

ONE = """ROUND: 1
AUTHOR: gemini
READS: draft.md
VERDICT: needs-work
OPEN_BLOCKERS: 1
OPEN_MAJORS: 0

[SEVERITY: blocker]
LENS: completeness
LOCATION: Section 2
ISSUE: No error handling defined
SUGGESTION: Specify retry behavior
"""

TWO = ONE + """
[SEVERITY: minor]
LENS: ambiguity
LOCATION: intro
ISSUE: term 'fast' undefined
SUGGESTION: quantify it
"""

CONVERGED = """ROUND: 3
AUTHOR: gemini
READS: draft.md
VERDICT: converged
OPEN_BLOCKERS: 0
OPEN_MAJORS: 0
"""

class TestProtocol(unittest.TestCase):
    def test_parse_single_finding(self):
        f, e = protocol.parse_findings(ONE)
        self.assertEqual(len(f), 1)
        self.assertEqual(e, [])
        self.assertEqual(f[0]["severity"], "blocker")
        self.assertEqual(f[0]["lens"], "completeness")
        self.assertEqual(f[0]["issue"], "No error handling defined")

    def test_parse_multiple_findings(self):
        f, e = protocol.parse_findings(TWO)
        self.assertEqual(len(f), 2)
        self.assertEqual(e, [])

    def test_malformed_block_reports_error(self):
        bad = "[SEVERITY: blocker]\nLENS: completeness\n(missing LOCATION/ISSUE/SUGGESTION)\n"
        f, e = protocol.parse_findings(bad)
        self.assertTrue(e)  # markers != parsed

    def test_bad_severity_error(self):
        bad = ONE.replace("[SEVERITY: blocker]", "[SEVERITY: critical]")
        f, e = protocol.parse_findings(bad)
        self.assertTrue(any("severity" in x for x in e))

    def test_is_converged(self):
        self.assertTrue(protocol.is_converged(CONVERGED))
        self.assertFalse(protocol.is_converged(ONE))

    def test_status_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            protocol.write_status(d, "gemini", 2, False)
            s = protocol.read_status(d)
            self.assertEqual(s["turn"], "gemini")
            self.assertEqual(s["round"], "2")
            self.assertEqual(s["converged"], "false")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tools/spec-harden/tests/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'protocol'`.

- [ ] **Step 3: Write minimal implementation**

`tools/spec-harden/claude-skill/scripts/protocol.py`:
```python
#!/usr/bin/env python3
"""spec-harden protocol helpers: parse critique files, headers, STATUS.md, convergence."""
import sys, os, re, json

SEVERITIES = {"blocker", "major", "minor", "nit"}
LENSES = {"completeness", "testability", "ambiguity", "assumptions", "scope"}

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


def write_status(d, turn, round_, converged):
    with open(os.path.join(d, "STATUS.md"), "w", encoding="utf-8") as fh:
        fh.write(f"turn: {turn}\nround: {round_}\nconverged: {str(converged).lower()}\n")


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
        write_status(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    else:
        print("usage: protocol.py findings|converged|status-read|status-write ...", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tools/spec-harden/tests/test_protocol.py -v`
Expected: PASS (6 tests OK).

- [ ] **Step 5: Commit**

```bash
git add tools/spec-harden/claude-skill/scripts/protocol.py tools/spec-harden/tests/test_protocol.py
git commit -m "feat(spec-harden): protocol parser (findings/header/status/convergence)"
```

---

### Task 3: Shared contract (`PROTOCOL.md`)

**Files:**
- Create: `tools/spec-harden/claude-skill/references/PROTOCOL.md`

**Interfaces:**
- Consumes: the finding-block + header formats from Global Constraints; must be parseable by `protocol.py` (Task 2).
- Produces: the single contract both skills reference; `init` copies it into each project's `harden/` folder.

- [ ] **Step 1: Write `PROTOCOL.md`**

`tools/spec-harden/claude-skill/references/PROTOCOL.md`:
````markdown
# spec-harden PROTOCOL

Two tools that cannot see each other's context coordinate ONLY through the files
in this `harden/` folder. Obey this contract exactly.

## Roles
- **Author (Claude Code):** owns `draft.md`; adjudicates each finding ACCEPT (edit
  the draft) or REBUT (record a reason); never accepts blindly. Writes `rN.claude.md`.
- **Primary critic (Gemini, in Antigravity):** reads `draft.md` + latest `rN.claude.md`;
  writes findings to `rN.gemini.md`. NEVER edits `draft.md`.
- **Secondary critic (Claude subagent):** one automatic pre-pass at `init`; logs
  `r0.claude-critic.md`. Same-family, so it supplements — never replaces — Gemini.
- **Driver (user):** alternates the two tools; makes the final confirm.

## Folder layout
```
<name>.harden/
  PROTOCOL.md        # this file (copied by init)
  draft.md           # working draft — Author edits; real spec untouched until finalize
  r0.claude-critic.md# optional secondary-critic pre-pass log
  rN.gemini.md       # round N critic findings (Gemini)
  rN.claude.md       # round N author adjudication (Claude)
  STATUS.md          # turn/round/converged
  SUMMARY.md         # written at finalize
```

## File header (every rN.*.md)
```
ROUND: <int>
AUTHOR: gemini | claude
READS: <files this is based on>
VERDICT: needs-work | converged
OPEN_BLOCKERS: <int>
OPEN_MAJORS: <int>
```

## Finding block (repeat per finding, under the header)
```
[SEVERITY: blocker|major|minor|nit]
LENS: completeness|testability|ambiguity|assumptions|scope
LOCATION: <section / quote>
ISSUE: <what is wrong or missing>
SUGGESTION: <concrete fix>
```

## Severity
- `blocker` — unimplementable / self-contradictory / missing a core decision. Blocks convergence.
- `major` — real gap or wrong assumption that would cause rework. Blocks convergence.
- `minor` — safe-to-resolve ambiguity/omission. Logged, does not block.
- `nit` — style/wording. Logged, does not block.

## Five lenses
Completeness · Testability · Ambiguity · Assumptions · Scope.

## Critic guards (both critics)
- **Anti-perfectionism:** a low/no-finding round is a legitimate convergence signal.
  Do NOT invent blockers to look thorough.
- **High-confidence bias:** only raise blocker/major when confident; uncertain → minor/nit.
- Only raise NEW or still-unaddressed issues vs prior rounds.

## Convergence
Converged when a Gemini round reports `OPEN_BLOCKERS: 0` and `OPEN_MAJORS: 0` AND the
prior Author round accepted no new blocker/major.
- **Circuit-breaker:** if the same blocker/major recurs across two rounds unresolved
  (Author REBUT vs critic re-raise, or an ACCEPTed fix still fails), STOP and surface it
  to the user to arbitrate.
- **Cap:** `MAX_ROUNDS = 4`. Hitting the cap with open majors is NOT convergence — report
  the unresolved majors to the user; never present as "clean".
````

- [ ] **Step 2: Verify the embedded finding block parses**

Run:
```bash
python3 - <<'PY'
import sys; sys.path.insert(0, "tools/spec-harden/claude-skill/scripts")
import protocol
sample = """ROUND: 1
AUTHOR: gemini
READS: draft.md
VERDICT: needs-work
OPEN_BLOCKERS: 1
OPEN_MAJORS: 0

[SEVERITY: blocker]
LENS: completeness
LOCATION: Section 2
ISSUE: No error handling defined
SUGGESTION: Specify retry behavior
"""
f, e = protocol.parse_findings(sample)
assert len(f) == 1 and not e, (f, e)
assert protocol.parse_header(sample)["ROUND"] == "1"
print("PROTOCOL sample parses OK")
PY
```
Expected: `PROTOCOL sample parses OK`.

- [ ] **Step 3: Commit**

```bash
git add tools/spec-harden/claude-skill/references/PROTOCOL.md
git commit -m "docs(spec-harden): shared PROTOCOL contract"
```

---

### Task 4: Claude author skill (`claude-skill/SKILL.md`)

**Files:**
- Create: `tools/spec-harden/claude-skill/SKILL.md`

**Interfaces:**
- Consumes: `scripts/lint.py`, `scripts/protocol.py`, `references/PROTOCOL.md` (Tasks 1–3); the Agent tool (secondary Claude critic).
- Produces: the orchestrator instructions with three phases — `init`, `respond`, `finalize`.

- [ ] **Step 1: Write `SKILL.md`**

`tools/spec-harden/claude-skill/SKILL.md`:
````markdown
---
name: spec-harden
description: Harden a written spec via a cross-tool adversarial review loop — Gemini (run manually in Antigravity) as primary critic plus an automatic Claude-subagent secondary critic — exchanging files in a `<name>.harden/` folder until no new blocker/major finding remains, then promote the hardened draft to the real spec on user confirmation. Use after brainstorming writes a spec, or on any existing spec document. Accepts an optional spec path and `--critic-model {opus|sonnet|haiku|fable}`.
---

# spec-harden (Claude side — author & orchestrator)

You are the **AUTHOR**. Gemini (run by the user in Antigravity) is the **primary critic**;
a fresh Claude subagent is the **secondary critic**. You coordinate through files in a
`harden/` folder. **Read `references/PROTOCOL.md` (next to this skill) once before acting.**

## Resolve inputs
- Spec path = the first non-flag argument, else the most recently modified `*.md` in
  `docs/superpowers/specs/`.
- `--critic-model {opus|sonnet|haiku|fable}` = model for the secondary-critic pre-pass.
  If absent, **skip the pre-pass** (Gemini leads alone).
- Harden dir = `<spec-dir>/<spec-stem>.harden/`. `SKILL_DIR` = this skill's directory
  (its `scripts/` and `references/` live there).

## Pick the phase
- Harden dir does not exist → **init**.
- User asks to finalize / confirms / says "chốt" → **finalize**.
- Otherwise (harden dir exists, `STATUS.md` turn = claude) → **respond**.
Run `python3 $SKILL_DIR/scripts/protocol.py status-read <harden>` to read turn/round.

## init
1. Create `<harden>/`; copy the spec file → `<harden>/draft.md`; copy
   `$SKILL_DIR/references/PROTOCOL.md` → `<harden>/PROTOCOL.md`.
2. **Lint (Step 0):** `python3 $SKILL_DIR/scripts/lint.py <harden>/draft.md`. For each JSON
   finding, fix it directly in `draft.md` (they are mechanical). Re-run until exit 0.
3. **Secondary-critic pre-pass** — only if `--critic-model` was given: spawn a subagent via
   the Agent tool (model = the flag value) with a critic prompt built from `PROTOCOL.md`
   (five lenses, severity, guards) over `<harden>/draft.md`. Triage its findings: ACCEPT →
   edit `draft.md`; REBUT → note reason. Write `<harden>/r0.claude-critic.md` (header +
   findings + your adjudication).
4. `python3 $SKILL_DIR/scripts/protocol.py status-write <harden> gemini 1 false`.
5. Tell the user, verbatim intent: *"Draft ready and pre-cleaned. Your turn — open Antigravity
   and run the spec-harden skill on `<harden>/draft.md`."*

## respond
1. Locate the latest `rN.gemini.md`. Run
   `python3 $SKILL_DIR/scripts/protocol.py findings <file>`. If it exits non-zero (errors /
   malformed blocks), show the errors and STOP — ask the user to re-run the Gemini turn.
2. Adjudicate each finding: **ACCEPT** → edit `draft.md` to fix; **REBUT** → one-line reason
   it is invalid/out-of-scope. Do not accept blindly (this is the author's judgment).
3. Count blocker/major you newly ACCEPTED this round. Write `<harden>/rN.claude.md`: the
   header (`AUTHOR: claude`, `OPEN_BLOCKERS`/`OPEN_MAJORS` = counts you did NOT resolve),
   per-finding ACCEPT/REBUT lines, and a short list of draft changes.
4. **Convergence / stop:**
   - `python3 $SKILL_DIR/scripts/protocol.py converged <rN.gemini.md>` exits 0 AND you
     accepted no new blocker/major → **converged**.
   - Same blocker/major seen in `r(N-1).gemini.md` and `rN.gemini.md` still unresolved →
     **circuit-breaker**: stop, surface to user.
   - Round `N >= 4` → **cap**: stop; list any unresolved majors — do NOT call it clean.
5. If continuing: `protocol.py status-write <harden> gemini <N+1> false`; tell user
   *"Round N done — your turn: Antigravity."* If converged/stopped: summarize and ask the user
   to confirm `finalize`.

## finalize (only after the user confirms)
1. Overwrite the real spec file with `<harden>/draft.md`.
2. Write `<harden>/SUMMARY.md`: rounds run, findings by severity, accepted vs rebutted,
   any unresolved majors, and the `minor`/`nit` cleanup list.
3. Commit the updated spec: `git add <spec> && git commit -m "docs(spec): harden <name>"`.
4. Tell the user it is done and where the summary is.

## Guards
- Apply the PROTOCOL critic guards (anti-perfectionism, high-confidence bias) when building
  the secondary-critic prompt.
- **Never edit the real spec before `finalize`.** All work happens in `draft.md`.
````

- [ ] **Step 2: Verify frontmatter + referenced paths exist**

Run:
```bash
python3 - <<'PY'
import re, os
p = "tools/spec-harden/claude-skill/SKILL.md"
t = open(p, encoding="utf-8").read()
assert t.startswith("---"), "missing frontmatter"
assert re.search(r'^name:\s*spec-harden\s*$', t, re.M), "bad name"
assert "description:" in t.split("---")[1], "missing description"
base = "tools/spec-harden/claude-skill"
for f in ("scripts/lint.py", "scripts/protocol.py", "references/PROTOCOL.md"):
    assert os.path.exists(os.path.join(base, f)), f"missing {f}"
print("Claude SKILL.md frontmatter + referenced files OK")
PY
```
Expected: `Claude SKILL.md frontmatter + referenced files OK`.

- [ ] **Step 3: Commit**

```bash
git add tools/spec-harden/claude-skill/SKILL.md
git commit -m "feat(spec-harden): Claude author/orchestrator skill"
```

---

### Task 5: Gemini critic skill (`gemini-skill/SKILL.md`)

**Files:**
- Create: `tools/spec-harden/gemini-skill/SKILL.md`

**Interfaces:**
- Consumes: `PROTOCOL.md` (copied into `harden/` by init); reads `draft.md` + latest `rN.claude.md`.
- Produces: `rN.gemini.md` (findings) + updates `STATUS.md` to `turn: claude`. Never edits `draft.md`.

- [ ] **Step 1: Write `SKILL.md`**

`tools/spec-harden/gemini-skill/SKILL.md`:
````markdown
---
name: spec-harden
description: Adversarial spec critic. Review the spec draft in the target `<name>.harden/` folder through five lenses and write severity-tagged findings that follow PROTOCOL.md. Activate when the user asks to harden, critique, or review a spec draft in this workspace.
---

# spec-harden (Antigravity/Gemini side — primary critic)

You are the **CRITIC**. The author is Claude (another tool); you never see its context —
coordinate ONLY through files. **Read `<name>.harden/PROTOCOL.md` first.**

## Steps
1. Find the harden folder (the `*.harden/` dir the user points you at, or under
   `docs/superpowers/specs/`). Read `PROTOCOL.md`, `draft.md`, `STATUS.md`, and the latest
   `rN.claude.md` if present (the author's prior responses).
2. Determine the round `N` from `STATUS.md` (`round`).
3. Critique `draft.md` through the five lenses — **Completeness, Testability, Ambiguity,
   Assumptions, Scope**. Raise only NEW or still-unaddressed issues versus prior rounds.
   Apply the guards: **anti-perfectionism** (a clean round is a valid result — do not invent
   blockers) and **high-confidence bias** (blocker/major only when confident).
4. Write `<harden>/r<N>.gemini.md`:
   - the header (`ROUND: N`, `AUTHOR: gemini`, `READS: draft.md[, r<N-1>.claude.md]`,
     `VERDICT: needs-work|converged`, `OPEN_BLOCKERS`, `OPEN_MAJORS`);
   - one finding block per issue, in the exact PROTOCOL format.
   If you have zero blocker/major findings, set `VERDICT: converged` with the counts at 0.
5. Update `STATUS.md` → `turn: claude` (keep the same round number).
6. Tell the user: *"Round N critique written to r<N>.gemini.md. Your turn — switch to Claude
   and run `spec-harden` (respond)."*

**You never edit `draft.md`.** You only write your findings file and flip the turn.
````

- [ ] **Step 2: Verify a hand-written Gemini file conforms to the parser**

Run:
```bash
python3 - <<'PY'
import sys; sys.path.insert(0, "tools/spec-harden/claude-skill/scripts")
import protocol
example = """ROUND: 1
AUTHOR: gemini
READS: draft.md
VERDICT: needs-work
OPEN_BLOCKERS: 0
OPEN_MAJORS: 1

[SEVERITY: major]
LENS: testability
LOCATION: Convergence section
ISSUE: 'no new blocker' is not defined precisely
SUGGESTION: Define 'new' as absent from prior rounds' findings
"""
f, e = protocol.parse_findings(example)
assert len(f) == 1 and not e, (f, e)
assert not protocol.is_converged(example)  # OPEN_MAJORS=1
print("Gemini example conforms to PROTOCOL")
PY
```
Expected: `Gemini example conforms to PROTOCOL`.

- [ ] **Step 3: Commit**

```bash
git add tools/spec-harden/gemini-skill/SKILL.md
git commit -m "feat(spec-harden): Gemini/Antigravity critic skill"
```

> **Note (manual, cannot be automated here):** the Gemini skill's *activation* inside
> Antigravity (auto-discovery of `<repo>/.agents/skills/spec-harden/SKILL.md`) must be
> smoke-tested live after Task 6 deploys the symlink — open Antigravity, confirm
> `/skills` lists `spec-harden`, and run it once against a real `harden/` folder.

---

### Task 6: Installer + auto-hook (`install.sh`)

**Files:**
- Create: `tools/spec-harden/install.sh`
- Modify: `~/.claude/CLAUDE.md` (append the auto-hook rule — done by the script, idempotently)

**Interfaces:**
- Consumes: the `claude-skill/` and `gemini-skill/` directories (Tasks 1–5).
- Produces: symlinks `~/.claude/skills/spec-harden` and `<repo>/.agents/skills/spec-harden`; an appended CLAUDE.md rule.

- [ ] **Step 1: Write `install.sh`**

`tools/spec-harden/install.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO_ROOT/tools/spec-harden"
CLAUDE_SKILLS="$HOME/.claude/skills"
AGENTS_SKILLS="$REPO_ROOT/.agents/skills"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"
HOOK_MARKER="<!-- spec-harden-auto-hook -->"

mkdir -p "$CLAUDE_SKILLS" "$AGENTS_SKILLS"

ln -sfn "$SRC/claude-skill" "$CLAUDE_SKILLS/spec-harden"
ln -sfn "$SRC/gemini-skill" "$AGENTS_SKILLS/spec-harden"
echo "linked: $CLAUDE_SKILLS/spec-harden -> $SRC/claude-skill"
echo "linked: $AGENTS_SKILLS/spec-harden -> $SRC/gemini-skill"

if [ -f "$CLAUDE_MD" ] && grep -q "$HOOK_MARKER" "$CLAUDE_MD"; then
  echo "auto-hook already present in $CLAUDE_MD"
else
  cat >> "$CLAUDE_MD" <<EOF

$HOOK_MARKER
## spec-harden auto-hook
After the \`superpowers:brainstorming\` skill writes and commits a spec, and BEFORE presenting
the user-review gate, invoke the \`spec-harden\` skill (\`init\`) on that spec, then tell the user
to run the Gemini turn in Antigravity. Only present the spec for approval once the loop has
converged (or the user opts out).
EOF
  echo "appended auto-hook to $CLAUDE_MD"
fi
```

- [ ] **Step 2: Make executable and run it**

Run:
```bash
chmod +x tools/spec-harden/install.sh && bash tools/spec-harden/install.sh
```
Expected: two `linked:` lines and an `appended`/`already present` line, no errors.

- [ ] **Step 3: Verify the deployment**

Run:
```bash
test -L "$HOME/.claude/skills/spec-harden" && \
  test -f "$HOME/.claude/skills/spec-harden/SKILL.md" && \
  test -f ".agents/skills/spec-harden/SKILL.md" && \
  grep -q "spec-harden-auto-hook" "$HOME/.claude/CLAUDE.md" && \
  echo "DEPLOY OK"
```
Expected: `DEPLOY OK` (symlinks resolve, both skills reachable, hook present).

- [ ] **Step 4: Commit**

```bash
git add tools/spec-harden/install.sh
git commit -m "feat(spec-harden): symlink installer + CLAUDE.md auto-hook"
```

---

### Task 7: End-to-end dry-run (Gemini turn simulated)

**Files:**
- Test: `tools/spec-harden/tests/test_e2e.sh` (a throwaway-driven integration check)

**Interfaces:**
- Consumes: everything (scripts, PROTOCOL, both skills, installer).
- Produces: proof the full file protocol + convergence + finalize works without Antigravity, by hand-writing the `rN.gemini.md` the user would otherwise produce.

- [ ] **Step 1: Write the e2e script**

`tools/spec-harden/tests/test_e2e.sh`:
```bash
#!/usr/bin/env bash
# Simulates one full spec-harden cycle using the scripts directly (no Antigravity, no LLM):
# init -> (fake Gemini round with 1 major) -> author resolves -> (fake clean round) -> converged.
set -euo pipefail
SCRIPTS="tools/spec-harden/claude-skill/scripts"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
H="$WORK/demo.harden"; mkdir -p "$H"

# init artifacts
printf '# Demo Spec\n\nThe cache TTL is 5 minutes.\n\n## Design\n\nConcrete detail.\n' > "$H/draft.md"
python3 "$SCRIPTS/lint.py" "$H/draft.md" >/dev/null && echo "lint: clean"
python3 "$SCRIPTS/protocol.py" status-write "$H" gemini 1 false

# round 1: fake Gemini finds one major
cat > "$H/r1.gemini.md" <<'EOF'
ROUND: 1
AUTHOR: gemini
READS: draft.md
VERDICT: needs-work
OPEN_BLOCKERS: 0
OPEN_MAJORS: 1

[SEVERITY: major]
LENS: completeness
LOCATION: Design
ISSUE: No cache eviction policy defined
SUGGESTION: Specify LRU with max size
EOF
python3 "$SCRIPTS/protocol.py" findings "$H/r1.gemini.md" >/dev/null && echo "r1 parse: ok"
python3 "$SCRIPTS/protocol.py" converged "$H/r1.gemini.md" && echo "BUG: should not be converged" && exit 1 || echo "r1: not converged (correct)"

# author accepts -> edits draft, advances round
printf '\n## Eviction\n\nLRU, max 128 entries.\n' >> "$H/draft.md"
python3 "$SCRIPTS/protocol.py" status-write "$H" gemini 2 false

# round 2: fake Gemini clean
cat > "$H/r2.gemini.md" <<'EOF'
ROUND: 2
AUTHOR: gemini
READS: draft.md, r1.claude.md
VERDICT: converged
OPEN_BLOCKERS: 0
OPEN_MAJORS: 0
EOF
python3 "$SCRIPTS/protocol.py" converged "$H/r2.gemini.md" && echo "r2: converged (correct)"

# finalize: promote draft (simulated)
cp "$H/draft.md" "$WORK/demo-spec.md"
grep -q "Eviction" "$WORK/demo-spec.md" && echo "finalize: promoted OK"
echo "E2E PASS"
```

- [ ] **Step 2: Run the e2e script**

Run: `bash tools/spec-harden/tests/test_e2e.sh`
Expected: ends with `E2E PASS` (lint clean → r1 not converged → r2 converged → promoted).

- [ ] **Step 3: Run the full test suite once more**

Run:
```bash
python3 tools/spec-harden/tests/test_lint.py && \
python3 tools/spec-harden/tests/test_protocol.py && \
bash tools/spec-harden/tests/test_e2e.sh && echo "ALL GREEN"
```
Expected: `ALL GREEN`.

- [ ] **Step 4: Commit**

```bash
git add tools/spec-harden/tests/test_e2e.sh
git commit -m "test(spec-harden): end-to-end dry-run (simulated Gemini turn)"
```

---

## Post-plan manual verification (cannot be automated)

1. **Live Antigravity smoke test** (the spec's biggest unknown): open Antigravity in this repo,
   confirm `/skills` lists `spec-harden` (from `.agents/skills/spec-harden`), and run it once
   against a real `harden/` folder — verify it writes a conforming `rN.gemini.md` and flips
   `STATUS.md`. If `.agents/skills/` is not auto-discovered, fall back to a saved workflow or a
   pasted prompt (spec §Delivery).
2. **Dogfood:** run the whole loop on `spec-harden`'s own design doc to shake out real findings
   before trusting it on the next feature spec.

## Self-Review

- **Spec coverage:** roles (T4/T5), file protocol + headers + severity + lenses (T3), Step-0
  lint (T1), secondary Claude critic pre-pass + `--critic-model` (T4), primary Gemini critic
  (T5), convergence + circuit-breaker + cap (T2 logic + T4/T5 prose), draft-then-promote-on-
  confirm (T4 finalize), 3 artifacts + install locations + auto-hook (T6), evidence/prior-art
  are spec-only (no task needed). Live Antigravity activation is flagged as manual (T5 note +
  post-plan §1). All covered.
- **Placeholder scan:** none — all code and file contents are complete.
- **Type consistency:** `parse_findings` returns `(findings, errors)` everywhere; `status-write
  <dir> <turn> <round> <converged>` arg order matches `write_status(d, turn, round_, converged)`;
  finding keys (`severity/lens/location/issue/suggestion`) identical in `lint.py` and
  `protocol.py`; header keys identical in PROTOCOL.md, `protocol.py`, and both skills.
