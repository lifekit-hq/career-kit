"""Unit tests for career_apply. Run: python3 -m unittest discover -s tools/career-apply"""
import json
import tempfile
import unittest
from pathlib import Path

import career_apply

JOB = {"schema": "li-scrape-job/1", "jobId": "4437630034",
       "source": "https://www.linkedin.com/jobs/view/4437630034/",
       "title": "Social Media Manager", "company": "Pardgroup",
       "location": "Dublin, County Dublin, Ireland", "description": "..."}
TODAY = "2026-08-21"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = Path(self.tmp.name)
        self.snap = self.client / "captures" / "2026-08-19T14-50-08Z"
        self.snap.mkdir(parents=True)
        (self.snap / "job.json").write_text(json.dumps(JOB))
        self.addCleanup(self.tmp.cleanup)

    def run_cli(self, *argv):
        """Returns (exit_code, parsed-json-or-None)."""
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = career_apply.main([*argv, "--json"], today=TODAY)
        out = buf.getvalue().strip()
        return code, (json.loads(out) if code == 0 and out else None)

    def add(self, *extra):
        return self.run_cli("add", str(self.client), str(self.snap), *extra)


class Add(Base):
    def test_company_and_role_come_from_the_capture_not_by_hand(self):
        # The ledger must not be able to disagree with the evidence it cites.
        _, d = self.add("--variant", "pardgroup")
        self.assertEqual((d["added"]["company"], d["added"]["role"]),
                         ("Pardgroup", "Social Media Manager"))
        self.assertEqual(d["added"]["source"], JOB["source"])

    def test_jd_is_stored_relative_to_the_client_dir(self):
        _, d = self.add()
        self.assertEqual(d["added"]["jd"], "captures/2026-08-19T14-50-08Z")

    def test_applied_defaults_to_today_and_followup_to_a_week_out(self):
        _, d = self.add()
        self.assertEqual(d["added"]["applied"], TODAY)
        self.assertEqual(d["added"]["followup"], "2026-08-28")

    def test_the_row_id_is_the_postings_vacancy_id(self):
        # It is what the applicant sees on the posting and types when chasing,
        # and the one thing that tells two live postings of a role apart.
        _, d = self.add()
        self.assertEqual(d["added"]["id"], "4437630034")

    def test_recording_the_same_posting_twice_is_a_usage_error(self):
        self.add()
        code, _ = self.add()
        self.assertEqual(code, 2)
        self.assertEqual(self.run_cli("list", str(self.client))[1]["count"], 1)

    def test_reapply_records_a_second_row_with_a_suffixed_id(self):
        self.add()
        _, d = self.add("--reapply")
        self.assertEqual(d["added"]["id"], "4437630034-2")
        _, d = self.add("--reapply")
        self.assertEqual(d["added"]["id"], "4437630034-3")
        self.assertEqual(d["count"], 3)

    def test_a_capture_without_a_vacancy_id_requires_an_explicit_id(self):
        # A careers-page snapshot has no jobId; guessing one would be worse
        # than refusing.
        (self.snap / "job.json").write_text(json.dumps(
            {k: v for k, v in JOB.items() if k != "jobId"}))
        code, _ = self.add()
        self.assertEqual(code, 2)
        _, d = self.add("--id", "acme-2026-09")
        self.assertEqual(d["added"]["id"], "acme-2026-09")

    def test_the_frozen_version_that_was_sent_is_recorded_and_listed(self):
        _, d = self.add("--variant", "pardgroup", "--version", "v2")
        self.assertEqual(d["added"]["version"], "v2")
        _, d = self.run_cli("list", str(self.client))
        self.assertEqual(d["applications"][0]["version"], "v2")

    def test_an_explicit_id_wins_over_the_captures(self):
        _, d = self.add("--id", "custom")
        self.assertEqual(d["added"]["id"], "custom")

    def test_a_bare_capture_timestamp_resolves(self):
        _, d = self.run_cli("add", str(self.client), "2026-08-19T14-50-08Z")
        self.assertEqual(d["added"]["jd"], "captures/2026-08-19T14-50-08Z")

    def test_a_snapshot_without_job_json_is_a_usage_error(self):
        # A profile capture is not a job post; recording one would be nonsense.
        bare = self.client / "captures" / "profile-snap"
        bare.mkdir(parents=True)
        code, _ = self.run_cli("add", str(self.client), str(bare))
        self.assertEqual(code, 2)

    def test_a_bad_date_is_a_usage_error(self):
        code, _ = self.add("--applied", "19-08-2026")
        self.assertEqual(code, 2)


