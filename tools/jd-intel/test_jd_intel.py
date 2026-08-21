"""Unit tests for jd_intel. Run:  python3 -m unittest discover -s tools/jd-intel"""
import json
import tempfile
import unittest
from pathlib import Path

import jd_intel

JOB_A = {"schema": "li-scrape-job/1", "title": "Social Media Executive",
         "description": ["Run Instagram and TikTok channels.",
                         "Plan the content calendar with Canva."]}
JOB_B = {"schema": "li-scrape-job/1", "title": "Social Media Coordinator",
         "description": ["Own the content calendar and paid social.",
                         "Report on Instagram analytics."]}


def make_job_snapshot(root: Path, job: dict):
    root.mkdir(parents=True, exist_ok=True)
    (root / "job.json").write_text(json.dumps(job), encoding="utf-8")
    return root


class JdIntelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tokens_filter_stopwords(self):
        self.assertEqual(jd_intel.tokens("You will run the Instagram channel"),
                         ["run", "instagram", "channel"])

    def test_unigram_document_frequency(self):
        report = jd_intel.aggregate([JOB_A, JOB_B])
        by_term = {t["term"]: t for t in report["terms"]}
        self.assertEqual(by_term["instagram"]["jobs"], 2)
        self.assertEqual(by_term["tiktok"]["jobs"], 1)
        self.assertEqual(report["jobs"], 2)

    def test_repeated_bigrams_kept(self):
        report = jd_intel.aggregate([JOB_A, JOB_B])
        bigrams = [t["term"] for t in report["terms"] if t["jobs"] is None]
        self.assertIn("social media", bigrams)
        self.assertIn("content calendar", bigrams)
        self.assertNotIn("paid social", bigrams)  # appears once only

    def test_cv_matching(self):
        cv = "Social media manager. Runs Instagram. Content calendars in Canva."
        report = jd_intel.aggregate([JOB_A, JOB_B], cv_text=cv)
        by_term = {t["term"]: t for t in report["terms"]}
        self.assertTrue(by_term["instagram"]["in_cv"])
        self.assertFalse(by_term["tiktok"]["in_cv"])
        self.assertFalse(by_term["analytics"]["in_cv"])

    def test_sorted_by_frequency(self):
        report = jd_intel.aggregate([JOB_A, JOB_B])
        freqs = [t["jobs"] or 0 for t in report["terms"] if t["jobs"] is not None]
        self.assertEqual(freqs, sorted(freqs, reverse=True))

    def test_load_job_and_markdown(self):
        snap = make_job_snapshot(self.root / "s", JOB_A)
        job = jd_intel.load_job(snap)
        self.assertEqual(job["title"], "Social Media Executive")
        report = jd_intel.aggregate([job], cv_text="nothing relevant")
        md = jd_intel.to_markdown(report, [str(snap)])
        self.assertIn("Missing from the CV", md)
        self.assertIn("instagram", md)

    def test_missing_job_json(self):
        self.assertIsNone(jd_intel.load_job(self.root))



class JobTextShape(unittest.TestCase):
    """description is a list of lines in li-scrape-job/1, but a string must not
    silently degrade to zero keywords - list("abc") is three 1-char tokens, all
    of which the tokenizer then drops. See #21."""

    def test_a_list_description_is_read(self):
        self.assertIn("kubernetes", jd_intel.tokens(
            jd_intel.job_text({"title": "Eng", "description": ["Kubernetes here"]})))

    def test_a_string_description_is_read_too(self):
        self.assertIn("kubernetes", jd_intel.tokens(
            jd_intel.job_text({"title": "Eng", "description": "Kubernetes here"})))

    def test_a_missing_description_still_yields_the_title(self):
        self.assertIn("engineer", jd_intel.tokens(
            jd_intel.job_text({"title": "Engineer"})))


if __name__ == "__main__":
    unittest.main()