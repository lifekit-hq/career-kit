"""Unit tests for li_scrape pure helpers (port of the retired node:test suite,
plus the job-post helpers). Playwright is never imported here - the runner
imports it lazily. Run:  python3 -m unittest discover -s tools/linkedin-scrape"""
import unittest
from pathlib import Path

import li_scrape as h

FIXTURES = Path(__file__).parent / "test" / "fixtures"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class HelpersTest(unittest.TestCase):
    def test_parse_public_id(self):
        self.assertEqual(
            h.parse_public_id("https://www.linkedin.com/in/yelyzaveta-morozova-496272408/"),
            "yelyzaveta-morozova-496272408")
        self.assertEqual(h.parse_public_id("yelyzaveta-morozova-496272408"),
                         "yelyzaveta-morozova-496272408")
        self.assertEqual(
            h.parse_public_id("https://www.linkedin.com/in/foo-bar/details/skills/"), "foo-bar")
        self.assertEqual(h.parse_public_id("https://www.linkedin.com/in/foo?utm=x#y"), "foo")
        self.assertIsNone(h.parse_public_id("https://www.linkedin.com/feed/"))
        self.assertIsNone(h.parse_public_id(""))
        self.assertIsNone(h.parse_public_id(None))

    def test_profile_base_section_url_name(self):
        self.assertEqual(h.profile_base("id"), "https://www.linkedin.com/in/id")
        self.assertEqual(h.section_url("id", ""), "https://www.linkedin.com/in/id/")
        self.assertEqual(h.section_url("id", "details/skills"),
                         "https://www.linkedin.com/in/id/details/skills/")
        self.assertEqual(h.section_name(""), "profile")
        self.assertEqual(h.section_name("details/skills"), "skills")

    def test_is_blocked_url(self):
        self.assertTrue(h.is_blocked_url("https://www.linkedin.com/authwall?x"))
        self.assertTrue(h.is_blocked_url("https://www.linkedin.com/login"))
        self.assertTrue(h.is_blocked_url("https://www.linkedin.com/checkpoint/xyz"))
        self.assertFalse(h.is_blocked_url("https://www.linkedin.com/in/foo/"))
        self.assertFalse(h.is_blocked_url(None))
        self.assertFalse(h.is_blocked_url(42))

    def test_out_dir_for(self):
        self.assertEqual(h.out_dir_for("/tmp", "foo"), "/tmp/out-foo")
        self.assertEqual(h.out_dir_for("/tmp", "foo", "custom"), "/tmp/custom")

    def test_normalize_lines(self):
        self.assertEqual(h.normalize_lines("a\n\n  a \nb\nb\nc"), ["a", "b", "c"])
        self.assertEqual(h.normalize_lines(""), [])
        self.assertEqual(h.normalize_lines(None), [])

    def test_slice_section(self):
        lines = h.slice_section(fixture("experience.txt"), "Experience")
        self.assertEqual(lines[0], "Senior Widget Engineer")
        self.assertNotIn("More profiles for you", lines)
        self.assertNotIn("Jane Doe", lines)

    def test_split_company_type(self):
        self.assertEqual(h.split_company_type("Acme Corp · Full-time"),
                         {"company": "Acme Corp", "employmentType": "Full-time"})

    def test_split_location_arrangement(self):
        self.assertEqual(h.split_location_arrangement("Berlin, Germany · Remote"),
                         {"location": "Berlin, Germany", "arrangement": "Remote"})
        self.assertEqual(h.split_location_arrangement("Kyiv, Ukraine"),
                         {"location": "Kyiv, Ukraine", "arrangement": None})

    def test_looks_like_date_line(self):
        self.assertTrue(h.looks_like_date_line("Jan 2020 - Present · 4 yrs 6 mos"))
        self.assertFalse(h.looks_like_date_line("Acme Corp · Full-time"))

    def test_strip_duration(self):
        self.assertEqual(h.strip_duration("Jan 2020 - Present · 4 yrs 6 mos"),
                         "Jan 2020 - Present")

    def test_parse_experience(self):
        positions = h.parse_experience(fixture("experience.txt"))
        self.assertEqual(len(positions), 2)
        self.assertEqual(positions[0], {
            "title": "Senior Widget Engineer",
            "company": "Acme Corp",
            "employmentType": "Full-time",
            "dateRange": "Jan 2020 - Present",
            "location": "Berlin, Germany",
            "arrangement": "Remote",
            "description": ["Built widgets at scale.", "Led the widget team."],
        })
        self.assertEqual(positions[1]["title"], "Junior Widget Maker")
        self.assertEqual(positions[1]["arrangement"], "On-site")
        self.assertEqual(positions[1]["description"], ["Made small widgets."])

    def test_parse_education(self):
        edu = h.parse_education(fixture("education.txt"))
        self.assertEqual(len(edu), 2)
        self.assertEqual(edu[0], {
            "school": "Fake State University",
            "degree": "Master's Degree",
            "field": "Computer Science",
            "dateRange": "Sep 2016 - Jun 2018",
        })
        self.assertEqual(edu[1]["school"], "Fake Community College")

    def test_parse_skills(self):
        self.assertEqual(h.parse_skills(fixture("skills.txt")), [
            {"name": "Widget Design", "endorsements": 5},
            {"name": "Scaling Systems", "endorsements": 3},
            {"name": "Team Leadership", "endorsements": 2},
        ])

    def test_extract_email(self):
        self.assertEqual(h.extract_email("Email\nfoo.bar@example.com\nConnected"),
                         "foo.bar@example.com")
        self.assertIsNone(h.extract_email("no email here"))


class JobHelpersTest(unittest.TestCase):
    def test_parse_job_id(self):
        self.assertEqual(
            h.parse_job_id("https://www.linkedin.com/jobs/view/4012345678/?refId=x"),
            "4012345678")
        self.assertEqual(h.parse_job_id("4012345678"), "4012345678")
        self.assertIsNone(h.parse_job_id("https://www.linkedin.com/jobs/search/"))
        self.assertIsNone(h.parse_job_id("12345"))  # too short for a job id
        self.assertIsNone(h.parse_job_id(None))

    def test_job_url(self):
        self.assertEqual(h.job_url("42424242"),
                         "https://www.linkedin.com/jobs/view/42424242/")

    def test_parse_job_text(self):
        raw = "\n".join([
            "Skip to search", "Home",
            "BrightWave Agency",
            "Social Media Executive",
            "Dublin, County Dublin, Ireland · 1 week ago · 55 applicants",
            "Hybrid  Full-time  Entry level",
            "Apply", "Save",
            "About the job",
            "We are looking for a social media executive.",
            "You will run Instagram and TikTok.",
            "About the company",
            "BrightWave is an agency.",
        ])
        job = h.parse_job_text(raw)
        self.assertEqual(job["title"], "Social Media Executive")
        self.assertEqual(job["company"], "BrightWave Agency")
        self.assertEqual(job["location"], "Dublin, County Dublin, Ireland")
        self.assertEqual(job["description"], [
            "We are looking for a social media executive.",
            "You will run Instagram and TikTok.",
        ])

    def test_parse_job_text_without_anchor(self):
        job = h.parse_job_text("random page\nwith no job markers")
        self.assertIsNone(job["title"])
        self.assertEqual(job["description"], [])


if __name__ == "__main__":
    unittest.main()
