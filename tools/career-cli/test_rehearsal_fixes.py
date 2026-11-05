"""CLI-level behaviour behind the job-hunt rehearsal fixes (CK-1, CK-3, CK-4,
CK-5). Each runs bin/career against a throwaway $CAREER_KIT_HOME with an
invented client, so nothing here needs a real client, a browser or the network.

Run: python3 -m unittest discover -s tools/career-cli
"""
import json
import unittest

import clihome


class Base(unittest.TestCase):
    def setUp(self):
        self.home = clihome.Home()
        self.addCleanup(self.home.cleanup)

    def env(self, p):
        return json.loads(p.stdout)


class JdAdd(Base):
    """CK-1: a posting that is not on LinkedIn becomes a snapshot, no login."""

    def test_a_file_becomes_a_job_snapshot_the_other_verbs_accept(self):
        snap = self.home.snapshot()
        self.assertEqual(json.loads((snap / "manifest.json").read_text())["kind"], "job")
        job = json.loads((snap / "job.json").read_text())
        self.assertEqual((job["jobId"], job["company"]), ("EX-1", "Example Corp"))
        self.home.fake_build()
        for verb in (("cv", "letter", str(snap)), ("apply", "add", str(snap))):
            with self.subTest(verb=" ".join(verb[:2])):
                p = self.home.run(*verb, "--json")
                self.assertTrue(self.env(p)["ok"], p.stdout + p.stderr)
        self.assertEqual(self.home.run("apply", "list", "--json").returncode, 0)

    def test_the_snapshot_is_a_job_for_keywords_and_not_a_profile(self):
        self.home.snapshot()
        self.home.fake_build()
        p = self.home.run("linkedin", "keywords", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.env(p)["data"]["jobs"], 1)

    def test_an_unsupported_url_is_a_usage_error_in_the_envelope(self):
        p = self.home.run("jd", "add", "https://example.com/careers/1", "--json")
        env = self.env(p)
        self.assertEqual(p.returncode, 2)
        self.assertFalse(env["ok"])
        self.assertIn("supported", env["error"]["message"])

    def test_a_file_without_company_and_title_is_a_usage_error(self):
        p = self.home.run("jd", "add", str(self.home.jd_file()), "--json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("--company", self.env(p)["error"]["message"])

    def test_no_argument_is_a_usage_error(self):
        self.assertEqual(self.home.run("jd", "add", "--json").returncode, 2)
        self.assertEqual(self.home.run("jd", "frobnicate", "--json").returncode, 2)


class NotBuiltFailsLoudly(Base):
    """CK-3: a verb that reads the built CV must say which build is missing,
    not exit 2 with nothing on stderr."""

    def check(self, *args):
        p = self.home.run(*args)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn(f"build/{clihome.CLIENT}/baseline", p.stderr)
        self.assertIn("career cv build", p.stderr)
        j = self.home.run(*args, "--json")
        self.assertEqual(j.returncode, 1)
        env = self.env(j)
        self.assertFalse(env["ok"])
        self.assertIn(f"build/{clihome.CLIENT}/baseline", env["error"]["message"])

    def test_keywords(self):
        self.home.snapshot()
        self.check("linkedin", "keywords")

    def test_letter(self):
        self.check("cv", "letter", str(self.home.snapshot()))

    def test_ats_and_match_say_to_build_first(self):
        snap = self.home.snapshot()
        for verb in (("cv", "ats"), ("cv", "match", "baseline", str(snap))):
            with self.subTest(verb=verb[1]):
                p = self.home.run(*verb)
                self.assertEqual(p.returncode, 1, p.stdout)
                self.assertIn("build baseline first", p.stderr)

    def test_a_different_variant_names_that_variant(self):
        self.home.snapshot()
        self.home.fake_build("baseline")
        p = self.home.run("linkedin", "keywords", "nope-variant")
        self.assertEqual(p.returncode, 1)
        self.assertIn(f"build/{clihome.CLIENT}/nope-variant", p.stderr)


class KeywordsAreRequirementsOnly(Base):
    """CK-4, through the CLI: `cv match` and `linkedin keywords`."""

    def test_cv_match_lists_requirement_words_and_none_of_the_boilerplate(self):
        snap = self.home.snapshot()
        self.home.fake_build()
        p = self.home.run("cv", "match", "baseline", str(snap), "--json")
        missing = self.env(p)["data"]["missing"]
        self.assertIn("observability", missing)
        self.assertNotIn("postgresql", missing)              # the CV has it
        for noise in ("opportunity", "employer", "regardless", "race", "riverton"):
            self.assertNotIn(noise, missing)
        self.assertTrue(all(w[-1].isalnum() or w[-1] in "+#" for w in missing), missing)

    def test_cv_match_still_takes_a_plain_text_jd_file(self):
        self.home.fake_build()
        p = self.home.run("cv", "match", "baseline", str(self.home.jd_file()), "--json")
        self.assertIn("observability", self.env(p)["data"]["missing"])

    def test_keywords_can_be_scoped_to_one_posting(self):
        first = self.home.snapshot()
        other = self.home.path / "clients" / clihome.CLIENT / "captures" / "2999-01-01T00-00-00Z"
        other.mkdir(parents=True)
        (other / "manifest.json").write_text(json.dumps({"kind": "job"}))
        (other / "job.json").write_text(json.dumps({
            "title": "Chef", "description": ["Sharpen knives daily."]}))
        self.home.fake_build()
        both = self.env(self.home.run("linkedin", "keywords", "--json"))["data"]
        one = self.env(self.home.run("linkedin", "keywords", "--job", str(first), "--json"))["data"]
        self.assertEqual((both["jobs"], one["jobs"]), (2, 1))
        self.assertNotIn("knives", {t["term"] for t in one["terms"]})

    def test_an_unknown_job_snapshot_is_a_usage_error(self):
        self.home.fake_build()
        p = self.home.run("linkedin", "keywords", "--job", "no-such-snapshot", "--json")
        self.assertEqual(p.returncode, 2)


class LetterFactsIncludeProjects(Base):
    """CK-5, through the CLI."""

    def test_project_bullets_are_under_facts_you_may_cite(self):
        snap = self.home.snapshot()
        self.home.fake_build()
        out = self.home.run("cv", "letter", str(snap)).stdout
        facts = out.split("FACTS YOU MAY CITE")[1].split("UNBACKED JD LANGUAGE")[0]
        self.assertIn("Project: sample-project", facts)
        self.assertIn("What it is and the interesting technical decision.", facts)


if __name__ == "__main__":
    unittest.main()
