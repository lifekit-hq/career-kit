"""The tool is publishable; the content is not. See PRIVATE.md and #36.

lifekit-hq/career-kit is a public repo, so a client's directory name or LinkedIn
id in a committed file is a published identity. This suite is the mechanism
behind that rule.

It never hardcodes a real name - it reads them out of the private tree at run
time and greps the committed files for them. In CI, where clients/ is absent,
that half skips and the static id check still runs.

Run: python3 -m unittest discover -s tools/career-cli
"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# A LinkedIn public id ends in the member's real numeric suffix. Fixtures must
# zero it out; anything else is somebody's actual profile.
REAL_LOOKING_ID = re.compile(r"/in/[a-z0-9-]+-(?!0+\b)\d{6,}", re.I)


def committed_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.split()
    return [ROOT / f for f in out]


def private_names():
    """Client identities, read from the tree that is never committed."""
    cdir = ROOT / "clients"
    if not cdir.is_dir():
        return []
    names = [p.name for p in cdir.iterdir() if p.is_dir() and not p.name.startswith("_")]
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


if __name__ == "__main__":
    unittest.main()
