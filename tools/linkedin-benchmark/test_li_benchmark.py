"""Unit tests for li_benchmark. Run:  python3 -m unittest discover -s tools/linkedin-benchmark"""
import json
import tempfile
import unittest
from pathlib import Path

import li_benchmark


def make_ref(root: Path, headline: str, skills: list[str], layout="new"):
    root.mkdir(parents=True, exist_ok=True)
    text = f"Jane Doe\n{headline}\nDublin, Ireland\n500 followers"
    if layout == "new":
        (root / "raw").mkdir(exist_ok=True)
        (root / "raw" / "profile.txt").write_text(text, encoding="utf-8")
        (root / "profile.json").write_text(
            json.dumps({"skills": [{"name": s} for s in skills]}), encoding="utf-8")
    else:
        (root / "profile_text.txt").write_text(text, encoding="utf-8")
        (root / "profile_structured.json").write_text(
            json.dumps({"skills": skills}), encoding="utf-8")
    return root


class LiBenchmarkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_aggregates_across_profiles(self):
        a = make_ref(self.root / "a", "Social Media Manager | Paid Social",
                     ["Canva", "Copywriting"])
        b = make_ref(self.root / "b", "Social Media Manager | Content Strategy",
                     ["Canva", "Analytics"], layout="legacy")
        r = li_benchmark.benchmark([a, b])
        self.assertEqual(r["profiles"], 2)
        self.assertEqual(len(r["headlines"]), 2)
        skills = {s["skill"]: s["profiles"] for s in r["skills"]}
        self.assertEqual(skills["canva"], 2)
        self.assertEqual(skills["analytics"], 1)
        kws = {t["term"]: t["profiles"] for t in r["headline_keywords"]}
        self.assertEqual(kws["social"], 2)
        self.assertEqual(kws["paid"], 1)
        self.assertEqual(r["pipe_headline_share"], 1.0)

    def test_profile_without_headline(self):
        a = make_ref(self.root / "a", "just a plain line", [])
        r = li_benchmark.benchmark([a])
        self.assertEqual(r["headlines"], [])
        self.assertEqual(r["pipe_headline_share"], 0)

    def test_markdown_report(self):
        a = make_ref(self.root / "a", "Social Media Manager | Reels", ["CapCut"])
        r = li_benchmark.benchmark([a])
        md = li_benchmark.to_markdown(r, [str(a)])
        self.assertIn("Social Media Manager | Reels", md)
        self.assertIn("capcut (1/1)", md)


if __name__ == "__main__":
    unittest.main()
