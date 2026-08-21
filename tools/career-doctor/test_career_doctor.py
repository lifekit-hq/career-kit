"""Unit tests for career_doctor. Run: python3 -m unittest discover -s tools/career-doctor"""
import tempfile
import unittest
from pathlib import Path

import career_doctor as doc


def scaffold(root: Path, client="acme", profile=True, design=True, variants=0):
    if profile:
        (root / "clients" / client).mkdir(parents=True)
        (root / "clients" / client / "profile.yml").write_text("name: x\n")
        if variants:
            (root / "clients" / client / "variants").mkdir()
            for i in range(variants):
                (root / "clients" / client / "variants" / f"v{i}.yml").write_text("{}\n")
    if design:
        (root / "data").mkdir(parents=True, exist_ok=True)
        (root / "data" / "design.yaml").write_text("{}\n")
    return root


class Probes(unittest.TestCase):
    def test_python_below_the_floor_fails(self):
        self.assertEqual(doc.check_python((3, 10, 0))["status"], doc.FAIL)
        self.assertEqual(doc.check_python((3, 11, 0))["status"], doc.OK)

    def test_missing_uv_fails_and_names_the_fix(self):
        c = doc.check_uv(which=lambda n: None)
        self.assertEqual(c["status"], doc.FAIL)
        self.assertIn("uv", c["fix"])

    def test_uv_without_uvx_still_fails(self):
        # uvx is what fetches RenderCV; uv alone renders nothing.
        c = doc.check_uv(which=lambda n: "/bin/uv" if n == "uv" else None)
        self.assertEqual(c["status"], doc.FAIL)

    def test_absent_chrome_is_a_warning_not_a_failure(self):
        # Only the linkedin lane drives it - the cv lane must stay usable.
        def refuse():
            raise OSError("refused")
        self.assertEqual(doc.check_cdp(connect=refuse)["status"], doc.WARN)

    def test_reachable_chrome_is_ok(self):
        class Sock:
            def close(self): pass
        self.assertEqual(doc.check_cdp(connect=Sock)["status"], doc.OK)


class ClientResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_a_named_client_with_a_profile_is_ok_and_counts_variants(self):
        scaffold(self.root, variants=2)
        c = doc.check_client(self.root, "acme")
        self.assertEqual(c["status"], doc.OK)
        self.assertIn("2 variant(s)", c["detail"])

    def test_an_unknown_client_fails(self):
        scaffold(self.root)
        self.assertEqual(doc.check_client(self.root, "nope")["status"], doc.FAIL)

    def test_a_client_dir_without_a_profile_fails(self):
        (self.root / "clients" / "acme").mkdir(parents=True)
        c = doc.check_client(self.root, "acme")
        self.assertEqual(c["status"], doc.FAIL)
        self.assertIn("profile.example.yml", c["fix"])

    def test_no_default_and_no_flag_warns_rather_than_guessing(self):
        # Guessing a client is how a CV gets built for the wrong person.
        (self.root / "clients").mkdir(parents=True)
        self.assertEqual(doc.check_client(self.root, None)["status"], doc.WARN)

    def test_the_default_file_is_read_when_no_client_is_given(self):
        scaffold(self.root)
        (self.root / "clients" / ".default").write_text("acme\n")
        self.assertEqual(doc.check_client(self.root, None)["status"], doc.OK)


class Report(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = scaffold(Path(self.tmp.name))
        self.addCleanup(self.tmp.cleanup)

    def test_warnings_alone_do_not_make_it_not_ok(self):
        checks = [doc._c(doc.OK, "a", ""), doc._c(doc.WARN, "b", "")]
        self.assertTrue(doc.summarize(checks)["ok"])

    def test_one_failure_makes_it_not_ok(self):
        checks = [doc._c(doc.OK, "a", ""), doc._c(doc.FAIL, "b", "")]
        self.assertFalse(doc.summarize(checks)["ok"])

    def test_exit_code_is_1_only_when_something_failed(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(doc.main([str(self.root), "--client", "acme", "--json"]), 0)
            self.assertEqual(doc.main([str(self.root), "--client", "nope", "--json"]), 1)

    def test_the_fix_line_is_shown_for_problems_and_hidden_for_ok(self):
        text = doc.render(doc.summarize(
            [doc._c(doc.OK, "a", "d", "unused"), doc._c(doc.FAIL, "b", "d", "do this")]))
        self.assertIn("do this", text)
        self.assertNotIn("unused", text)


if __name__ == "__main__":
    unittest.main()
