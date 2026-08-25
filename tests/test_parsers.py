"""Regression tests for the wolfpack parsers.

Run from the repo root:  python3 -m unittest discover -s tests
Covers the parsers hardened by review findings: right_lines (incl. the `++ `
added-line edge and multi-file metadata), anchors, the Known-gaps bounding
regex, the lockfile path-boundary regex, and dynamic fence sizing.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import build_packet
import wolftools

PATCH = """\
diff --git a/a.txt b/a.txt
index 0000000..1111111 100644
--- a/a.txt
+++ b/a.txt
@@ -1,3 +1,4 @@
 ctx1
-old
+new
+++ plusplus
 ctx2
@@ -10,2 +11,2 @@
 ctx3
-gone
+here
diff --git a/b.py b/b.py
new file mode 100644
index 0000000..2222222
--- /dev/null
+++ b/b.py
@@ -0,0 +1,2 @@
+line1
+line2
"""


class TestRightLines(unittest.TestCase):
    def setUp(self):
        f = tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False)
        f.write(PATCH); f.close()
        self.addCleanup(os.unlink, f.name)
        self.out = wolftools.right_lines(f.name)

    def test_added_and_context_lines_only_inside_hunks(self):
        # `+++ plusplus` inside a hunk is an ADDED line (new-side 3), not a header;
        # `index`/`---`/`new file mode` metadata between hunks must not count.
        self.assertEqual(self.out["a.txt"], {1, 2, 3, 4, 11, 12})

    def test_new_file(self):
        self.assertEqual(self.out["b.py"], {1, 2})

    def test_no_other_paths(self):
        self.assertEqual(set(self.out), {"a.txt", "b.py"})


class TestAnchors(unittest.TestCase):
    def test_range(self):
        self.assertEqual(list(wolftools.anchors("scripts/wolftools.py:94-101")),
                         [("scripts/wolftools.py", 94, 101)])

    def test_multiple_and_single_line(self):
        self.assertEqual(list(wolftools.anchors("a.py:1 and b.js:2-3")),
                         [("a.py", 1, 1), ("b.js", 2, 3)])

    def test_dotfile_and_en_dash(self):
        self.assertEqual(list(wolftools.anchors(".gitignore:3")), [(".gitignore", 3, 3)])
        self.assertEqual(list(wolftools.anchors("docs/plan.md:5–7")), [("docs/plan.md", 5, 7)])

    def test_symbol_only_location_yields_nothing(self):
        self.assertEqual(list(wolftools.anchors("profileOf / the PROFILES table")), [])


class TestKnownGapsBounding(unittest.TestCase):
    def test_stops_at_next_h2(self):
        body = "intro\n\n## Known gaps\n- gap A\n- gap B\n\n## Verification\n- tests pass\n"
        got = build_packet.KNOWN_GAPS_RE.search(body).group(0)
        self.assertIn("gap A", got)
        self.assertIn("gap B", got)
        self.assertNotIn("Verification", got)
        self.assertNotIn("tests pass", got)

    def test_stops_at_closes_line(self):
        body = "## Known gaps\n- gap\nCloses #5\n"
        got = build_packet.KNOWN_GAPS_RE.search(body).group(0)
        self.assertIn("gap", got)
        self.assertNotIn("Closes", got)

    def test_absent_section(self):
        self.assertIsNone(build_packet.KNOWN_GAPS_RE.search("## Summary\nno gaps section\n"))


class TestLockfileRegex(unittest.TestCase):
    def test_matches_lockfiles_at_path_boundary(self):
        self.assertTrue(build_packet.LOCKFILE_RE.search("diff --git a/package-lock.json b/package-lock.json"))
        self.assertTrue(build_packet.LOCKFILE_RE.search("diff --git a/sub/yarn.lock b/sub/yarn.lock"))

    def test_rejects_name_suffixes_and_extensions(self):
        self.assertFalse(build_packet.LOCKFILE_RE.search("diff --git a/my-package-lock.json b/my-package-lock.json"))
        self.assertFalse(build_packet.LOCKFILE_RE.search("diff --git a/Cargo.lockfile b/Cargo.lockfile"))


class TestFence(unittest.TestCase):
    def test_plain_content_gets_three_backticks(self):
        self.assertEqual(build_packet.fence("plain", "diff"), "```diff\nplain\n```")

    def test_content_with_backtick_runs_gets_longer_fence(self):
        out = build_packet.fence("before\n```\ninjected\n```\nafter")
        self.assertTrue(out.startswith("````\n") and out.endswith("\n````"))
        out5 = build_packet.fence("x `````` y")  # 6-backtick run inside -> 7-tick fence
        self.assertTrue(out5.startswith("```````\n"))


if __name__ == "__main__":
    unittest.main()
