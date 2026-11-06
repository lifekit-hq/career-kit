"""CLI-level behaviour behind the second set of job-hunt rehearsal fixes
(CK-7 to CK-12). Each runs bin/career against a throwaway $CAREER_KIT_HOME with
an invented client, so nothing here needs a real client, a browser or the network.

Run: python3 -m unittest discover -s tools/career-cli
"""
import json
import os
import subprocess
import sys
import unittest

import clihome

sys.path.insert(0, str(clihome.ROOT / "tools" / "career-version"))
import career_version                                       # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.home = clihome.Home()
        self.addCleanup(self.home.cleanup)

    def env(self, p):
        return json.loads(p.stdout)

    def freeze(self, snap, variant="acme"):
        """What `career cv version` leaves behind, without rendering a PDF."""
        build = self.home.fake_build(variant)
        (build / "Ada_Lovelace_CV.pdf").write_bytes(b"%PDF")
        (build / "Ada_Lovelace_CV_1.png").write_bytes(b"")
        vfile = self.home.client_dir / "variants" / f"{variant}.yml"
        vfile.parent.mkdir(exist_ok=True)
        vfile.write_text("summary: Builds platforms.\n")
        career_version.freeze(self.home.client_dir, vfile, snap, build, None, "2026-09-07")
        return self.home.client_dir / "applications" / "example-corp" / "ex-1-platform-engineer"


