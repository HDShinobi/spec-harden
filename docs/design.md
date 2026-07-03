# spec-harden — Cross-Tool Adversarial Spec-Review Loop (Claude ⇄ Gemini/Antigravity)

**Status:** Draft 2026-07-02 · Tooling (cross-project, user-level + workspace)
**Scope:** A file-mediated adversarial review loop that hardens a spec before the user
approves it. **Claude Code** owns and revises the spec (author); **Gemini running inside
Antigravity** critiques it (a different model family). The two tools never call each other —
they exchange numbered files in a shared `harden/` folder, and the **user drives the turns**
by alternating between the two tools. The loop repeats until a round surfaces no new
blocker/major finding and both sides agree; on the user's confirmation, Claude promotes the
converged draft into the real spec.

## Problem

Specs produced by `superpowers:brainstorming` are frequently incomplete; forwarding them to a
*different* model (Gemini) surfaces gaps the original author missed — a same-model blind spot.
Today this cross-model review is manual, ad hoc, and easy to skip.

## Why this architecture (the binding constraint)

The critic must be a *different* model family than the author (evidence below). The user pays
for **Google AI Pro (Gemini)**, so Gemini is the zero-marginal-cost critic — **but only
interactively inside Antigravity**. Verified 2026-07-02:

- The standalone **`gemini` CLI** free OAuth tier was discontinued by Google for individuals
  (`IneligibleTierError: UNSUPPORTED_CLIENT` → "migrate to the Antigravity suite"). Consumer
  Gemini Pro does **not** grant Gemini Code Assist CLI eligibility.
- The **Antigravity Python SDK** (`google-antigravity` 0.1.5) installs fine but its
  `LocalAgentConfig` **also requires a raw `GEMINI_API_KEY`** — it does not reuse the
  Antigravity/Pro login.
- Therefore **no headless path uses the paid Pro quota**; only the interactive Antigravity
  surfaces (IDE sidebar, Antigravity 2.0 app, or `agy` TUI, all using G1 credits) do.

**Consequence:** we cannot auto-spawn the critic. A **human-mediated, file-based handoff** is
the correct — and only free — way to use the Gemini the user already pays for. (Codex was also
rejected: `codex exec` works via ChatGPT login but free usage is too limited and would require
paying.) An automated `codex exec` / SDK loop remains a possible future path if the user later
adds paid API budget — the file protocol below is designed so a driver script could replace
the human turn-taking without changing the format.

## Roles

- **Author = Claude Code.** Owns the spec, adjudicates each critic finding (ACCEPT → revise;
  REBUT → reasoned rejection, per `superpowers:receiving-code-review`), maintains the working
  draft. Never accepts findings blindly.
- **Primary critic = Gemini inside Antigravity.** Reads the current draft + the author's latest
  responses, returns severity-tagged findings against the five-lens rubric. A different model
  family → catches blind spots a Claude self-review would share. **Gemini leads the loop.**
- **Secondary critic = a fresh Claude subagent** (model chosen per run via `--critic-model`;
  spawned via the Agent tool with a clean context, no authoring bias). Runs **once, as a
  pre-pass** before the first Gemini handoff, to shake out the obvious gaps cheaply and
  automatically so Gemini's (manual) turns are spent on the harder cross-family blind spots.
  This realizes the user's original "spawn another agent to critique and debate the author"
  idea. *Caveat:* same model family as the author → shares some self-preference blind spots, so
  it supplements — never replaces — the Gemini pass.
- **Driver = the user.** Runs the Claude-side skill, switches to Antigravity to run the
  Gemini-side skill, and switches back — alternating until convergence — then confirms the
  final promotion.

## The shared protocol (`harden/` folder)

For a spec at `docs/.../<name>-design.md`, all exchange lives in a sibling folder
`docs/.../<name>.harden/`:

```
<name>.harden/
  PROTOCOL.md        # the contract both skills obey (authored once, copied per project)
  draft.md           # the working spec draft — Claude edits; starts as a copy of the spec
  r1.gemini.md       # round 1 critic findings (written by Gemini/Antigravity)
  r1.claude.md       # round 1 author adjudication (written by Claude)
  r2.gemini.md
  r2.claude.md
  STATUS.md          # turn, round, open counts, converged flag, target_spec_path
```

- The **real spec is never edited during the loop.** Debate happens on `draft.md`; only on the
  user's confirmation does Claude promote `draft.md` → the real spec (`finalize`).