class ListAndSet(Base):
    def test_list_is_empty_before_anything_is_recorded(self):
        _, d = self.run_cli("list", str(self.client))
        self.assertEqual((d["count"], d["applications"]), (0, []))

    def test_status_filter(self):
        self.add()
        self.run_cli("set", str(self.client), "4437630034", "--status", "interview")
        _, d = self.run_cli("list", str(self.client), "--status", "interview")
        self.assertEqual(d["count"], 1)
        _, d = self.run_cli("list", str(self.client), "--status", "sent")
        self.assertEqual(d["count"], 0)

    def test_a_terminal_status_clears_the_followup_date(self):
        # Otherwise a rejected application keeps surfacing in the chase queue.
        self.add()
        _, d = self.run_cli("set", str(self.client), "4437630034", "--status", "rejected")
        self.assertIsNone(d["updated"]["followup"])

    def test_unknown_status_and_unknown_id_are_usage_errors(self):
        self.add()
        self.assertEqual(self.run_cli("set", str(self.client), "4437630034",
                                      "--status", "vibing")[0], 2)
        self.assertEqual(self.run_cli("set", str(self.client), "a999",
                                      "--status", "replied")[0], 2)

    def test_the_ledger_survives_a_round_trip_as_readable_yaml(self):
        self.add("--notes", "referred by a friend")
        text = (self.client / "applications.yml").read_text()
        self.assertIn("referred by a friend", text)
        _, d = self.run_cli("list", str(self.client))
        self.assertEqual(d["applications"][0]["notes"], "referred by a friend")


class Followup(Base):
    """What is due to chase. See #24."""

    def due(self, on):
        return self.run_cli("followup", str(self.client), "--on", on)[1]

    def test_nothing_is_due_before_the_followup_date(self):
        self.add("--applied", "2026-08-19")          # followup 2026-08-26
        self.assertEqual(self.due("2026-08-25")["count"], 0)

    def test_due_on_the_day_and_overdue_after(self):
        self.add("--applied", "2026-08-19")
        self.assertEqual(self.due("2026-08-26")["due"][0]["days_overdue"], 0)
        self.assertEqual(self.due("2026-08-30")["due"][0]["days_overdue"], 4)

    def test_a_rejected_application_drops_out_of_the_queue(self):
        # Its followup was cleared at set-time; this guards both halves.
        self.add("--applied", "2026-08-19")
        self.run_cli("set", str(self.client), "4437630034", "--status", "rejected")
        self.assertEqual(self.due("2026-09-30")["count"], 0)

    def test_a_replied_application_is_still_worth_chasing(self):
        self.add("--applied", "2026-08-19")
        self.run_cli("set", str(self.client), "4437630034", "--status", "replied")
        self.assertEqual(self.due("2026-08-30")["count"], 1)

    def test_most_overdue_first(self):
        self.add("--applied", "2026-08-10")           # followup 08-17
        self.add("--applied", "2026-08-19", "--reapply")   # followup 08-26
        due = self.due("2026-08-30")["due"]
        self.assertEqual([a["id"] for a in due], ["4437630034", "4437630034-2"])
        self.assertGreater(due[0]["days_overdue"], due[1]["days_overdue"])


class Chasing(Base):
    """days-quiet and the chase recorder (#45). Both derived from data the
    ledger already holds - nothing new is stored except the notes marker."""

    def test_days_quiet_counts_from_applied(self):
        self.add("--applied", "2026-08-10")           # TODAY is 2026-08-21
        _, d = self.run_cli("list", str(self.client))
        self.assertEqual(d["applications"][0]["days_quiet"], 11)
        self.assertEqual(d["applications"][0]["chases"], 0)

    def test_a_chase_restarts_the_quiet_clock_and_the_followup(self):
        self.add("--applied", "2026-08-01")
        _, d = self.run_cli("set", str(self.client), "4437630034",
                            "--chased", "2026-08-15")
        self.assertIn("chased 2026-08-15", d["updated"]["notes"])
        self.assertEqual(d["updated"]["followup"], "2026-08-22")   # chase + 7
        _, d = self.run_cli("list", str(self.client))
        self.assertEqual(d["applications"][0]["days_quiet"], 6)    # from chase
        self.assertEqual(d["applications"][0]["chases"], 1)

    def test_a_bare_chased_flag_means_today(self):
        self.add("--applied", "2026-08-01")
        _, d = self.run_cli("set", str(self.client), "4437630034", "--chased")
        self.assertIn(f"chased {TODAY}", d["updated"]["notes"])

    def test_chasing_keeps_existing_notes(self):
        self.add("--notes", "referred by a friend")
        _, d = self.run_cli("set", str(self.client), "4437630034", "--chased")
        self.assertEqual(d["updated"]["notes"],
                         f"referred by a friend; chased {TODAY}")

    def test_an_explicit_followup_beats_the_chase_bump(self):
        self.add()
        _, d = self.run_cli("set", str(self.client), "4437630034",
                            "--chased", "--followup", "2026-09-15")
        self.assertEqual(d["updated"]["followup"], "2026-09-15")

    def test_chasing_a_closed_application_is_a_usage_error(self):
        self.add()
        self.run_cli("set", str(self.client), "4437630034", "--status", "rejected")
        code, _ = self.run_cli("set", str(self.client), "4437630034", "--chased")
        self.assertEqual(code, 2)

    def test_a_terminal_application_has_no_quiet_to_measure(self):
        self.add("--applied", "2026-08-10")
        self.run_cli("set", str(self.client), "4437630034", "--status", "ghosted")
        _, d = self.run_cli("list", str(self.client))
        self.assertIsNone(d["applications"][0]["days_quiet"])

    def test_a_hand_written_chase_marker_counts_too(self):
        # The marker is the format, not the flag - hand edits stay first-class.
        self.add()
        self.run_cli("set", str(self.client), "4437630034",
                     "--notes", "pinged recruiter, chased 2026-08-25, no reply")
        _, d = self.run_cli("followup", str(self.client), "--on", "2026-09-30")
        self.assertEqual(d["due"][0]["chases"], 1)

    def test_derived_fields_never_reach_the_ledger_file(self):
        self.add()
        self.run_cli("list", str(self.client))
        text = (self.client / "applications.yml").read_text()
        self.assertNotIn("days_quiet", text)
        self.assertNotIn("chases", text)

    def test_a_garbage_hand_typed_date_degrades_to_no_value(self):
        (self.client / "applications.yml").write_text(
            "applications:\n- id: a001\n  status: sent\n  applied: soonish\n")
        code, d = self.run_cli("list", str(self.client))
        self.assertEqual(code, 0)
        self.assertIsNone(d["applications"][0]["days_quiet"])


