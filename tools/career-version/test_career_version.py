"""Unit tests for career_version. Run: python3 -m unittest discover -s tools/career-version"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import career_version

JOB = {"schema": "li-scrape-job/1", "jobId": "123",
       "source": "https://example.com/jobs/123",
       "title": "Software Engineer, Privacy Engineering (Lawful Access)",
       "company": "Acme Corp", "location": "Dublin, Ireland"}
TODAY = "2026-09-07"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.client = root / "clients" / "sample"
        self.snap = self.client / "captures" / "2026-09-07T18-18-04Z"
        self.snap.mkdir(parents=True)
        (self.snap / "job.json").write_text(json.dumps(JOB))
        self.variant = self.client / "variants" / "acme.yml"
        self.variant.parent.mkdir()
        self.variant.write_text("headline: Engineer\n")
        self.build = root / "build" / "sample" / "acme"
        self.build.mkdir(parents=True)
        (root / "build" / "sample" / "acme.rendercv.yaml").write_text("cv: {}\n")
        self.render_pages(1)

    def render_pages(self, n):
        for p in self.build.glob("*_CV_*.png"):
            p.unlink()
        (self.build / "Sample_CV.pdf").write_bytes(b"%PDF")
        (self.build / "Sample_CV.md").write_text("# CV\n")
        for i in range(1, n + 1):
            (self.build / f"Sample_CV_{i}.png").write_bytes(b"")

    def run_cli(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = career_version.main(
                [str(self.client), str(self.variant), str(self.snap), str(self.build),
                 *extra, "--json"], today=TODAY)
        text = out.getvalue().strip()
        return code, (json.loads(text) if code == 0 and text else err.getvalue())

    @property
    def app(self):
        return (self.client / "applications" / "acme-corp"
                / "123-software-engineer-privacy-engineering-lawful-access")


class Freeze(Base):
    def test_folder_is_company_then_vacancy_id_and_kebab_title(self):
        code, d = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(d["application"],
                         "applications/acme-corp/123-software-engineer-privacy-engineering-lawful-access")
        self.assertTrue((self.app / "v1").is_dir())

    def test_a_version_holds_the_variant_the_merged_input_the_pdf_the_ats_text_and_a_review(self):
        _, d = self.run_cli()
        self.assertEqual(d["files"],
                         ["CV.md", "CV.pdf", "REVIEW.md", "cv.rendercv.yaml", "variant.yml"])
        self.assertEqual((self.app / "v1" / "variant.yml").read_text(), "headline: Engineer\n")

    def test_versions_increment_and_never_overwrite(self):
        self.run_cli()
        self.variant.write_text("headline: Better\n")
        _, d = self.run_cli()
        self.assertEqual(d["version"], "v2")
        self.assertEqual((self.app / "v1" / "variant.yml").read_text(), "headline: Engineer\n")
        self.assertEqual((self.app / "v2" / "variant.yml").read_text(), "headline: Better\n")

    def test_review_skeleton_has_both_review_sections_and_an_empty_verdict(self):
        self.run_cli()
        review = (self.app / "v1" / "REVIEW.md").read_text()
        for needle in ("## Grounding", "## Credibility", "Verdict: \n"):
            self.assertIn(needle, review)

    def test_versions_index_gets_a_header_once_and_a_row_per_version(self):
        self.run_cli(); self.run_cli()
        text = (self.app / "VERSIONS.md").read_text()
        self.assertEqual(text.count("| version |"), 1)
        self.assertIn(f"| v1 | {TODAY} | acme |", text)
        self.assertIn(f"| v2 | {TODAY} | acme |", text)

    def test_a_bare_capture_timestamp_resolves(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = career_version.main(
                [str(self.client), str(self.variant), "2026-09-07T18-18-04Z",
                 str(self.build), "--json"], today=TODAY)
        self.assertEqual(code, 0)


class Refusals(Base):
    def test_two_pages_is_an_operational_failure_not_a_version(self):
        self.render_pages(2)
        code, err = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("2 page(s)", err)
        self.assertFalse(self.app.exists())

    def test_a_capture_without_a_vacancy_id_requires_an_explicit_id(self):
        (self.snap / "job.json").write_text(json.dumps(
            {k: v for k, v in JOB.items() if k != "jobId"}))
        self.assertEqual(self.run_cli()[0], 2)
        code, d = self.run_cli("--id", "acme-2026-09")
        self.assertEqual(code, 0)
        self.assertIn("/acme-2026-09-software-engineer", d["application"])

    def test_an_unbuilt_variant_is_an_operational_failure(self):
        for p in self.build.iterdir():
            p.unlink()
        code, err = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("build the variant first", err)

    def test_a_profile_capture_is_a_usage_error(self):
        (self.snap / "job.json").unlink()
        self.assertEqual(self.run_cli()[0], 2)

    def test_a_missing_variant_file_is_a_usage_error(self):
        self.variant.unlink()
        self.assertEqual(self.run_cli()[0], 2)


if __name__ == "__main__":
    unittest.main()
