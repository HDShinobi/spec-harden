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


class TestContextTimeoutRegression(unittest.TestCase):
    """Reference roots for the critic, configurable timeout, regression-first prior rounds."""

    def setUp(self):
        self._cfg_dir = tempfile.TemporaryDirectory()
        self._old_cfg = codex_critic.CONFIG_PATH
        codex_critic.CONFIG_PATH = os.path.join(self._cfg_dir.name, "cfg.json")
        self._old_env = {k: os.environ.pop(k, None) for k in
                         ("SPEC_HARDEN_CONTEXT", "SPEC_HARDEN_CRITIC_TIMEOUT")}

    def tearDown(self):
        codex_critic.CONFIG_PATH = self._old_cfg
        for k, v in self._old_env.items():
            if v is not None:
                os.environ[k] = v
        self._cfg_dir.cleanup()

    def _cfg(self, **kw):
        import json
        with open(codex_critic.CONFIG_PATH, "w") as fh:
            json.dump(kw, fh)

    def _harden(self, d):
        with open(os.path.join(d, "draft.md"), "w") as fh:
            fh.write("# Spec\n\nSome content.\n")
        return d

    def test_prompt_lists_context_roots(self):
        with tempfile.TemporaryDirectory() as d:
            self._harden(d)
            p = codex_critic.build_prompt(d, 1, context_dirs=["/repo/a", "/ref/b"])
            self.assertIn("/repo/a", p)
            self.assertIn("/ref/b", p)
            self.assertIn("verify", p.lower())
            self.assertNotIn("{{", p)

    def test_prompt_without_context_has_no_roots_block(self):
        with tempfile.TemporaryDirectory() as d:
            self._harden(d)
            p = codex_critic.build_prompt(d, 1, context_dirs=[])
            self.assertNotIn("Reference roots", p)
            self.assertNotIn("{{", p)

    def test_context_default_is_git_toplevel(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            harden = os.path.join(d, "docs", "x.harden"); os.makedirs(harden)
            got = codex_critic.resolve_context(None, harden)
            self.assertEqual([os.path.realpath(x) for x in got], [os.path.realpath(d)])

    def test_context_none_from_config(self):
        self._cfg(context="none")
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            self.assertEqual(codex_critic.resolve_context(None, d), [])

    def test_context_cli_overrides(self):
        self._cfg(context="none")
        self.assertEqual(codex_critic.resolve_context(["/x", "/y"], "/tmp"), ["/x", "/y"])

    def test_timeout_precedence(self):
        self.assertEqual(codex_critic.resolve_timeout(None), codex_critic.FALLBACK_TIMEOUT)
        self._cfg(critic_timeout=1234)
        self.assertEqual(codex_critic.resolve_timeout(None), 1234)
        os.environ["SPEC_HARDEN_CRITIC_TIMEOUT"] = "77"
        self.assertEqual(codex_critic.resolve_timeout(None), 77)
        self.assertEqual(codex_critic.resolve_timeout(5), 5)
        del os.environ["SPEC_HARDEN_CRITIC_TIMEOUT"]

    def test_round2_prompt_is_regression_first(self):
        with tempfile.TemporaryDirectory() as d:
            self._harden(d)
            open(os.path.join(d, "r1.claude.md"), "w").close()
            p = codex_critic.build_prompt(d, 2)
            self.assertIn("Draft changes", p)
            self.assertIn("regression", p.lower())

    def test_timeout_flag_enforced(self):
        with tempfile.TemporaryDirectory() as d:
            bindir = os.path.join(d, "bin"); os.mkdir(bindir)
            harden = os.path.join(d, "h"); os.mkdir(harden)
            self._harden(harden)
            fake = os.path.join(bindir, "codex")
            with open(fake, "w") as fh:
                fh.write("#!/usr/bin/env bash\nsleep 5\n")
            os.chmod(fake, 0o755)
            env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"],
                       SPEC_HARDEN_CONFIG=codex_critic.CONFIG_PATH)
            r = subprocess.run(
                [sys.executable, os.path.join(SCRIPTS, "codex_critic.py"), harden, "1",
                 "--model", "m", "--timeout", "1", "--context", "none"],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 1)
            self.assertIn("timed out after 1s", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