class DraftedAndWithdrawn(Base):
    """CK-7 and the withdrawn status, through the CLI."""

    def test_a_draft_is_recorded_listed_and_never_due(self):
        snap = self.home.snapshot()
        p = self.home.run("apply", "add", str(snap), "--status", "drafted", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        row = self.env(p)["data"]["added"]
        self.assertEqual((row["status"], row["applied"], row["followup"]),
                         ("drafted", None, None))
        listed = self.home.run("apply", "list")
        self.assertIn("drafted", listed.stdout)
        due = self.home.run("apply", "followup", "--on", "2999-01-01", "--json")
        self.assertEqual(self.env(due)["data"]["count"], 0)

    def test_withdrawn_is_accepted_by_set_and_filtered_by_list(self):
        snap = self.home.snapshot()
        self.home.run("apply", "add", str(snap))
        p = self.home.run("apply", "set", "EX-1", "--status", "withdrawn", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.env(p)["data"]["updated"]["status"], "withdrawn")
        listed = self.home.run("apply", "list", "--status", "withdrawn", "--json")
        self.assertEqual(self.env(listed)["data"]["count"], 1)

    def test_the_same_role_under_another_id_warns_in_both_output_modes(self):
        first = self.home.snapshot()
        self.home.run("apply", "add", str(first))
        other = self.home.run("jd", "add", str(self.home.jd_file()), "--company",
                              "Example Corp, Inc.", "--title", "Platform Engineer",
                              "--id", "board-9", "--json")
        snap2 = self.env(other)["data"]["snapshot"]
        p = self.home.run("apply", "add", snap2, "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        warnings = self.env(p)["data"]["warnings"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("EX-1", warnings[0])
        text = self.home.run("apply", "add", snap2, "--reapply")
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn("warning:", text.stdout)


class Verdict(Base):
    """CK-9: one call, two files that agree."""

    def test_the_verdict_lands_in_review_and_versions_through_the_cli(self):
        app = self.freeze(self.home.snapshot())
        p = self.home.run("cv", "verdict", "v1", "confirm", "--note",
                          "Confirm the billing scope.", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.env(p)["data"]["verdict"], "submittable with confirmations")
        self.assertIn("Verdict: submittable with confirmations",
                      (app / "v1" / "REVIEW.md").read_text())
        self.assertIn("| submittable with confirmations |", (app / "VERSIONS.md").read_text())

    def test_a_bad_verdict_is_a_usage_error_in_the_envelope(self):
        self.freeze(self.home.snapshot())
        p = self.home.run("cv", "verdict", "v1", "maybe", "--json")
        self.assertEqual(p.returncode, 2)
        self.assertFalse(self.env(p)["ok"])
        self.assertEqual(self.home.run("cv", "verdict", "--json").returncode, 2)


class LintVariantAndAge(Base):
    """CK-10: lint the variant you name, and say how old the capture is."""

    def profile_snapshot(self, name="2026-08-19T14-50-08Z"):
        snap = self.home.client_dir / "captures" / name
        (snap / "raw").mkdir(parents=True)
        (snap / "manifest.json").write_text(json.dumps({"kind": "profile"}))
        (snap / "raw" / "profile.txt").write_text("Senior Software Engineer\n")
        return snap

    def test_a_stale_snapshot_warns_but_does_not_fail_the_lint(self):
        self.profile_snapshot()
        p = self.home.run("cv", "lint", "--json")
        findings = self.env(p)["data"]["findings"]
        age = next(f for f in findings if f["check"] == "snapshot age")
        self.assertEqual(age["status"], "warn")
        self.assertIn("days old", age["detail"])
        self.assertIn("career linkedin capture", age["detail"])

    def test_the_named_variant_is_what_is_linted(self):
        self.profile_snapshot()
        variants = self.home.client_dir / "variants"
        variants.mkdir()
        (variants / "acme.yml").write_text("headline: Head of Nothing | Anything\n")
        p = self.home.run("cv", "lint", "acme", "--json")
        data = self.env(p)["data"]
        self.assertEqual(data["variant"], "acme")
        self.assertEqual(p.returncode, 1)                      # the variant's noun is not on LinkedIn
        self.assertIn("Head of Nothing", json.dumps(data["findings"]))

    def test_a_variant_that_does_not_exist_is_refused_not_silently_the_profile(self):
        self.profile_snapshot()
        p = self.home.run("cv", "lint", "no-such-variant", "--json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("no-such-variant", self.env(p)["error"]["message"])


class Prep(Base):
    """CK-11, through the CLI."""

    def test_the_pack_has_stories_gaps_and_questions(self):
        snap = self.home.snapshot()
        self.home.fake_build()
        p = self.home.run("cv", "prep", str(snap), "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        data = self.env(p)["data"]
        self.assertTrue(data["stories"])
        self.assertIn("observability", data["gaps"]["terms"])
        self.assertTrue(any("observability" in q for q in data["questions"]))
        self.assertEqual(self.home.run("cv", "prep", str(snap)).returncode, 0)

    def test_a_frozen_cuts_review_points_reach_the_pack(self):
        snap = self.home.snapshot()
        app = self.freeze(snap)
        (app / "v1" / "REVIEW.md").write_text(
            "## Credibility\n\nThe platform scope reads bigger than one team.\n")
        self.home.fake_build("baseline")
        p = self.home.run("cv", "prep", str(snap), "baseline", "--json")
        review = self.env(p)["data"]["gaps"]["review"]
        self.assertEqual(review["version"], "v1")
        self.assertIn("bigger than one team", review["points"][0]["text"])

    def test_an_unbuilt_variant_says_which_build_is_missing(self):
        snap = self.home.snapshot()
        p = self.home.run("cv", "prep", str(snap))
        self.assertEqual(p.returncode, 1)
        self.assertIn(f"build/{clihome.CLIENT}/baseline", p.stderr)

    def test_no_snapshot_is_a_usage_error(self):
        self.assertEqual(self.home.run("cv", "prep", "--json").returncode, 2)


class ForbiddenClaims(Base):
    """CK-12: the build itself refuses a CV that makes a listed claim. Runs the
    generator directly (no RenderCV, so no network)."""

    def generate(self):
        env = {**os.environ, "CAREER_KIT_HOME": str(self.home.path)}
        return subprocess.run([sys.executable, str(clihome.ROOT / "generate.py"),
                               "baseline", "-c", clihome.CLIENT], capture_output=True,
                              text=True, cwd=clihome.ROOT, env=env, timeout=60)

    def test_a_listed_phrase_fails_the_build_and_an_unlisted_cv_builds(self):
        ok = self.generate()
        self.assertEqual(ok.returncode, 0, ok.stderr)
        (self.home.client_dir / "forbidden_claims.yml").write_text(
            "- phrase: interesting technical decision\n  reason: invented for the example\n")
        bad = self.generate()
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("interesting technical decision", bad.stderr)
        self.assertIn("invented for the example", bad.stderr)

    def test_an_example_list_ships_and_parses(self):
        import generate
        example = clihome.ROOT / "examples" / "forbidden_claims.example.yml"
        self.assertTrue(example.is_file())
        (self.home.client_dir / "forbidden_claims.yml").write_text(example.read_text())
        self.assertGreaterEqual(len(generate.load_forbidden(self.home.client_dir)), 1)


if __name__ == "__main__":
    unittest.main()
