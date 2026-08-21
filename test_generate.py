"""Unit tests for the CV engine. Run:  python3 -m unittest test_generate

(The engine sits at the repo root, not under tools/, so it is not part of the
`discover -s tools/<dir>` sweep - run it by name.)
"""
import unittest

import generate

ROLE = {"key": "acme", "title": "Social Media & Recruiting", "company": "Acme",
        "start": "Jan. 2026", "end": "Present", "location": "Remote - Dublin",
        "bullets": ["Ran the channels day to day, writing every caption."]}

CFG = {"name": "Jane Doe", "headline": "Social Media Manager", "summary": "A - B",
       "sections": ["profile", "experience"], "experience": [ROLE]}


def cfg_with_bullets(*bullets):
    return dict(CFG, experience=[dict(ROLE, bullets=list(bullets))])


class CheckHighlights(unittest.TestCase):
    """RenderCV parses " - " inside a highlight as a new list item, silently
    splitting one bullet into two in the PDF and the ATS Markdown. See #15."""

    def test_clean_bullets_render(self):
        out = generate.to_rendercv(CFG, {})
        self.assertEqual(out["cv"]["sections"]["Experience"][0]["highlights"],
                         ROLE["bullets"])

    def test_dash_clause_in_a_bullet_is_rejected(self):
        with self.assertRaises(SystemExit) as ctx:
            generate.to_rendercv(cfg_with_bullets("Ran the channels - daily."), {})
        self.assertIn(" - ", str(ctx.exception))
        self.assertIn("Ran the channels - daily.", str(ctx.exception))

    def test_every_offending_bullet_is_listed(self):
        with self.assertRaises(SystemExit) as ctx:
            generate.to_rendercv(
                cfg_with_bullets("one - split", "fine, a comma", "two - split"), {})
        self.assertIn("2 bullet(s)", str(ctx.exception))

    def test_summary_and_location_may_contain_the_separator(self):
        # Neither is a Markdown list item, so neither splits.
        out = generate.to_rendercv(CFG, {})
        self.assertEqual(out["cv"]["sections"]["Profile"], ["A - B"])
        self.assertEqual(out["cv"]["sections"]["Experience"][0]["location"],
                         "Remote - Dublin")

    def test_hyphenated_words_and_ranges_are_not_flagged(self):
        generate.to_rendercv(cfg_with_bullets("End-to-end ownership, 2024-2026."), {})

    def test_project_and_education_bullets_are_checked_too(self):
        cfg = dict(CFG, sections=["projects"],
                   projects=[{"name": "p", "url": "https://e.com",
                              "bullets": ["a - b"]}])
        with self.assertRaises(SystemExit):
            generate.to_rendercv(cfg, {})


class Merge(unittest.TestCase):
    def test_variant_headline_replaces_the_profile_headline(self):
        merged = generate.merge(CFG, {"headline": "Social Media Manager | Reels"})
        self.assertEqual(merged["headline"], "Social Media Manager | Reels")

    def test_unknown_experience_key_is_a_hard_error(self):
        with self.assertRaises(SystemExit):
            generate.merge(CFG, {"experience_order": ["nope"]})


if __name__ == "__main__":
    unittest.main()
