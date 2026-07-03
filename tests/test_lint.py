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

    def test_placeholder_in_inline_code_ignored(self):
        # a spec that documents the tokens (in inline code) must NOT be flagged
        f = lint.lint("# Spec\n\nThe scan looks for `TBD` and `TODO` tokens.\n")
        self.assertEqual(f, [])

    def test_placeholder_in_fenced_code_ignored(self):
        f = lint.lint("# Spec\n\n```\nTODO: sample\n```\n\nreal content\n")
        self.assertFalse(any("TODO" in x["issue"] for x in f))

    def test_section_with_only_code_not_empty(self):
        f = lint.lint("# Spec\n\n## Example\n\n```\ncode here\n```\n")
        self.assertFalse(any("Example" in x["issue"] for x in f))

    def test_placeholder_in_prose_still_detected(self):
        f = lint.lint("# Spec\n\nThe timeout is TBD seconds.\n")
        self.assertTrue(any("TBD" in x["issue"] for x in f))

if __name__ == "__main__":
    unittest.main()
