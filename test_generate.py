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


class UnicodeHygiene(unittest.TestCase):
    """Invisible controls and exotic spaces reach the PDF and the ATS Markdown
    unseen; a non-Latin lookalike makes a keyword unmatchable. See #18."""

    def render(self, cfg):
        return generate.to_rendercv(cfg, {})["cv"]

    def test_zero_width_and_soft_hyphen_are_stripped(self):
        cv = self.render(cfg_with_bullets("Grew\u200b the chan\u00adnels."))
        self.assertEqual(cv["sections"]["Experience"][0]["highlights"],
                         ["Grew the channels."])

    def test_bom_and_bidi_controls_are_stripped_from_any_field(self):
        cv = self.render(dict(CFG, headline="\ufeffSocial\u202e Media Manager"))
        self.assertEqual(cv["headline"], "Social Media Manager")

    def test_exotic_spaces_fold_to_u0020(self):
        cv = self.render(cfg_with_bullets("Ran\u00a0the\u2009channels\u202fdaily."))
        self.assertEqual(cv["sections"]["Experience"][0]["highlights"],
                         ["Ran the channels daily."])

    def test_nbsp_wrapped_separator_still_trips_the_bullet_check(self):
        # The fold has to run first, or #15's check never sees a plain " - ".
        with self.assertRaises(SystemExit) as ctx:
            self.render(cfg_with_bullets("Ran the channels\u00a0-\u00a0daily."))
        # Reported with the NBSPs already folded, i.e. as the text RenderCV sees.
        self.assertIn("Ran the channels - daily.", str(ctx.exception))

    def test_cyrillic_lookalike_is_a_hard_error_naming_the_codepoint(self):
        with self.assertRaises(SystemExit) as ctx:
            self.render(dict(CFG, headline="Social Media M\u0430nager"))
        msg = str(ctx.exception)
        self.assertIn("U+0430", msg)
        self.assertIn("cv.headline", msg)

    def test_fullwidth_latin_is_rejected_too(self):
        with self.assertRaises(SystemExit) as ctx:
            self.render(cfg_with_bullets("Owned \uff34ikTok end to end."))
        self.assertIn("U+FF34", str(ctx.exception))

    def test_every_offending_field_is_listed(self):
        with self.assertRaises(SystemExit) as ctx:
            self.render(dict(CFG, headline="M\u0430nager", summary="\u0435ditor"))
        self.assertIn("2 field(s)", str(ctx.exception))

    def test_plain_ascii_and_en_dash_are_left_alone(self):
        cv = self.render(cfg_with_bullets("Owned 2024\u20132026 end to end."))
        self.assertEqual(cv["sections"]["Experience"][0]["highlights"],
                         ["Owned 2024\u20132026 end to end."])


if __name__ == "__main__":
    unittest.main()
