#!/usr/bin/env python3
"""spec-harden — automatic Codex critic turn.

Builds the adversarial-critic prompt from references/CRITIC_PROMPT.md, runs it through
`codex exec` in a READ-ONLY sandbox rooted at the harden folder (so Codex reads draft.md /
prior author round itself), and captures the model's final message straight into
`<harden>/r<ROUND>.codex.md` in the exact PROTOCOL finding-block format.

We call `codex exec` DIRECTLY (not the codex plugin's codex-companion.mjs): the plugin's
app-server pins an older client_version and rejects current models (gpt-5.6-*), whereas the
CLI honors the logged-in ChatGPT account. Foreground/blocking — specs harden in seconds.

Usage:
  codex_critic.py <harden_dir> <round> [--model M] [--effort E]

Env overrides: SPEC_HARDEN_CRITIC_MODEL, SPEC_HARDEN_CRITIC_EFFORT.
Exit 0 on a captured, parseable critique; non-zero (with a reason on stderr) otherwise.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(SKILL_DIR, "references", "CRITIC_PROMPT.md")

# Settings file — edit this to change the critic model / effort once, no flags needed.
# Precedence: CLI flag > env var > config file > built-in default.
CONFIG_PATH = os.environ.get("SPEC_HARDEN_CONFIG", os.path.expanduser("~/.spec-harden.json"))
FALLBACK_MODEL = "gpt-5.6-terra"
FALLBACK_EFFORT = "medium"
FALLBACK_DEPTH = "spec"          # spec = spec-quality only; design = also challenge the approach

_SPEC_LENSES = "completeness|testability|ambiguity|assumptions|scope"
_DESIGN_LENSES = _SPEC_LENSES + "|design"
_CHALLENGE_BLOCK = """
Additionally, apply the **design** lens — challenge the APPROACH itself, not just how it is written:
- **design** — is this the right solution? What load-bearing assumptions does the chosen approach
  depend on, and what happens when one is false? Where does it break under real-world conditions
  (scale, concurrency, failure/degraded dependencies, migration, rollback)? What simpler or more
  robust alternative was not considered, and why might it be better? Name the tradeoff being made.
Raise a `design` finding only when you can point to a concrete way the approach fails or a concrete
better alternative — do not raise vague "have you considered…" musings.
"""


def load_config():
    """Read ~/.spec-harden.json (keys: critic_model, critic_effort, final_verify). Never raises."""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_model(cli):
    cfg = load_config()
    return cli or os.environ.get("SPEC_HARDEN_CRITIC_MODEL") or cfg.get("critic_model") or FALLBACK_MODEL


def resolve_effort(cli):
    cfg = load_config()
    return cli or os.environ.get("SPEC_HARDEN_CRITIC_EFFORT") or cfg.get("critic_effort") or FALLBACK_EFFORT


def resolve_depth(cli):
    cfg = load_config()
    depth = (cli or os.environ.get("SPEC_HARDEN_DEPTH") or cfg.get("depth") or FALLBACK_DEPTH).lower()
    if depth not in ("spec", "design"):
        die(f"invalid depth {depth!r} — use 'spec' or 'design'.")
    return depth

# import the shared parser so we validate what Codex produced
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))
from protocol import parse_findings, parse_header  # noqa: E402


def die(msg):
    print(f"codex_critic: {msg}", file=sys.stderr)
    sys.exit(1)


def build_prompt(harden_dir, round_no, depth="spec"):
    draft = os.path.join(harden_dir, "draft.md")
    if not os.path.isfile(draft):
        die(f"draft not found: {draft}")
    prior_rel = f"r{round_no - 1}.claude.md"
    prior_path = os.path.join(harden_dir, prior_rel)
    has_prior = round_no > 1 and os.path.isfile(prior_path)
    if has_prior:
        prior_block = (
            f"- `{prior_rel}` — the author's adjudication of your PREVIOUS round "
            "(ACCEPT/REBUT + the changes made). Read it so you only raise new/unaddressed issues."
        )
        reads = f"draft.md, {prior_rel}"
    else:
        prior_block = "- (no prior author round — this is the first critic pass.)"
        reads = "draft.md"

    challenge = _CHALLENGE_BLOCK if depth == "design" else ""
    lens_enum = _DESIGN_LENSES if depth == "design" else _SPEC_LENSES

    with open(TEMPLATE, encoding="utf-8") as fh:
        tpl = fh.read()
    return (
        tpl.replace("{{ROUND}}", str(round_no))
        .replace("{{DRAFT_REL}}", "draft.md")
        .replace("{{PRIOR_BLOCK}}", prior_block)
        .replace("{{READS}}", reads)
        .replace("{{CHALLENGE_BLOCK}}", challenge)
        .replace("{{LENS_ENUM}}", lens_enum)
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("harden_dir")
    ap.add_argument("round", type=int)
    ap.add_argument("--model", default=None, help="override critic model (else config/env/default)")
    ap.add_argument("--effort", default=None, help="override reasoning effort (else config/env/default)")
    ap.add_argument("--depth", default=None, choices=["spec", "design"],
                    help="spec = spec-quality only (default); design = also challenge the approach")
    args = ap.parse_args()

    model = resolve_model(args.model)
    effort = resolve_effort(args.effort)
    depth = resolve_depth(args.depth)

    harden_dir = os.path.abspath(args.harden_dir)
    if not os.path.isdir(harden_dir):
        die(f"harden dir not found: {harden_dir}")

    codex = shutil.which("codex")
    if not codex:
        die("`codex` CLI not found on PATH. Install with `npm install -g @openai/codex` and `codex login`.")

    prompt = build_prompt(harden_dir, args.round, depth)
    out_path = os.path.join(harden_dir, f"r{args.round}.codex.md")

    cmd = [
        codex, "exec",
        "-m", model,
        "-c", f"model_reasoning_effort={effort}",
        "-s", "read-only",
        "-C", harden_dir,
        "--skip-git-repo-check",
        "--ignore-rules",          # don't let repo .rules files perturb the critic
        "-o", out_path,            # final message → rN.codex.md, clean
        "-",                       # prompt from stdin
    ]
    try:
        proc = subprocess.run(
            cmd, input=prompt, text=True,
            capture_output=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        die("codex exec timed out after 600s.")

    if proc.returncode != 0 or not os.path.isfile(out_path) or not open(out_path, encoding="utf-8").read().strip():
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        die("codex exec produced no critique. Last output:\n  " + "\n  ".join(tail))

    text = open(out_path, encoding="utf-8").read()
    # A real critique MUST carry the protocol header — this is what distinguishes a
    # legitimately empty (converged) critique from off-format garbage that happens to
    # contain zero finding blocks.
    header = parse_header(text)
    missing = [k for k in ("VERDICT", "OPEN_BLOCKERS", "OPEN_MAJORS") if k not in header]
    if missing:
        die(f"Codex output is missing protocol header field(s) {missing} — not a valid critique.\nSee {out_path}")
    findings, errors = parse_findings(text)
    if errors:
        die(f"Codex output did not match the finding-block format: {errors}\nSee {out_path}")

    print(out_path)
    print(f"model={model} effort={effort} depth={depth} findings={len(findings)}")


if __name__ == "__main__":
    main()
