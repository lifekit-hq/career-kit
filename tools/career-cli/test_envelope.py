"""The --json envelope is a contract, not a per-verb courtesy.

docs/CONTRACT.md states it without qualification: "With --json, a command prints
exactly one JSON object to stdout." Before #23, `career cv ats --json` printed
Markdown and `career cv match --json` printed a plain list, because bin/career
gated the envelope on `verb = build`; missing-argument errors bypassed it too.
This suite exists so the next verb added cannot regress it silently.

Run:  python3 -m unittest discover -s tools/career-cli
"""
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAREER = ROOT / "bin" / "career"
ENVELOPE_KEYS = {"ok", "lane", "verb", "client", "data", "error"}

# Every implemented verb in CONTRACT.md's lane table, with arguments chosen to
# fail fast: an unknown client trips require_client_dir (linkedin) or the
# missing-build guard (cv) before anything touches the network or a browser.
NOPE = ["-c", "__no_such_client__"]
VERBS = [
    ("cv", "ats", []),
    ("cv", "match", ["baseline", "/nonexistent.txt"]),
    ("cv", "lint", []),
    ("linkedin", "capture", []),
    ("linkedin", "diff", []),
    ("linkedin", "audit", []),
    ("linkedin", "jd", []),
    ("linkedin", "keywords", []),
    ("linkedin", "benchmark", []),
]


def run(*args):
    return subprocess.run([str(CAREER), *args], capture_output=True, text=True,
                          timeout=60, cwd=ROOT)


class EveryVerbAnswersWithAnEnvelope(unittest.TestCase):
    """Failure is the path most likely to skip the envelope, so test it for all
    of them - a verb that dies via bash `${n:?...}` never reaches emit()."""

    # A throwaway client, so the missing-argument tests reach the argument check
    # instead of stopping at require_client_dir. Without one the suite passes
    # locally (a real clients/ tree exists) and fails in CI, where it does not.
    TMP_CLIENT = "__envelope_test__"

    @classmethod
    def setUpClass(cls):
        cls.cdir = ROOT / "clients" / cls.TMP_CLIENT
        cls.cdir.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "examples" / "profile.example.yml",
                    cls.cdir / "profile.yml")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.cdir, ignore_errors=True)

    def test_error_paths_are_parseable_envelopes(self):
        for lane, verb, extra in VERBS:
            with self.subTest(verb=f"{lane} {verb}"):
                p = run(lane, verb, *extra, *NOPE, "--json")
                try:
                    env = json.loads(p.stdout)
                except json.JSONDecodeError:
                    self.fail(f"{lane} {verb} --json wrote non-JSON to stdout: "
                              f"{p.stdout[:200]!r}")
                self.assertEqual(set(env), ENVELOPE_KEYS)
                self.assertIs(env["ok"], False)
                self.assertEqual((env["lane"], env["verb"]), (lane, verb))
                self.assertIsNotNone(env["error"], "a failure must carry error")
                # An unknown client is a usage error: CONTRACT.md reserves 2
                # for those and 1 for operational failure.
                self.assertEqual(p.returncode, 2, p.stdout)

    def test_stdout_holds_exactly_one_json_object(self):
        # Diagnostics belong on stderr; a second line would break every caller
        # that does json.loads(stdout).
        p = run("linkedin", "jd", *NOPE, "--json")
        self.assertEqual(len(p.stdout.strip().splitlines()), 1)

    def test_a_missing_argument_still_emits_the_envelope(self):
        # capture/jd used bash `${3:?usage}`, which exits without reaching emit.
        for verb in ("capture", "jd"):
            with self.subTest(verb=verb):
                p = run("linkedin", verb, "-c", self.TMP_CLIENT, "--json")
                self.assertIn("usage", json.loads(p.stdout)["error"]["message"])
                self.assertEqual(p.returncode, 2)

    def test_an_unknown_lane_or_verb_is_a_usage_error_in_the_envelope(self):
        p = run("bogus", "verb", "--json")
        self.assertFalse(json.loads(p.stdout)["ok"])
        self.assertEqual(p.returncode, 2)


@unittest.skipUnless((ROOT / "clients" / ".default").exists(),
                     "needs a real client; clients/ is private and absent in CI")
class CvLaneSuccessPayloads(unittest.TestCase):
    """The happy paths, which need a built CV. Skipped in CI by design - the
    clients/ tree is never committed (PRIVATE.md)."""

    @classmethod
    def setUpClass(cls):
        cls.client = (ROOT / "clients" / ".default").read_text().strip()
        cls.md = next((ROOT / "build" / cls.client / "baseline").glob("*_CV.md"), None)
        if cls.md is None:
            raise unittest.SkipTest("no built CV - run: career cv build")

    def test_ats_returns_the_markdown_an_ats_parser_sees(self):
        env = json.loads(run("cv", "ats", "--json").stdout)
        self.assertTrue(env["ok"])
        self.assertEqual(env["data"]["markdown"].strip(),
                         self.md.read_text().strip())

    def test_match_returns_missing_keywords_as_a_list(self):
        jd = ROOT / "build" / "_envelope_test_jd.txt"
        jd.write_text("kubernetes zzzznotaword\n")
        try:
            env = json.loads(run("cv", "match", "baseline", str(jd), "--json").stdout)
        finally:
            jd.unlink(missing_ok=True)
        self.assertTrue(env["ok"])
        self.assertIsInstance(env["data"]["missing"], list)
        self.assertIn("zzzznotaword", env["data"]["missing"])


if __name__ == "__main__":
    unittest.main()
