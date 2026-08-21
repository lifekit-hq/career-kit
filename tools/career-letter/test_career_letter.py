"""Unit tests for career_letter. Run: python3 -m unittest discover -s tools/career-letter"""
import json
import tempfile
import unittest
from pathlib import Path

import career_letter as cl

JOB = {"schema": "li-scrape-job/1", "jobId": "1", "title": "Social Media Manager",
       "company": "Pardgroup", "location": "Dublin, Ireland",
       "source": "https://www.linkedin.com/jobs/view/1/",
       # li-scrape-job/1 stores the description as a list of lines.
       "description": ["Own Instagram content.",
                       "Run paid Marketo campaigns across our dynamic Italy and "
                       "Dubai offices.", "Kubernetes a plus."]}

PROFILE = {
    "name": "Ada Lovelace", "headline": "Social Media Manager", "location": "Dublin",
    "contacts": [{"href": "mailto:ada@example.com", "label": "ada@example.com"}],
    "summary": "Runs social channels.",
    "sections": ["profile", "experience"],
    "experience": [{"key": "acme", "title": "Social Media Manager", "company": "Acme",
                    "start": "Jan. 2024", "end": "Present", "location": "Dublin",
                    "bullets": ["Owned Instagram content end to end."]}],
    "skills": [{"group": "Tools", "items": "Canva"}],
}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.profile = root / "profile.yml"
        self.profile.write_text(json.dumps(PROFILE))     # JSON is valid YAML
        self.snap = root / "captures" / "snap"
        self.snap.mkdir(parents=True)
        (self.snap / "job.json").write_text(json.dumps(JOB))

    def build(self, **kw):
        return cl.build(self.profile, self.snap, **kw)


class Grounding(Base):
    def test_evidence_quotes_the_cv_verbatim(self):
        pack = self.build()
        self.assertEqual(pack["evidence"]["roles"][0]["bullets"],
                         PROFILE["experience"][0]["bullets"])

    def test_jd_language_the_cv_backs_is_matched(self):
        self.assertIn("instagram", self.build()["signals"]["matched"])

    def test_jd_language_the_cv_does_not_back_is_flagged(self):
        # Marketo and Kubernetes appear nowhere in the CV: claiming either is
        # the exact fabrication a work trial exposes.
        unev = self.build()["signals"]["unevidenced"]
        self.assertIn("marketo", unev)
        self.assertIn("kubernetes", unev)

    def test_the_employers_own_name_and_places_are_not_do_not_claim_items(self):
        unev = self.build()["signals"]["unevidenced"]
        for noise in ("pardgroup", "dublin", "dynamic"):
            self.assertNotIn(noise, unev)
        self.assertGreater(self.build()["signals"]["noise_filtered"], 0)

    def test_a_bare_capture_timestamp_resolves_as_it_does_for_apply_add(self):
        # Two verbs taking the same argument must not disagree on its shape.
        pack = cl.build(self.profile, Path("snap"))
        self.assertEqual(pack["job"]["company"], "Pardgroup")

    def test_the_scaffold_carries_no_claim_of_its_own(self):
        # Everything factual in it comes from the profile or the job posting.
        s = self.build()["scaffold"]
        self.assertIn("Pardgroup", s)
        self.assertIn("Ada Lovelace", s)
        self.assertIn("[OPENING", s)

    def test_a_variant_reframes_what_the_letter_may_stand_on(self):
        v = Path(self.tmp.name) / "v.yml"
        v.write_text(json.dumps({"experience_overrides":
                                 {"acme": {"bullets": ["Ran paid Marketo campaigns."]}}}))
        unev = self.build(variant_path=v)["signals"]["unevidenced"]
        self.assertNotIn("marketo", unev)      # now evidenced, so claimable


class Hygiene(Base):
    def test_model_unicode_is_folded_out_of_the_pack(self):
        p = json.loads(self.profile.read_text())
        p["summary"] = "Runs social​ channels."
        self.profile.write_text(json.dumps(p))
        self.assertEqual(self.build()["evidence"]["summary"], "Runs social channels.")

    def test_a_latin_confusable_stops_the_pack(self):
        p = json.loads(self.profile.read_text())
        p["name"] = "Adа Lovelace"
        self.profile.write_text(json.dumps(p))
        with self.assertRaises(SystemExit):
            self.build()


class Errors(Base):
    def test_a_snapshot_without_job_json_is_a_usage_error(self):
        bare = Path(self.tmp.name) / "captures" / "profile-snap"
        bare.mkdir(parents=True)
        with self.assertRaises(cl.Usage):
            cl.build(self.profile, bare)

    def test_exit_code_2_for_a_bad_snapshot(self):
        import contextlib
        import io
        bare = Path(self.tmp.name) / "nope"
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cl.main([str(self.profile), str(bare), "--json"]), 2)


if __name__ == "__main__":
    unittest.main()
