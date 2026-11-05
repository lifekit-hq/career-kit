"""Unit tests for jd_add. Run: python3 -m unittest discover -s tools/jd-add

Every posting here is invented (Example Corp / Acme): the API payloads mirror the
shape the three boards publish, and nothing touches the network.
"""
import datetime
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import jd_add

NOW = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
ASHBY_ID = "c3f1a9b2-1111-4222-8333-444455556666"
LEVER_ID = "e7a20d4c-1111-4222-8333-444455556666"

ASHBY_BOARD = {"jobs": [
    {"id": "00000000-0000-4000-8000-000000000000", "title": "Other Role",
     "location": "Nowhere", "descriptionPlain": "Not this one."},
    {"id": ASHBY_ID, "title": "Platform Engineer", "location": "Dublin, Ireland",
     "jobUrl": f"https://jobs.ashbyhq.com/example-corp/{ASHBY_ID}",
     "descriptionPlain": "About the role\n\nYou will build audit trails.\n\n"
                         "Minimum requirements\n\nPython and Postgres.\n"},
]}
GREENHOUSE_JOB = {
    "id": 4242, "title": "Backend Engineer", "company_name": "Example Corp",
    "location": {"name": "Remote, EU"},
    "absolute_url": "https://boards.greenhouse.io/examplecorp/jobs/4242",
    # Greenhouse entity-escapes its HTML a second time.
    "content": "&lt;p&gt;Build &amp;amp; run services.&lt;/p&gt;"
               "&lt;ul&gt;&lt;li&gt;Go or Python&lt;/li&gt;&lt;li&gt;Kubernetes&lt;/li&gt;&lt;/ul&gt;",
}
LEVER_JOB = {
    "id": LEVER_ID, "text": "Site Reliability Engineer",
    "categories": {"location": "London"},
    "hostedUrl": f"https://jobs.lever.co/example-corp/{LEVER_ID}",
    "descriptionPlain": "Keep the platform up.",
    "lists": [{"text": "What you will do:", "content": "<li>Own on-call</li><li>Write runbooks</li>"}],
    "additionalPlain": "We value clear writing.",
}


def fake_fetch(url):
    if "api.ashbyhq.com" in url:
        return ASHBY_BOARD
    if "boards-api.greenhouse.io" in url:
        return GREENHOUSE_JOB
    if "api.lever.co" in url:
        return LEVER_JOB
    raise AssertionError(f"unexpected fetch: {url}")


class Args:
    company = title = location = id = source = None

    def __init__(self, **kw):
        self.__dict__.update(kw)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.captures = Path(self.tmp.name) / "captures"

    def add(self, ref, **kw):
        return jd_add.add(self.captures, ref, Args(**kw), fake_fetch, NOW)

    def job(self, out):
        return json.loads((Path(out["snapshot"]) / "job.json").read_text())


class UrlParsing(unittest.TestCase):
    def test_the_three_boards(self):
        self.assertEqual(jd_add.parse_url(f"https://jobs.ashbyhq.com/acme/{ASHBY_ID}"),
                         ("ashby", "acme", ASHBY_ID))
        self.assertEqual(jd_add.parse_url(f"https://jobs.ashbyhq.com/acme/{ASHBY_ID}/application?utm=x"),
                         ("ashby", "acme", ASHBY_ID))
        self.assertEqual(jd_add.parse_url("https://boards.greenhouse.io/acme/jobs/123"),
                         ("greenhouse", "acme", "123"))
        self.assertEqual(jd_add.parse_url("https://job-boards.greenhouse.io/acme/jobs/123?gh_src=x"),
                         ("greenhouse", "acme", "123"))
        self.assertEqual(jd_add.parse_url(f"https://jobs.lever.co/acme/{LEVER_ID}"),
                         ("lever", "acme", LEVER_ID))

    def test_anything_else_is_not_supported(self):
        for url in ("https://example.com/jobs/1", "http://jobs.lever.co/acme/" + LEVER_ID,
                    "https://jobs.lever.co.evil.test/acme/" + LEVER_ID,
                    "https://boards.greenhouse.io/acme/jobs/abc",
                    "https://www.linkedin.com/jobs/view/123456789/"):
            self.assertIsNone(jd_add.parse_url(url), url)


