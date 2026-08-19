"""Unit tests for career_lint. Run:  python3 -m unittest discover -s tools/career-lint"""
import json
import tempfile
import unittest
from pathlib import Path

import career_lint

CFG = {
    "headline": "Social Media Manager | Canva",
    "experience": [
        {"key": "acme", "title": "Social Media & Recruiting", "company": "Acme",
         "start": "Jan. 2026", "end": "Present", "location": "Remote", "bullets": ["x"]},
    ],
    "education": [
        {"school": "Fake State University", "degree": "BA",
         "area": "Ukrainian Language & Literature", "dates": "2022 – 2026",
         "location": "Kyiv"},
    ],
}


def make_snapshot(root: Path, profile_text="", experience_text="", education_text="",
                  structured=None):
    (root / "raw").mkdir(parents=True, exist_ok=True)
    (root / "raw" / "profile.txt").write_text(profile_text, encoding="utf-8")
    (root / "raw" / "experience.txt").write_text(experience_text, encoding="utf-8")
    (root / "raw" / "education.txt").write_text(education_text, encoding="utf-8")
    if structured is not None:
        (root / "profile.json").write_text(json.dumps(structured), encoding="utf-8")
    return root


GOOD_STRUCTURED = {
    "positions": [{"title": "Social Media & Recruiting", "company": "Acme",
                   "dateRange": "Jan 2026 - Present"}],
    "education": [{"school": "Fake State University", "degree": "Bachelor's Degree",
                   "field": "Ukrainian Language and Literature"}],
}


class CareerLintTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _lint(self, **kw):
        snap = make_snapshot(self.root / "s", **kw)
        return {(f["status"], f["check"]): f for f in
                career_lint.lint(CFG, career_lint.load_snapshot(snap))}

    def test_clean_profile(self):
        res = self._lint(
            profile_text="Jane\nSocial Media Manager | Canva\nDublin",
            education_text="Fake State University\nUkrainian Language and Literature",
            structured=GOOD_STRUCTURED)
        statuses = {k[0] for k in res}
        self.assertEqual(statuses, {"pass"})

    def test_headline_mismatch(self):
        res = self._lint(profile_text="Jane\nRecruiter at Acme",
                         structured=GOOD_STRUCTURED)
        self.assertIn(("fail", "headline"), res)

    def test_title_mismatch(self):
        st = {"positions": [{"title": "Recruiter", "company": "Acme",
                             "dateRange": "Jan 2026 - Present"}], "education": []}
        res = self._lint(profile_text="Social Media Manager | Canva", structured=st)
        self.assertIn(("fail", "role: Social Media & Recruiting @ Acme"), res)

    def test_start_date_mismatch(self):
        st = {"positions": [{"title": "Social Media & Recruiting", "company": "Acme",
                             "dateRange": "Apr 2026 - Present"}], "education": []}
        res = self._lint(profile_text="Social Media Manager | Canva", structured=st)
        key = ("fail", "start date: Social Media & Recruiting @ Acme")
        self.assertIn(key, res)
        self.assertIn("Apr 2026", res[key]["detail"])

    def test_degree_class_mismatch(self):
        st = dict(GOOD_STRUCTURED,
                  education=[{"school": "Fake State University",
                              "degree": "Master's Degree", "field": "x"}])
        res = self._lint(
            profile_text="Social Media Manager | Canva",
            education_text="Fake State University\nUkrainian Language and Literature",
            structured=st)
        self.assertIn(("fail", "degree: Fake State University"), res)

    def test_company_missing_entirely(self):
        res = self._lint(profile_text="Social Media Manager | Canva",
                         structured={"positions": [], "education": []})
        self.assertIn(("fail", "role: Social Media & Recruiting @ Acme"), res)

    def test_company_in_text_but_not_parsed_warns(self):
        res = self._lint(profile_text="Social Media Manager | Canva",
                         experience_text="Acme things happened",
                         structured={"positions": [], "education": []})
        self.assertIn(("warn", "role: Social Media & Recruiting @ Acme"), res)

    def test_lint_aliases_match_cyrillic_company(self):
        cfg = json.loads(json.dumps(CFG))
        cfg["experience"][0]["lint_aliases"] = ["Акме"]
        st = {"positions": [{"title": "Social Media & Recruiting", "company": "Акме",
                             "dateRange": "Jan 2026 - Present"}], "education": []}
        snap = make_snapshot(self.root / "s",
                             profile_text="Social Media Manager | Canva", structured=st)
        res = {(f["status"], f["check"]) for f in
               career_lint.lint(cfg, career_lint.load_snapshot(snap))}
        self.assertIn(("pass", "role: Social Media & Recruiting @ Acme"), res)

    def test_norm_and_degree_class(self):
        self.assertEqual(career_lint.norm("Ukrainian Language & Literature"),
                         "ukrainian language and literature")
        self.assertEqual(career_lint.degree_class("BA"), "bachelor")
        self.assertEqual(career_lint.degree_class("Bachelor's Degree"), "bachelor")
        self.assertEqual(career_lint.degree_class("MSc"), "master")
        self.assertIsNone(career_lint.degree_class("Diploma"))


if __name__ == "__main__":
    unittest.main()
