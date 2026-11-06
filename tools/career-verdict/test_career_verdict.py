"""Unit tests for career_verdict. Run: python3 -m unittest discover -s tools/career-verdict"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "career-version"))
import career_verdict                                       # noqa: E402
import career_version                                       # noqa: E402

JOB = {"schema": "li-scrape-job/1", "jobId": "EX-1", "title": "Platform Engineer",
       "company": "Example Corp"}
TODAY = "2026-09-07"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.client = root / "clients" / "sample"
        self.variant = self.client / "variants" / "acme.yml"
        self.variant.parent.mkdir(parents=True)
        self.variant.write_text("headline: Engineer\n")
        self.build = root / "build" / "sample" / "acme"
        self.build.mkdir(parents=True)
        (self.build / "Sample_CV.pdf").write_bytes(b"%PDF")
        (self.build / "Sample_CV.md").write_text("# CV\n")
        (self.build / "Sample_CV_1.png").write_bytes(b"")
        self.snap = self.snapshot("2026-09-07T18-18-04Z", JOB)

    def snapshot(self, name, job):
        snap = self.client / "captures" / name
        snap.mkdir(parents=True)
        (snap / "job.json").write_text(json.dumps(job))
        return snap

    def freeze(self, snap=None):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(career_version.main(
                [str(self.client), str(self.variant), str(snap or self.snap),
                 str(self.build)], today=TODAY), 0)

    def verdict(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = career_verdict.main([str(self.client), *argv, "--json"])
        text = out.getvalue().strip()
        return code, (json.loads(text) if code == 0 and text else err.getvalue())

    @property
    def app(self):
        return self.client / "applications" / "example-corp" / "ex-1-platform-engineer"


class Record(Base):
    def test_one_call_writes_the_same_verdict_to_review_and_versions(self):
        self.freeze()
        code, d = self.verdict("v1", "submittable")
        self.assertEqual((code, d["verdict"]), (0, "submittable"))
        self.assertIn("\nVerdict: submittable\n", (self.app / "v1" / "REVIEW.md").read_text())
        versions = (self.app / "VERSIONS.md").read_text()
        self.assertIn(f"| v1 | {TODAY} | acme | submittable |", versions)
        self.assertNotIn("(pending review)", versions)

    def test_review_prose_above_the_verdict_is_untouched(self):
        self.freeze()
        review = self.app / "v1" / "REVIEW.md"
        review.write_text(review.read_text().replace(
            "## Grounding\n", "## Grounding\n\nEvery bullet traces to the profile.\n"))
        self.verdict("v1", "submittable")
        self.assertIn("Every bullet traces to the profile.", review.read_text())

    def test_confirm_is_stored_in_words_and_carries_its_note(self):
        self.freeze()
        self.verdict("v1", "confirm", "--note", "Confirm: the audit-trail phrasing.")
        review = (self.app / "v1" / "REVIEW.md").read_text()
        self.assertIn("Verdict: submittable with confirmations", review)
        self.assertIn("Confirm: the audit-trail phrasing.", review)
        self.assertIn("| submittable with confirmations |", (self.app / "VERSIONS.md").read_text())

    def test_only_the_named_version_changes(self):
        self.freeze(); self.freeze()
        self.verdict("v2", "rejected")
        versions = (self.app / "VERSIONS.md").read_text()
        self.assertIn("| v1 |", versions)
        self.assertIn(f"| v1 | {TODAY} | acme | (pending review) |", versions)
        self.assertIn(f"| v2 | {TODAY} | acme | rejected |", versions)
        self.assertIn("Verdict: \n", (self.app / "v1" / "REVIEW.md").read_text())

    def test_a_later_verdict_replaces_the_earlier_one_and_its_note(self):
        self.freeze()
        self.verdict("v1", "confirm", "--note", "Confirm the first thing.")
        self.verdict("v1", "submittable")
        review = (self.app / "v1" / "REVIEW.md").read_text()
        self.assertEqual(review.count("Verdict:"), 1)
        self.assertNotIn("Confirm the first thing", review)
        self.assertIn("| submittable |", (self.app / "VERSIONS.md").read_text())

    def test_frozen_artifacts_are_not_touched(self):
        self.freeze()
        before = {p.name: p.read_bytes() for p in (self.app / "v1").iterdir()
                  if p.name != "REVIEW.md"}
        self.verdict("v1", "rejected")
        after = {p.name: p.read_bytes() for p in (self.app / "v1").iterdir()
                 if p.name != "REVIEW.md"}
        self.assertEqual(before, after)


class FindingTheApplication(Base):
    def test_a_version_that_exists_in_one_application_needs_no_selector(self):
        self.freeze()
        self.assertEqual(self.verdict("v1", "submittable")[0], 0)

    def test_a_version_in_several_applications_demands_a_selector(self):
        self.freeze()
        other = self.snapshot("2026-09-08T10-00-00Z", {**JOB, "jobId": "EX-2"})
        self.freeze(other)
        code, msg = self.verdict("v1", "submittable")
        self.assertEqual(code, 2)
        self.assertIn("--jd", msg)
        self.assertIn("example-corp/ex-2-platform-engineer", msg)
        code, d = self.verdict("v1", "submittable", "--jd", str(other))
        self.assertEqual(d["application"], "applications/example-corp/ex-2-platform-engineer")
        self.assertIn("(pending review)", (self.app / "VERSIONS.md").read_text())
        code, d = self.verdict("v1", "rejected", "--app", "example-corp/ex-1-platform-engineer")
        self.assertEqual(code, 0)
        self.assertIn("| rejected |", (self.app / "VERSIONS.md").read_text())

    def test_unknown_inputs_are_usage_errors(self):
        self.freeze()
        for argv in (("v9", "submittable"), ("v1", "maybe"), ("1", "submittable"),
                     ("v1", "submittable", "--app", "nope/nope"),
                     ("v1", "submittable", "--jd", "no-such-snapshot")):
            with self.subTest(argv=argv):
                self.assertEqual(self.verdict(*argv)[0], 2)

    def test_a_versions_file_without_the_row_fails_and_changes_nothing(self):
        self.freeze()
        versions = self.app / "VERSIONS.md"
        versions.write_text("# header only\n")
        review = (self.app / "v1" / "REVIEW.md").read_text()
        self.assertEqual(self.verdict("v1", "submittable")[0], 1)
        self.assertEqual((self.app / "v1" / "REVIEW.md").read_text(), review)


if __name__ == "__main__":
    unittest.main()
