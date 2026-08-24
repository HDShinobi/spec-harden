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

    def test_status_converged_true_roundtrips(self):
        # the converged-exit path writes the flag as the CLI string "true"; it must read back "true"
        with tempfile.TemporaryDirectory() as d:
            protocol.write_status(d, "claude", 3, "true")
            self.assertEqual(protocol.read_status(d)["converged"], "true")
            # a bool True must serialize the same way (lower-cased)
            protocol.write_status(d, "claude", 3, True)
            self.assertEqual(protocol.read_status(d)["converged"], "true")

    def test_status_target_spec_path(self):
        with tempfile.TemporaryDirectory() as d:
            protocol.write_status(d, "gemini", 1, False, "docs/x-design.md")
            self.assertEqual(protocol.read_status(d)["target_spec_path"], "docs/x-design.md")

    def test_status_preserves_target_spec_path(self):
        # advancing the round without re-passing the path must NOT drop it
        with tempfile.TemporaryDirectory() as d:
            protocol.write_status(d, "gemini", 1, False, "docs/x-design.md")
            protocol.write_status(d, "claude", 2, False)
            s = protocol.read_status(d)
            self.assertEqual(s["target_spec_path"], "docs/x-design.md")
            self.assertEqual(s["round"], "2")

if __name__ == "__main__":
    unittest.main()
