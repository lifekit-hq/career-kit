"""Unit tests for career_lint. Run:  python3 -m unittest discover -s tools/career-lint"""
import contextlib
import io
import json
import tempfile
import unittest
from datetime import date
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

    def _lint(self, cfg=None, tailored=False, **kw):
        snap = make_snapshot(self.root / "s", **kw)
        return {(f["status"], f["check"]): f for f in
                career_lint.lint(cfg or CFG, career_lint.load_snapshot(snap), tailored)}

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

    # The role noun (before the first '|') is fixed everywhere; the modifiers
    # after it are per-variant framing. See issue #16.
    def test_role_noun(self):
        self.assertEqual(career_lint.role_noun("Social Media Manager | Canva · Reels"),
                         "Social Media Manager")
        self.assertEqual(career_lint.role_noun("Recruiter"), "Recruiter")
        self.assertEqual(career_lint.role_noun(None), "")

    def test_tailored_headline_warns_when_only_modifiers_differ(self):
        cfg = dict(CFG, headline="Social Media Manager | Instagram & LinkedIn")
        res = self._lint(cfg=cfg, tailored=True, profile_text="Jane\nSocial Media Manager | Canva",
                         structured=GOOD_STRUCTURED)
        self.assertIn(("warn", "headline"), res)
        self.assertNotIn(("fail", "headline"), res)

    def test_untailored_headline_still_fails_when_modifiers_differ(self):
        cfg = dict(CFG, headline="Social Media Manager | Instagram & LinkedIn")
        res = self._lint(cfg=cfg, tailored=False, profile_text="Jane\nSocial Media Manager | Canva",
                         structured=GOOD_STRUCTURED)
        self.assertIn(("fail", "headline"), res)

    def test_tailored_headline_still_fails_when_the_role_noun_differs(self):
        cfg = dict(CFG, headline="Head of Social | Canva")
        res = self._lint(cfg=cfg, tailored=True, profile_text="Jane\nSocial Media Manager | Canva",
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


class SnapshotAge(unittest.TestCase):
    """CK-10: the comparison is only as good as the capture."""
    TODAY = date(2026, 11, 6)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def snap(self, name="2026-08-19T14-50-08Z", manifest=None):
        d = self.root / name
        d.mkdir()
        if manifest is not None:
            (d / "manifest.json").write_text(json.dumps(manifest))
        return d

    def test_an_old_snapshot_warns_with_its_age_and_the_fix(self):
        f, age = career_lint.age_finding(self.snap(), self.TODAY)
        self.assertEqual((f["status"], age), ("warn", 79))
        self.assertIn("79 days old", f["detail"])
        self.assertIn("career linkedin capture", f["detail"])

    def test_a_recent_snapshot_passes(self):
        f, age = career_lint.age_finding(self.snap("2026-11-01T10-00-00Z"), self.TODAY)
        self.assertEqual((f["status"], age), ("pass", 5))

    def test_the_manifest_date_wins_over_the_directory_name(self):
        d = self.snap(manifest={"captured_at": "2026-11-05T09:30:00+00:00"})
        self.assertEqual(career_lint.age_finding(d, self.TODAY)[1], 1)

    def test_an_undatable_snapshot_says_so_instead_of_passing(self):
        f, age = career_lint.age_finding(self.snap("legacy"), self.TODAY)
        self.assertEqual((f["status"], age), ("warn", None))

    def test_a_stale_warning_never_fails_the_lint(self):
        profile = self.root / "profile.yml"
        profile.write_text("name: Jane\nheadline: Social Media Manager | Canva\n"
                           "experience: []\neducation: []\n")
        snap = make_snapshot(self.snap(), profile_text="Social Media Manager | Canva")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = career_lint.main([str(profile), str(snap), "--json"], today=self.TODAY)
        data = json.loads(out.getvalue())
        self.assertEqual((rc, data["failed"], data["snapshot_age_days"]), (0, 0, 79))
        self.assertEqual(data["findings"][0]["check"], "snapshot age")

    def test_a_variant_is_what_gets_linted_and_is_named(self):
        profile = self.root / "profile.yml"
        profile.write_text("name: Jane\nheadline: Social Media Manager | Canva\n"
                           "experience: []\neducation: []\n")
        variant = self.root / "acme.yml"
        variant.write_text("headline: Head of Social | Canva\n")
        snap = make_snapshot(self.snap(), profile_text="Social Media Manager | Canva")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = career_lint.main([str(profile), str(snap), "--variant", str(variant),
                                   "--json"], today=self.TODAY)
        data = json.loads(out.getvalue())
        self.assertEqual((rc, data["variant"]), (1, "acme"))     # the variant's headline fails
        self.assertIn("Head of Social", json.dumps(data["findings"]))


if __name__ == "__main__":
    unittest.main()
