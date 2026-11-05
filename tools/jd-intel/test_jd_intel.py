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


# An invented posting shaped like a real one: a role, requirements, a company
# pitch, a benefits list, and the legal tail every employer appends.
POSTING = {
    "title": "Platform Engineer", "company": "Example Corp",
    "location": "Riverton, Examplestate",
    "description": [
        "About Example Corp",
        "Example Corp builds tools for the future. See https://example.com/careers.",
        "About the role",
        "You will build audit trails and observability for Riverton customers.",
        "Minimum requirements",
        "Strong accountability.",
        "Experience with PostgreSQL, Kubernetes and C++.",
        "Benefits",
        "Generous parental leave",
        "Free lunches",
        "Equal opportunity statement",
        "Example Corp is an equal opportunity employer and decides regardless of "
        "race, religion or veteran status.",
        "Qualified applicants with arrest records will be considered per the "
        "Riverton Fair Chance Ordinance.",
    ],
}


class RequirementPhrasesOnly(unittest.TestCase):
    """CK-4: `cv match` printed ~300 'missing' words, mostly boilerplate."""

    def toks(self, job=POSTING):
        return set(jd_intel.requirement_tokens(job))

    def test_the_requirements_survive(self):
        self.assertTrue({"audit", "observability", "postgresql", "kubernetes",
                         "accountability", "c++"} <= self.toks())

    def test_eeo_and_legal_text_is_gone(self):
        for noise in ("veteran", "religion", "arrest", "ordinance", "fair", "chance",
                      "regardless", "opportunity", "employer"):
            self.assertNotIn(noise, self.toks(), noise)

    def test_benefits_and_the_company_pitch_are_gone(self):
        for noise in ("parental", "lunches", "generous", "future", "builds"):
            self.assertNotIn(noise, self.toks(), noise)

    def test_urls_are_not_keywords(self):
        for noise in ("https", "example.com", "careers", "example.com/careers"):
            self.assertNotIn(noise, self.toks(), noise)

    def test_the_postings_own_company_and_place_names_are_gone(self):
        for noise in ("riverton", "examplestate", "example"):
            self.assertNotIn(noise, self.toks(), noise)

    def test_no_token_ends_in_punctuation(self):
        for t in self.toks():
            self.assertRegex(t, r"[a-z0-9+#]$", t)
        self.assertIn("accountability", self.toks())       # not "accountability."

    def test_a_posting_with_no_headings_is_kept_whole(self):
        job = {"title": "Engineer", "description": [
            "Python and Postgres required.", "Experience running Kubernetes."]}
        self.assertTrue({"python", "postgres", "kubernetes"} <= self.toks(job))

    def test_a_requirement_heading_ends_a_dropped_section(self):
        job = {"title": "Engineer", "description": [
            "Benefits", "Free snacks", "What you will bring", "Rust expertise"]}
        got = self.toks(job)
        self.assertIn("rust", got)
        self.assertNotIn("snacks", got)

    def test_a_legal_sentence_is_dropped_wherever_it_sits(self):
        job = {"title": "Engineer", "description": [
            "Build services in Go.", "We consider applicants regardless of gender."]}
        self.assertNotIn("gender", self.toks(job))
        self.assertIn("services", self.toks(job))

    def test_trailing_punctuation_is_stripped_but_c_plus_plus_stays(self):
        got = jd_intel.tokens("accountability. ownership, c++")
        self.assertEqual(got, ["accountability", "ownership", "c++"])


class MissingFromCv(unittest.TestCase):
    CV = "Built audit trails on PostgreSQL. Ran Kubernetes in production."

    def test_only_requirement_words_the_cv_lacks_are_listed(self):
        missing = jd_intel.missing_from_cv(POSTING, self.CV)
        self.assertIn("observability", missing)
        self.assertNotIn("kubernetes", missing)
        self.assertNotIn("veteran", missing)
        self.assertEqual(missing, sorted(missing))

    def test_the_cli_prints_the_header_and_one_word_per_line(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cv = root / "cv.md"
            cv.write_text(self.CV)
            snap = make_job_snapshot(root / "snap", dict(POSTING, schema="li-scrape-job/1"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = jd_intel.main(["--missing", str(cv), str(snap)])
            self.assertEqual(rc, 0)
            lines = buf.getvalue().splitlines()
            self.assertEqual(lines[0], "Keywords in JD not found in CV text:")
            self.assertIn("  - observability", lines)
            self.assertTrue(all(l.startswith("  - ") for l in lines[1:]))

    def test_a_plain_text_jd_file_is_accepted(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            cv, jd = Path(d) / "cv.md", Path(d) / "jd.txt"
            cv.write_text("Python.")
            jd.write_text("Python and Rust.\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                jd_intel.main(["--missing", str(cv), str(jd)])
            self.assertIn("  - rust", buf.getvalue())
            self.assertNotIn("  - python", buf.getvalue())

    def test_a_missing_file_is_an_operational_failure(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(jd_intel.main(["--missing", "/nonexistent-cv", "/nonexistent-jd"]), 1)
            self.assertEqual(jd_intel.main(["--missing", "only-one"]), 2)


class AggregateIsScopedToTheRequirements(unittest.TestCase):
    def test_boilerplate_does_not_enter_the_corpus(self):
        terms = {t["term"] for t in jd_intel.aggregate([POSTING])["terms"]}
        self.assertIn("observability", terms)
        self.assertNotIn("veteran", terms)
        self.assertNotIn("riverton", terms)


if __name__ == "__main__":
    unittest.main()