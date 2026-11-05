"""The tool is publishable; the content is not. See PRIVATE.md and #36.

lifekit-hq/career-kit is a public repo, so a client's directory name or LinkedIn
id in a committed file is a published identity. This suite is the mechanism
behind that rule.

It never hardcodes a real name - it reads them out of the private tree at run
time and greps the committed files for them. In CI, where clients/ is absent,
that half skips and the static id check still runs.

Run: python3 -m unittest discover -s tools/career-cli
"""
import os
import re
import subprocess
import unittest
from pathlib import Path

import clihome

ROOT = Path(__file__).resolve().parents[2]

# A LinkedIn public id ends in the member's real numeric suffix. Fixtures must
# zero it out; anything else is somebody's actual profile.
REAL_LOOKING_ID = re.compile(r"/in/[a-z0-9-]+-(?!0+\b)\d{6,}", re.I)


def committed_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.split()
    return [ROOT / f for f in out]


def private_roots():
    """Every place a client tree can live: the checkout, and wherever
    $CAREER_KIT_HOME points the CLI (the recommended, out-of-repo home)."""
    roots = [ROOT / "clients"]
    home = os.environ.get("CAREER_KIT_HOME", "")
    if home:
        roots.append(Path(home).expanduser() / "clients")
    return roots


def private_names():
    """Client identities, read from the tree that is never committed."""
    names = []
    for cdir in private_roots():
        if not cdir.is_dir():
            continue
        names += [p.name for p in cdir.iterdir()
                  if p.is_dir() and not p.name.startswith("_")]
        default = cdir / ".default"
        if default.is_file():
            names.append(default.read_text(encoding="utf-8").strip())
    return sorted({n for n in names if n})


class NoIdentitiesInCommittedFiles(unittest.TestCase):
    def _grep(self, needle):
        hits = []
        for f in committed_files():
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if needle(line):
                    hits.append(f"{f.relative_to(ROOT)}:{i}")
        return hits

    def test_no_client_directory_name_is_committed(self):
        names = private_names()
        if not names:
            self.skipTest("no clients/ tree here (this is how CI sees the repo)")
        for name in names:
            with self.subTest(client=name):
                hits = self._grep(lambda l, n=name: n in l)
                self.assertEqual(hits, [], f"client identity in committed file(s): {hits}")

    def test_no_real_looking_linkedin_id_is_committed(self):
        # Runs everywhere, including CI - it needs no private data to work.
        hits = self._grep(lambda l: bool(REAL_LOOKING_ID.search(l)))
        self.assertEqual(hits, [], f"real-looking LinkedIn id(s): {hits}")


class DataRootKeepsThePrivateTreeOutOfTheCheckout(unittest.TestCase):
    """CK-2: with $CAREER_KIT_HOME set, the CLI reads and writes clients/ and
    build/ there and nowhere in the repo, so no symlink into the checkout is
    needed (and a symlink would slip past the directory-only /clients/ rule)."""

    def setUp(self):
        self.home = clihome.Home()
        self.addCleanup(self.home.cleanup)

    def checkout_has_no_trace(self):
        self.assertFalse((ROOT / "clients" / clihome.CLIENT).exists())
        self.assertFalse((ROOT / "build" / clihome.CLIENT).exists())

    def test_a_whole_flow_runs_against_an_external_directory(self):
        snap = self.home.snapshot()
        self.assertTrue(str(snap).startswith(str(self.home.path / "clients" / clihome.CLIENT)))
        self.home.fake_build()
        for verb in (("cv", "letter", str(snap)), ("cv", "ats"),
                     ("apply", "add", str(snap)), ("apply", "list")):
            with self.subTest(verb=" ".join(verb[:2])):
                p = self.home.run(*verb)
                self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertTrue((self.home.client_dir / "applications.yml").is_file())
        self.checkout_has_no_trace()

    def test_an_unknown_client_is_looked_for_in_the_data_root_only(self):
        p = self.home.run("cv", "ats", "--json", home=self.home.path / "elsewhere")
        self.assertEqual(p.returncode, 2)
        self.assertIn("CAREER_KIT_HOME", p.stdout)

    def test_a_data_root_that_is_not_a_directory_is_a_usage_error(self):
        gone = self.home.path / "does-not-exist"
        p = self.home.run("apply", "list", "--json", home=gone)
        self.assertEqual(p.returncode, 2)
        self.assertFalse(gone.exists())
        self.checkout_has_no_trace()

    def test_the_default_client_is_read_from_the_data_root(self):
        (self.home.path / "clients" / ".default").write_text(clihome.CLIENT + "\n")
        p = subprocess.run([str(clihome.CAREER), "apply", "list", "--json"],
                           capture_output=True, text=True, cwd=ROOT, timeout=60,
                           env={**os.environ, "CAREER_KIT_HOME": str(self.home.path)})
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)

    def test_private_names_are_also_read_from_the_data_root(self):
        (self.home.path / "clients" / "invented-person").mkdir()
        old = os.environ.get("CAREER_KIT_HOME")
        os.environ["CAREER_KIT_HOME"] = str(self.home.path)
        try:
            self.assertIn("invented-person", private_names())
        finally:
            if old is None:
                os.environ.pop("CAREER_KIT_HOME")
            else:
                os.environ["CAREER_KIT_HOME"] = old


if __name__ == "__main__":
    unittest.main()
