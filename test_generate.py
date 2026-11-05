"""Unit tests for the CV engine. Run:  python3 -m unittest test_generate

(The engine sits at the repo root, not under tools/, so it is not part of the
`discover -s tools/<dir>` sweep - run it by name.)
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

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


class CheckBulletTypes(unittest.TestCase):
    """A plain YAML scalar holding ": " parses as a one-key mapping. Passed
    through, RenderCV dies with an opaque KeyError and the build prints
    nothing. See #50."""

    def test_mapping_bullet_is_rejected_naming_the_bullet(self):
        cfg = cfg_with_bullets({"Built the service for its frontend": "one API surface."})
        with self.assertRaises(SystemExit) as ctx:
            generate.to_rendercv(cfg, {})
        msg = str(ctx.exception)
        self.assertIn("Built the service for its frontend: one API surface.", msg)
        self.assertIn('": "', msg)
        self.assertIn("1 bullet(s)", msg)

    def test_quoted_colon_bullet_is_fine(self):
        # The same text as a real string (what quoting it in YAML yields).
        generate.to_rendercv(
            cfg_with_bullets("Built the service for its frontend: one API surface."), {})

    def test_project_and_education_bullets_are_checked_too(self):
        cfg = dict(CFG, sections=["projects"],
                   projects=[{"name": "p", "url": "https://e.com",
                              "bullets": [{"a": "b"}]}])
        with self.assertRaises(SystemExit) as ctx:
            generate.to_rendercv(cfg, {})
        self.assertIn("[Projects] a: b", str(ctx.exception))


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


class ExampleProfileIsTheSchemaAnchor(unittest.TestCase):
    """CLAUDE.md calls examples/profile.example.yml the committed schema and
    fidelity anchor. It is the only profile CI can see - the clients/ tree is
    private (PRIVATE.md) - so if it drifts, nothing notices. See #26."""

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent
        cls.path = root / "examples" / "profile.example.yml"
        cls.raw = cls.path.read_text(encoding="utf-8")
        cls.cfg = yaml.safe_load(cls.raw)
        cls.design = yaml.safe_load((root / "data" / "design.yaml").read_text())

    def test_it_still_builds(self):
        # Also exercises every guard: a " - " bullet or a confusable in here
        # raises, which is what makes CI's render job meaningful.
        doc = generate.to_rendercv(generate.merge(self.cfg, {}), self.design)
        self.assertTrue(doc["cv"]["sections"])

    def test_every_variant_key_is_documented(self):
        # A key a variant may override but the example never shows is a key
        # nobody knows exists.
        for key in generate.VARIANT_KEYS:
            with self.subTest(key=key):
                self.assertRegex(self.raw, rf"(?m)^#?\s*{key}:", msg=f"{key} undocumented")

    def test_every_section_builder_is_demonstrated(self):
        self.assertEqual(set(self.cfg["sections"]), set(generate.BUILDERS))

    def test_every_experience_field_the_builder_reads_is_present(self):
        for role in self.cfg["experience"]:
            for field in generate.EXPERIENCE_FIELDS:
                with self.subTest(role=role.get("key"), field=field):
                    self.assertIn(field, role)

    def test_it_is_still_fabricated(self):
        # Committed file, public repo: a real profile pasted in here leaks an
        # identity, which PRIVATE.md treats as the one unrecoverable mistake.
        self.assertIn("Ada Lovelace", self.raw)
        self.assertIn("example.com", self.raw)


# RenderCV's Markdown header template renders email, phone, location, website and
# social networks only, so a labelled link (custom_connection) never reaches the
# text an ATS parser reads. See CK-6.
RENDERED_MD = """# Jane Doe's CV

- Email: [jane@example.com](mailto:jane@example.com)
- Location: Dublin, Ireland
- GitHub: [example](https://github.com/example)


# Profile
Text.
"""

LINKED_DOC = {"cv": {"custom_connections": [
    {"placeholder": "LinkedIn", "url": "https://linkedin.com/in/example",
     "fontawesome_icon": "linkedin"}]}}


class AtsMarkdownCarriesTheCustomConnections(unittest.TestCase):
    def test_the_linkedin_link_is_added_to_the_header(self):
        out = generate.patch_ats_markdown(RENDERED_MD, LINKED_DOC)
        self.assertIn("- LinkedIn: [LinkedIn](https://linkedin.com/in/example)", out)

    def test_it_lands_inside_the_header_before_the_first_section(self):
        out = generate.patch_ats_markdown(RENDERED_MD, LINKED_DOC)
        self.assertLess(out.index("linkedin.com/in/example"), out.index("# Profile"))
        self.assertGreater(out.index("linkedin.com/in/example"),
                           out.index("- GitHub:"))

    def test_patching_twice_changes_nothing(self):
        once = generate.patch_ats_markdown(RENDERED_MD, LINKED_DOC)
        self.assertEqual(generate.patch_ats_markdown(once, LINKED_DOC), once)

    def test_no_custom_connection_means_no_change(self):
        self.assertEqual(generate.patch_ats_markdown(RENDERED_MD, {"cv": {}}),
                         RENDERED_MD)

    def test_an_unknown_icon_is_a_plain_link(self):
        doc = {"cv": {"custom_connections": [
            {"placeholder": "Portfolio", "url": "https://example.com/p",
             "fontawesome_icon": "link"}]}}
        self.assertIn("- Link: [Portfolio](https://example.com/p)",
                      generate.patch_ats_markdown(RENDERED_MD, doc))

    def test_a_profile_with_a_labelled_linkedin_contact_yields_the_connection(self):
        cfg = dict(CFG, contacts=[
            {"href": "https://linkedin.com/in/example", "label": "LinkedIn"}])
        doc = generate.to_rendercv(cfg, {})
        self.assertIn("- LinkedIn: [LinkedIn](https://linkedin.com/in/example)",
                      generate.ats_connection_lines(doc))

    def test_the_file_form_rewrites_the_markdown_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            gen, md = Path(d) / "v.rendercv.yaml", Path(d) / "Jane_Doe_CV.md"
            gen.write_text(yaml.safe_dump(LINKED_DOC))
            md.write_text(RENDERED_MD)
            self.assertTrue(generate.patch_ats_file(gen, md))
            self.assertIn("linkedin.com/in/example", md.read_text())
            self.assertFalse(generate.patch_ats_file(gen, md))


class DataRoot(unittest.TestCase):
    """$CAREER_KIT_HOME moves clients/ and build/ out of the checkout. CK-2."""

    def test_unset_means_the_checkout(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CAREER_KIT_HOME", None)
            self.assertEqual(generate.data_root(), generate.ROOT)

    def test_set_means_that_directory(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"CAREER_KIT_HOME": d}):
            self.assertEqual(generate.data_root(), Path(d).resolve())

    def test_a_missing_directory_is_refused_not_created(self):
        with tempfile.TemporaryDirectory() as d:
            gone = str(Path(d) / "nope")
            with mock.patch.dict(os.environ, {"CAREER_KIT_HOME": gone}):
                with self.assertRaises(SystemExit) as ctx:
                    generate.data_root()
            self.assertIn("CAREER_KIT_HOME", str(ctx.exception))
            self.assertFalse(Path(gone).exists())


if __name__ == "__main__":
    unittest.main()
