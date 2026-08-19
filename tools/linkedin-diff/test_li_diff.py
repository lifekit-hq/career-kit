"""Unit tests for li_diff. Run:  python3 -m unittest discover -s tools/linkedin-diff"""
import json
import tempfile
import unittest
from pathlib import Path

import li_diff


def make_snapshot(root: Path, layout: str, sections: dict, structured=None):
    """layout: 'new' (raw/<s>.txt + profile.json) or 'legacy' (flat files)."""
    root.mkdir(parents=True, exist_ok=True)
    for name, text in sections.items():
        if layout == "new":
            rel = f"raw/{name}.txt"
        else:
            rel = "profile_text.txt" if name == "profile" else f"{name}.txt"
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    if structured is not None:
        fname = "profile.json" if layout == "new" else "profile_structured.json"
        (root / fname).write_text(json.dumps(structured), encoding="utf-8")


class LiDiffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _diff(self, a, b):
        return li_diff.diff_snapshots(li_diff.load_snapshot(a), li_diff.load_snapshot(b))

    def test_added_and_removed_lines(self):
        a, b = self.root / "a", self.root / "b"
        make_snapshot(a, "new", {"profile": "Recruiter at Acme\nDublin"})
        make_snapshot(b, "new", {"profile": "Social Media Manager\nDublin"})
        d = self._diff(a, b)
        self.assertEqual(d["sections"]["profile"]["added"], ["Social Media Manager"])
        self.assertEqual(d["sections"]["profile"]["removed"], ["Recruiter at Acme"])

    def test_identical_chrome_cancels_out(self):
        nav = "Skip to search\nHome\nMy Network\n"
        a, b = self.root / "a", self.root / "b"
        make_snapshot(a, "new", {"skills": nav + "Canva"})
        make_snapshot(b, "new", {"skills": nav + "Canva\nCapCut"})
        d = self._diff(a, b)
        self.assertEqual(d["sections"]["skills"]["added"], ["CapCut"])
        self.assertEqual(d["sections"]["skills"]["removed"], [])

    def test_legacy_layout_maps_to_same_sections(self):
        a, b = self.root / "a", self.root / "b"
        make_snapshot(a, "legacy", {"profile": "Old headline"})
        make_snapshot(b, "new", {"profile": "New headline"})
        d = self._diff(a, b)
        self.assertIn("profile", d["sections"])
        self.assertEqual(d["sections"]["profile"]["added"], ["New headline"])

    def test_section_only_on_one_side(self):
        a, b = self.root / "a", self.root / "b"
        make_snapshot(a, "new", {"profile": "x"})
        make_snapshot(b, "new", {"profile": "x", "interests": "Canva, Company"})
        d = self._diff(a, b)
        self.assertEqual(d["sections"]["interests"]["only_in"], "b")

    def test_structured_field_change(self):
        a, b = self.root / "a", self.root / "b"
        make_snapshot(a, "new", {}, structured={"headline": "Recruiter", "skills": ["Canva"]})
        make_snapshot(b, "new", {}, structured={"headline": "SMM", "skills": ["Canva", "CapCut"]})
        d = self._diff(a, b)
        self.assertEqual(d["fields"]["headline"], {"a": "Recruiter", "b": "SMM"})
        self.assertEqual(d["fields"]["skills.1"], {"a": None, "b": "CapCut"})

    def test_no_changes(self):
        a, b = self.root / "a", self.root / "b"
        make_snapshot(a, "new", {"profile": "same"}, structured={"h": 1})
        make_snapshot(b, "new", {"profile": "same"}, structured={"h": 1})
        d = self._diff(a, b)
        self.assertEqual(d["sections"], {})
        self.assertEqual(d["fields"], {})
        md = li_diff.to_markdown(d, "a", "b")
        self.assertIn("No changes detected", md)

    def test_blank_and_duplicate_lines_normalized(self):
        a, b = self.root / "a", self.root / "b"
        make_snapshot(a, "new", {"profile": "x\n\nx\n  x  "})
        make_snapshot(b, "new", {"profile": "x"})
        self.assertEqual(self._diff(a, b)["sections"], {})


if __name__ == "__main__":
    unittest.main()