class FromTheBoards(Base):
    def test_ashby_posting_becomes_a_job_snapshot(self):
        out = self.add(f"https://jobs.ashbyhq.com/example-corp/{ASHBY_ID}")
        job = self.job(out)
        self.assertEqual(job["schema"], "li-scrape-job/1")
        self.assertEqual(job["jobId"], "ashby-c3f1a9b2")
        self.assertEqual((job["title"], job["company"], job["location"]),
                         ("Platform Engineer", "Example Corp", "Dublin, Ireland"))
        self.assertTrue(job["source"].startswith("https://jobs.ashbyhq.com/"))
        self.assertIn("You will build audit trails.", job["description"])

    def test_greenhouse_unescapes_and_splits_the_html(self):
        job = self.job(self.add("https://boards.greenhouse.io/examplecorp/jobs/4242"))
        self.assertEqual(job["jobId"], "4242")
        self.assertEqual(job["company"], "Example Corp")
        self.assertEqual(job["description"],
                         ["Build & run services.", "Go or Python", "Kubernetes"])

    def test_lever_joins_description_lists_and_additional(self):
        job = self.job(self.add(f"https://jobs.lever.co/example-corp/{LEVER_ID}"))
        self.assertEqual(job["jobId"], "lever-e7a20d4c")
        self.assertEqual(job["title"], "Site Reliability Engineer")
        self.assertEqual(job["description"], [
            "Keep the platform up.", "What you will do:", "Own on-call",
            "Write runbooks", "We value clear writing."])

    def test_the_snapshot_layout_matches_what_linkedin_jd_writes(self):
        out = self.add(f"https://jobs.ashbyhq.com/example-corp/{ASHBY_ID}")
        snap = Path(out["snapshot"])
        self.assertEqual(snap.name, "2026-01-02T03-04-05Z")
        manifest = json.loads((snap / "manifest.json").read_text())
        self.assertEqual(manifest["kind"], "job")
        self.assertIs(manifest["legacy"], False)
        self.assertTrue((snap / "raw" / "job.txt").is_file())
        self.assertEqual(json.loads((snap / "raw" / "api.json").read_text())["id"], ASHBY_ID)

    def test_a_second_snapshot_in_the_same_second_gets_its_own_dir(self):
        a = self.add("https://boards.greenhouse.io/examplecorp/jobs/4242")
        b = self.add("https://boards.greenhouse.io/examplecorp/jobs/4242")
        self.assertNotEqual(a["snapshot"], b["snapshot"])

    def test_flags_override_the_board(self):
        job = self.job(self.add(f"https://jobs.ashbyhq.com/example-corp/{ASHBY_ID}",
                                company="Example Corp Ltd", id="X-1"))
        self.assertEqual((job["company"], job["jobId"]), ("Example Corp Ltd", "X-1"))

    def test_a_posting_the_board_does_not_list_fails(self):
        with self.assertRaises(jd_add.Failure):
            self.add("https://jobs.ashbyhq.com/example-corp/99999999-1111-4222-8333-444455556666")


class FromAFile(Base):
    def write(self, name, text):
        p = Path(self.tmp.name) / name
        p.write_text(text)
        return str(p)

    def test_a_text_file_needs_company_and_title(self):
        f = self.write("jd.txt", "Build things.\n")
        with self.assertRaises(jd_add.Usage):
            self.add(f)
        with self.assertRaises(jd_add.Usage):
            self.add(f, company="Example Corp")

    def test_a_text_file_becomes_a_snapshot_without_an_invented_id(self):
        f = self.write("jd.txt", "Build things.\n\nRun them.\n")
        job = self.job(self.add(f, company="Example Corp", title="Engineer",
                                location="Dublin", source="https://example.com/j/1"))
        self.assertNotIn("jobId", job)
        self.assertEqual(job["description"], ["Build things.", "Run them."])
        self.assertEqual(job["source"], "https://example.com/j/1")

    def test_an_id_flag_sets_the_vacancy_id(self):
        f = self.write("jd.txt", "Build things.\n")
        job = self.job(self.add(f, company="Example Corp", title="Engineer", id="EX-9"))
        self.assertEqual(job["jobId"], "EX-9")

    def test_html_files_are_converted(self):
        f = self.write("jd.html", "<h2>Role</h2><p>Build <b>things</b>.</p><li>Python</li>")
        job = self.job(self.add(f, company="Example Corp", title="Engineer"))
        self.assertEqual(job["description"], ["Role", "Build things.", "Python"])

    def test_missing_file_and_unsupported_url_are_usage_errors(self):
        with self.assertRaises(jd_add.Usage):
            self.add(str(Path(self.tmp.name) / "nope.txt"))
        with self.assertRaises(jd_add.Usage):
            self.add("https://example.com/careers/1")


class Cli(Base):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = jd_add.main([str(self.captures), *argv], fetch=fake_fetch, now=NOW)
        return rc, out.getvalue(), err.getvalue()

    def test_json_mode_prints_one_object(self):
        rc, out, _ = self.run_main("https://boards.greenhouse.io/examplecorp/jobs/4242", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["jobId"], "4242")

    def test_text_mode_prints_the_snapshot_path(self):
        rc, out, _ = self.run_main("https://boards.greenhouse.io/examplecorp/jobs/4242")
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("→ "))

    def test_exit_codes(self):
        self.assertEqual(self.run_main("https://example.com/x")[0], 2)
        self.assertEqual(self.run_main("--no-such-flag", "x")[0], 2)
        rc, _, err = self.run_main("https://jobs.ashbyhq.com/example-corp/"
                                   "99999999-1111-4222-8333-444455556666")
        self.assertEqual(rc, 1)
        self.assertIn("does not list", err)


class Downstream(Base):
    """The done-when: `cv letter`, `cv version` and `apply add` take the snapshot."""

    def test_the_other_verbs_read_the_snapshot(self):
        out = self.add(f"https://jobs.ashbyhq.com/example-corp/{ASHBY_ID}")
        snap = Path(out["snapshot"])
        import sys
        root = Path(__file__).resolve().parents[2]
        for tool in ("career-letter", "career-apply", "career-version", "jd-intel"):
            sys.path.insert(0, str(root / "tools" / tool))
        import career_apply
        import career_version
        import jd_intel
        job = jd_intel.load_job(snap)
        self.assertEqual(job["title"], "Platform Engineer")
        self.assertEqual(career_apply.read_job(snap)["jobId"], "ashby-c3f1a9b2")
        self.assertEqual(career_version.read_job(snap)["company"], "Example Corp")
        app = career_version.application_dir(Path(self.tmp.name), job, None)
        self.assertEqual(app.name, "ashby-c3f1a9b2-platform-engineer")


if __name__ == "__main__":
    unittest.main()
