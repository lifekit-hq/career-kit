"""Unit tests for li_audit. Run:  python3 -m unittest discover -s tools/linkedin-audit"""
import json
import tempfile
import unittest
from pathlib import Path

import li_audit

GOOD_PROFILE = "\n".join([
    "Jane Doe",
    "She/Her",
    "Social Media Manager | Short-form Video · Canva · Copywriting",
    "Dublin, County Dublin, Ireland",
    "661 followers",
    "I run social media end-to-end - the content, the short-form video, the design, and the copy every day.",
    "In every role I've had, I ran the company's social channels: planning and publishing daily content for brands.",
    "That work sat alongside a recruiting role - which trains the exact muscles social media rewards over the years.",
    "Top skills",
    "Social Media Marketing • Video Editing • Community Management",
])


def make_snapshot(root: Path, sections: dict, manifest=None, layout="new"):
    root.mkdir(parents=True, exist_ok=True)
    for name, text in sections.items():
        rel = (f"raw/{name}.txt" if layout == "new"
               else ("profile_text.txt" if name == "profile" else f"{name}.txt"))
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    if manifest is not None:
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class LiAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _statuses(self, report):
        return {r["id"]: r["status"] for r in report["checks"]}

    def test_good_profile_passes_core_checks(self):
        snap = self.root / "s"
        make_snapshot(snap, {
            "profile": GOOD_PROFILE,
            "experience": "- Ran socials end-to-end.\n- Produced Reels.\n- Grew audience.",
            "education": "Bachelor's Degree, Ukrainian Language and Literature",
            "skills": "Skills (6)\nSocial Media Marketing",
            "interests": "Digital Marketing Institute, Company\n239,628 followers",
        }, manifest={"target": "jane-doe-12345678"})
        report = li_audit.audit(snap)
        st = self._statuses(report)
        for cid in ("headline", "about", "pinned_skills", "experience_bullets",
                    "education", "interests", "dash_hygiene"):
            self.assertEqual(st[cid], "pass", cid)
        self.assertEqual(st["skill_count"], "pass")
        self.assertEqual(report["score"], "8/8")

    def test_recruiter_profile_fails(self):
        snap = self.root / "s"
        make_snapshot(snap, {
            "profile": "Jane Doe\nRecruiter at Acme\n660 followers",
            "experience": "Рекрутер\nActually no bullets here",
        }, layout="legacy")
        st = self._statuses(li_audit.audit(snap))
        self.assertEqual(st["headline"], "fail")
        self.assertEqual(st["about"], "fail")
        self.assertEqual(st["pinned_skills"], "fail")
        self.assertEqual(st["experience_bullets"], "fail")

    def test_em_dash_flagged(self):
        snap = self.root / "s"
        make_snapshot(snap, {"profile": GOOD_PROFILE + "\nI craft stories — daily."})
        st = self._statuses(li_audit.audit(snap))
        self.assertEqual(st["dash_hygiene"], "warn")

    def test_vanity_slug_detection(self):
        snap = self.root / "s"
        make_snapshot(snap, {"profile": "x"}, manifest={"target": "jane-doe-000000000"})
        report = li_audit.audit(snap)
        detail = next(r["detail"] for r in report["checks"] if r["id"] == "vanity_url")
        self.assertIn("unclaimed", detail)

    def test_followers_metric(self):
        snap = self.root / "s"
        make_snapshot(snap, {"profile": "Jane\n661 followers"})
        detail = next(r["detail"] for r in li_audit.audit(snap)["checks"]
                      if r["id"] == "followers")
        self.assertEqual(detail, "661 followers")

    def test_keywords_override(self):
        snap = self.root / "s"
        make_snapshot(snap, {"profile": "Jane\nSenior Software Engineer | .NET | Angular"})
        st_default = self._statuses(li_audit.audit(snap))
        self.assertEqual(st_default["headline"], "warn")
        st_dev = self._statuses(li_audit.audit(snap, keywords=r"engineer|\.net|angular"))
        self.assertEqual(st_dev["headline"], "pass")

    def test_experience_prose_fallback(self):
        snap = self.root / "s"
        make_snapshot(snap, {"experience": "Senior Engineer\nAcme · Full-time\nProse only."})
        (snap / "profile.json").write_text(json.dumps({"positions": [
            {"title": "Senior Engineer", "description": ["Did prose things."]},
            {"title": "Engineer", "description": ["More prose."]},
        ]}), encoding="utf-8")
        st = self._statuses(li_audit.audit(snap))
        self.assertEqual(st["experience_bullets"], "pass")

    def test_skill_count_falls_back_to_structured(self):
        snap = self.root / "s"
        make_snapshot(snap, {"skills": "no count header here"})
        (snap / "profile.json").write_text(json.dumps(
            {"skills": [{"name": f"s{i}"} for i in range(6)]}), encoding="utf-8")
        st = self._statuses(li_audit.audit(snap))
        self.assertEqual(st["skill_count"], "pass")

    def test_info_checks_never_scored(self):
        snap = self.root / "s"
        make_snapshot(snap, {"profile": "x"})
        report = li_audit.audit(snap)
        scored_ids = {r["id"] for r in report["checks"] if r["status"] in ("pass", "fail")}
        self.assertNotIn("vanity_url", scored_ids)
        self.assertNotIn("followers", scored_ids)
        self.assertNotIn("open_to_work", scored_ids)


if __name__ == "__main__":
    unittest.main()
