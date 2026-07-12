#!/usr/bin/env python3
"""Offline tests for codex_critic.py — prompt assembly + the codex-exec contract.

No network: we put a fake `codex` on PATH that echoes a canned, protocol-shaped critique
into the --output-last-message file, and assert codex_critic wires it up correctly.
"""
import os
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "claude-skill", "scripts")
sys.path.insert(0, SCRIPTS)
import codex_critic  # noqa: E402


class TestPromptBuild(unittest.TestCase):
    def _harden(self, d):
        with open(os.path.join(d, "draft.md"), "w") as fh:
            fh.write("# Spec\n\nSome content.\n")
        return d

    def test_round1_no_prior(self):
        with tempfile.TemporaryDirectory() as d:
            self._harden(d)
            p = codex_critic.build_prompt(d, 1)
            self.assertIn("ROUND: 1", p)
            self.assertIn("AUTHOR: codex", p)
            self.assertIn("READS: draft.md", p)
            self.assertIn("first critic pass", p)
            self.assertNotIn("{{", p)  # every placeholder interpolated

    def test_round2_with_prior(self):
        with tempfile.TemporaryDirectory() as d:
            self._harden(d)
            open(os.path.join(d, "r1.claude.md"), "w").close()
            p = codex_critic.build_prompt(d, 2)
            self.assertIn("ROUND: 2", p)
            self.assertIn("r1.claude.md", p)
            self.assertIn("READS: draft.md, r1.claude.md", p)
            self.assertNotIn("{{", p)

    def test_depth_spec_excludes_design(self):
        with tempfile.TemporaryDirectory() as d:
            self._harden(d)
            p = codex_critic.build_prompt(d, 1, depth="spec")
            self.assertNotIn("challenge the APPROACH", p)
            # the finding-block lens enum must NOT offer 'design' in spec mode
            self.assertIn("LENS: completeness|testability|ambiguity|assumptions|scope\n", p)
            self.assertNotIn("assumptions|scope|design", p)
            self.assertNotIn("{{", p)

    def test_depth_design_includes_challenge(self):
        with tempfile.TemporaryDirectory() as d:
            self._harden(d)
            p = codex_critic.build_prompt(d, 1, depth="design")
            self.assertIn("challenge the APPROACH", p)
            self.assertIn("assumptions|scope|design", p)  # design lens offered in the enum
            self.assertNotIn("{{", p)


class TestExecContract(unittest.TestCase):
    """Run the whole script against a fake `codex` binary — asserts flags + capture + validation."""

    CANNED = (
        "ROUND: 1\nAUTHOR: codex\nREADS: draft.md\nVERDICT: needs-work\n"
        "OPEN_BLOCKERS: 0\nOPEN_MAJORS: 1\n\n"
        "[SEVERITY: major]\nLENS: completeness\nLOCATION: Spec\n"
        "ISSUE: missing thing\nSUGGESTION: add thing\n"
    )

    def _fake_codex(self, bindir, body):
        p = os.path.join(bindir, "codex")
        with open(p, "w") as fh:
            fh.write(body)
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return p

    def _run(self, harden, bindir, round_no=1):
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"])
        return subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "codex_critic.py"), harden, str(round_no),
             "--model", "gpt-5.6-terra"],
            env=env, capture_output=True, text=True,
        )

    def test_happy_path(self):
        with tempfile.TemporaryDirectory() as d:
            bindir = os.path.join(d, "bin"); os.mkdir(bindir)
            harden = os.path.join(d, "h"); os.mkdir(harden)
            open(os.path.join(harden, "draft.md"), "w").write("# S\n\nx\n")
            # fake codex: find the -o path in argv, write the canned critique to it
            self._fake_codex(bindir, (
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "a=sys.argv\n"
                "o=a[a.index('-o')+1]\n"
                f"open(o,'w').write({self.CANNED!r})\n"
            ))
            r = self._run(harden, bindir)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("findings=1", r.stdout)
            self.assertTrue(os.path.isfile(os.path.join(harden, "r1.codex.md")))

    def test_malformed_output_fails(self):
        with tempfile.TemporaryDirectory() as d:
            bindir = os.path.join(d, "bin"); os.mkdir(bindir)
            harden = os.path.join(d, "h"); os.mkdir(harden)
            open(os.path.join(harden, "draft.md"), "w").write("# S\n\nx\n")
            self._fake_codex(bindir, (
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "a=sys.argv\n"
                "o=a[a.index('-o')+1]\n"
                "open(o,'w').write('garbage not in protocol format')\n"
            ))
            r = self._run(harden, bindir)
            self.assertEqual(r.returncode, 1)
            # rejected either as bad header or bad finding block — both are valid rejections
            self.assertTrue(
                "not a valid critique" in r.stderr or "finding-block format" in r.stderr,
                r.stderr,
            )

    def test_empty_output_fails(self):
        with tempfile.TemporaryDirectory() as d:
            bindir = os.path.join(d, "bin"); os.mkdir(bindir)
            harden = os.path.join(d, "h"); os.mkdir(harden)
            open(os.path.join(harden, "draft.md"), "w").write("# S\n\nx\n")
            # codex exits non-zero, writes nothing
            self._fake_codex(bindir, "#!/usr/bin/env bash\necho boom >&2\nexit 3\n")
            r = self._run(harden, bindir)
            self.assertEqual(r.returncode, 1)
            self.assertIn("no critique", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