class HandEditedLedger(Base):
    """The file header says "Hand-editable", so it has to tolerate what a hand
    writes - not only what save() wrote. Every case here crashed with a raw
    traceback before."""

    def write(self, text):
        (self.client / "applications.yml").write_text(text)

    def test_an_applications_key_with_nothing_under_it(self):
        # `applications:` alone parses as None, not as an empty list.
        self.write("schema: career-apply/1\napplications:\n")
        _, d = self.run_cli("list", str(self.client))
        self.assertEqual((d["count"], d["applications"]), (0, []))

    def test_an_unquoted_date_is_a_date_object_not_a_string(self):
        # YAML parses 2026-08-01 as datetime.date; we compare these as ISO
        # strings, so followup raised TypeError on a hand-written entry.
        self.write("applications:\n- id: a001\n  status: sent\n"
                   "  applied: 2026-08-01\n  followup: 2026-08-01\n")
        _, d = self.run_cli("followup", str(self.client), "--on", "2026-08-21")
        self.assertEqual(d["count"], 1)
        self.assertEqual(d["due"][0]["days_overdue"], 20)

    def test_applications_that_is_not_a_list_is_a_usage_error(self):
        self.write("applications: nope\n")
        self.assertEqual(self.run_cli("list", str(self.client))[0], 2)

    def test_an_entry_that_is_not_a_mapping_is_a_usage_error(self):
        self.write("applications:\n- just a string\n")
        self.assertEqual(self.run_cli("list", str(self.client))[0], 2)

    def test_a_hand_written_or_legacy_id_is_still_addressable(self):
        # Rows from before vacancy ids (a001) and hand-typed ids are just ids.
        self.write("applications:\n- id: a001\n  status: sent\n"
                   "- id: pardgroup-aug\n  status: sent\n")
        _, d = self.run_cli("set", str(self.client), "a001", "--status", "replied")
        self.assertEqual(d["updated"]["status"], "replied")
        _, d = self.add()
        self.assertEqual(d["added"]["id"], "4437630034")
        self.assertEqual(d["count"], 3)


class Reopening(Base):
    def test_reopening_a_rejected_application_restores_its_followup_date(self):
        # Otherwise it reads as live while being invisible to `followup`
        # forever - the exact lost thread the ledger exists to prevent.
        self.add("--applied", "2026-08-10")
        self.run_cli("set", str(self.client), "4437630034", "--status", "rejected")
        _, d = self.run_cli("set", str(self.client), "4437630034", "--status", "sent")
        self.assertEqual(d["updated"]["followup"], "2026-08-28")   # today + 7

    def test_an_explicit_followup_still_wins_over_the_restored_one(self):
        self.add()
        self.run_cli("set", str(self.client), "4437630034", "--status", "ghosted")
        _, d = self.run_cli("set", str(self.client), "4437630034",
                            "--status", "sent", "--followup", "2026-09-01")
        self.assertEqual(d["updated"]["followup"], "2026-09-01")

    def test_reopening_does_not_disturb_a_followup_that_is_still_set(self):
        self.add("--applied", "2026-08-10")
        _, d = self.run_cli("set", str(self.client), "4437630034", "--status", "replied")
        self.assertEqual(d["updated"]["followup"], "2026-08-17")


if __name__ == "__main__":
    unittest.main()