- `STATUS.md` records `target_spec_path` (the original spec's path) at `init`, so `finalize`
  promotes `draft.md` back to the exact file regardless of the spec's naming convention.
- Each file carries a header both skills parse:
  ```
  ROUND: N
  AUTHOR: gemini | claude
  READS: <the files this response is based on>
  VERDICT: needs-work | converged
  OPEN_BLOCKERS: <int>
  OPEN_MAJORS: <int>
  ```

### Critic rubric (five lenses)

The Gemini skill directs the critic through five explicit lenses (Constitutional-AI lesson:
written principles beat "find problems"; lenses from `teterouge/spec-auditor` + Kiro):
**Completeness · Testability · Ambiguity · Assumptions · Scope.**

### Severity classification

| Severity | Meaning | Blocks convergence? |
|----------|---------|---------------------|
| `blocker` | Unimplementable / self-contradictory / missing a core decision | Yes |
| `major` | Real gap or wrong assumption that would cause rework | Yes |
| `minor` | Safe-to-resolve ambiguity or omission | No (logged) |
| `nit` | Style / wording | No (logged) |

Finding format (one block per finding, strict + machine-parseable):
```
[SEVERITY: blocker|major|minor|nit]
LENS: completeness|testability|ambiguity|assumptions|scope
LOCATION: <section / quote>
ISSUE: <what is wrong or missing>
SUGGESTION: <concrete fix>
```
Each field is a **single line**; separate consecutive finding blocks with a blank line.

Both skills carry two calibration guards (from `adversarial-spec` + OpenAI Agents SDK judge +
CriticGPT): **anti-perfectionism** — a low-/no-finding round is a legitimate convergence
signal, do not invent blockers; and **high-confidence bias** — only raise blocker/major when
confident.

## The loop, step by step

0. **Claude** writes the spec (via brainstorming) and runs `spec-harden init` →
   creates `<name>.harden/`, copies the spec to `draft.md`, writes `PROTOCOL.md` + `STATUS.md`
   (turn = gemini, round = 1, `target_spec_path` = the original spec's path). Also runs a
   **deterministic lint** on the draft first (`TBD`/`TODO`/`???`/empty sections/dup headings),
   auto-fixing mechanical defects before the critic ever sees it (pattern from BMAD V6
   `lint_spine.py`). The lint ignores tokens inside inline-code/fenced-code spans so a spec that
   *documents* placeholder tokens is not falsely flagged.
0.5. **Claude-critic pre-pass (automatic, no handoff).** `init` (or a `preclean` sub-step)
   spawns a fresh Claude subagent (`--critic-model`, default resolved from the flag) that
   critiques `draft.md` against the same rubric. Claude the author triages its findings,
   ACCEPT→edits `draft.md`, and logs `r0.claude-critic.md`. Runs once; its point is to hand
   Gemini an already-cleaned draft, not to converge on its own.
1. **User → Antigravity**, runs the Gemini `spec-harden` skill. Gemini reads `draft.md`,
   `r0.claude-critic.md` (round 1), and — when `N > 1` — **its own prior findings
   `r<N-1>.gemini.md`** plus `r<N-1>.claude.md` (so it can enforce "only raise NEW issues" and
   detect recurrence for the circuit-breaker). All are listed in its `READS` header. It writes
   `rN.gemini.md` with findings + verdict and sets `STATUS.md` turn = claude.
2. **User → Claude Code**, runs `spec-harden respond`. Claude reads the latest `rN.gemini.md`,
   adjudicates each finding (ACCEPT → edit `draft.md`; REBUT → reason), writes `rN.claude.md`
   (what changed + rebuttals + verdict), advances round, sets turn = gemini.
3. Repeat 1–2. The **debate is realized across rounds**: a wrongly-rebutted finding gets
   re-raised by the next Gemini round against the (unchanged-on-that-point) draft.
4. **Convergence:** stop when a Gemini round reports `OPEN_BLOCKERS: 0` and `OPEN_MAJORS: 0` —
   i.e. every previously-raised blocker/major is either fixed in `draft.md` or rebutted with
   Gemini's agreement, and **no new** blocker/major was raised this round → `VERDICT: converged`.
   Fixes verified in this same round DO count as converged; the gate only blocks on *newly
   raised* blocker/major that Gemini has not yet re-reviewed.
5. **Circuit-breaker:** if the same blocker/major recurs across two rounds unresolved
   (author REBUT vs critic re-raise, or an ACCEPTed fix still fails), stop and surface it to
   the user as a genuine disagreement to arbitrate (pattern from `alecnielsen/adversarial-review`).
6. **Round cap `MAX_ROUNDS = 4`** as a thrash guard. Hitting the cap with open majors does
   **not** count as converged — Claude reports the unresolved majors to the user, never
   silently "clean".
7. **User confirms** → Claude runs `spec-harden finalize`: promotes `draft.md` → the real spec
   (path read from `STATUS.md`'s `target_spec_path`), writes a summary (rounds, findings by
   severity, accepted vs rebutted, any leftovers). It then stages and commits **only** the
   target spec file and the `<name>.harden/` directory with the message
   `docs(spec): harden <name>` — nothing else is staged. `minor`/`nit` findings are offered as
   an optional cleanup list.

## Delivery — three artifacts

1. **Claude Code skill** — `~/.claude/skills/spec-harden/SKILL.md` (user-level, cross-project).
   Sub-commands driven by `STATUS.md` state: `init` (+ Claude-critic pre-pass), `respond`,
   `finalize`. Reads/writes files in `harden/` and edits `draft.md`; the only "external"
   action is spawning the secondary Claude critic via the Agent tool (`--critic-model` selects
   its model; omitting the flag skips the pre-pass and goes straight to the Gemini handoff).
2. **Gemini/Antigravity skill** — `<project-root>/.agents/skills/spec-harden/SKILL.md`.
   Antigravity auto-discovers `<project-root>/.agents/` for rules + custom skills, and uses the
   **identical `SKILL.md` + frontmatter format** as Claude Code (verified from the local
   `antigravity_guide` builtin skill). Same rubric/severity/format; role = critic only (it
   never edits `draft.md`, only writes `rN.gemini.md`).
3. **`PROTOCOL.md`** — the shared contract (file layout, header fields, severity, lenses,
   finding format, convergence + circuit-breaker rules). Both skills reference it; `init`
   drops a copy into each project's `harden/` folder so the two blind-to-each-other tools stay
   in lock-step through disk.

**Auto-hook (Claude side only):** a soft rule in `~/.claude/CLAUDE.md` — after brainstorming
writes a spec, before the user-review gate, run `spec-harden init` and tell the user to start
the Gemini turn. (Does not touch vendored plugins; survives updates. Escalate to a `Stop` hook
only if the rule is ignored in practice.)

## Prior art & evidence (GitHub research, 2026-07-01)

**Why a *different-model* critic (the core bet):**
- *Model heterogeneity* — same-model debate shares correlated errors and often fails to beat a
  single self-consistency baseline; a different model family corrects error propagation
  ([arXiv 2502.08788](https://arxiv.org/pdf/2502.08788)). Keep roles fixed (Gemini=critic).
- *Self-preference bias* — models overrate their own / same-family output; mitigation is a
  different-family judge ([arXiv 2410.21819](https://arxiv.org/html/2410.21819v1)).
- *CriticGPT* — a dedicated critic caught more inserted bugs than paid human reviewers, but an
  over-eager critic hallucinates findings ([arXiv 2407.00215](https://arxiv.org/abs/2407.00215)).

**Closest prior art (patterns borrowed):**
- `zscole/adversarial-spec` (~552★) — Claude Code plugin, multi-model adversarial spec debate
  to consensus + anti-rubber-stamp guard. We use a leaner two-tool handoff + per-finding severity.
- `alecnielsen/adversarial-review` — **circuit-breaker on stagnation** (adopted).
- BMAD-METHOD V6 (~50k★) `lint_spine.py` — **deterministic lint floor first** (adopted, Step 0).
- `teterouge/spec-auditor` — the **five-lens** rubric.
- OpenAI Agents SDK `llm_as_a_judge.py` / CrewAI `guardrail_max_retries` (default 3) — confirm
  the *exit-on-clean + hard round cap (3–5)* shape; our per-finding severity gate refines it.
- `hamelsmu/claude-review-loop` (~689★) — Claude↔Codex Stop-hook enforcement (our deferred
  escalation). `atompilot/claude-code-cross-review` — Claude-writes / other-model-reviews /
  loop-until-clean, the same shape, but auto (needs paid API).

**Landscape note:** no mainstream commercial spec tool ships a true iterative multi-model
adversarial loop; Kiro = one advisory pass + human gate. The loop concept lives in the OSS
Claude Code plugin ecosystem.

## Dependencies & risks

- **Antigravity** must be installed with a logged-in Google AI Pro account (verified present).
  The Gemini skill runs there interactively; there is no headless fallback by design.
- **Same SKILL.md format across tools** is verified but the Antigravity skill/rules loader
  behavior (auto-discovery of `.agents/skills/`, exact activation) should be confirmed on the
  first real run — treat the Gemini skill as needing a live smoke test.
- **Two blind tools coordinating via disk** — the strict header + `STATUS.md` turn field is the
  guardrail; if a file is malformed, the receiving skill logs it and asks the user rather than
  guessing.
- **Human-driven turns are slow and skippable** — mitigated by clear `STATUS.md` ("your turn:
  Antigravity") and the Claude-side auto-hook that kicks off `init`.
- **Codex dropped** (cost); **Gemini headless dropped** (no free path). Documented above so the
  decision isn't re-litigated.

## Resolved decisions (formerly open questions)

- **Antigravity custom-skill activation: CONFIRMED.** `<repo>/.agents/skills/<name>/SKILL.md`
  is auto-discovered and registered by Antigravity (verified 2026-07-03: Gemini loaded the
  `spec-harden` skill and produced a PROTOCOL-conforming `r1.gemini.md`).
- **`STATUS.md` is machine-checked.** Both skills read `STATUS.md` `turn` and refuse to act out
  of turn — the Claude skill runs `respond` only when `turn: claude`, the Gemini skill critiques
  only when `turn: gemini`.
