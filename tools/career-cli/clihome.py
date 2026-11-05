"""A throwaway $CAREER_KIT_HOME for the CLI suites: clients/ and build/ live in a
temp dir, never in the checkout. Every name in it is invented."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAREER = ROOT / "bin" / "career"
CLIENT = "__datahome_test__"

JD_TEXT = """About the role
You will build audit trails and observability for the platform.
Experience with PostgreSQL and Kubernetes.
Equal opportunity statement
Example Corp is an equal opportunity employer and decides regardless of race.
"""


class Home:
    """Create with `Home()`, call .cleanup(); .run(*args) runs bin/career in it."""

    def __init__(self, with_profile=True):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name).resolve()
        self.client_dir = self.path / "clients" / CLIENT
        self.client_dir.mkdir(parents=True)
        if with_profile:
            shutil.copy(ROOT / "examples" / "profile.example.yml",
                        self.client_dir / "profile.yml")

    def cleanup(self):
        self._tmp.cleanup()

    def run(self, *args, home=None):
        env = {**os.environ, "CAREER_KIT_HOME": str(home or self.path)}
        return subprocess.run([str(CAREER), *args, "-c", CLIENT], capture_output=True,
                              text=True, timeout=120, cwd=ROOT, env=env)

    def jd_file(self):
        f = self.path / "jd.txt"
        f.write_text(JD_TEXT)
        return f

    def snapshot(self):
        """`career jd add` a posting from a file; returns the snapshot dir."""
        p = self.run("jd", "add", str(self.jd_file()), "--company", "Example Corp",
                     "--title", "Platform Engineer", "--location", "Riverton",
                     "--id", "EX-1", "--json")
        assert p.returncode == 0, p.stderr + p.stdout
        return Path(json.loads(p.stdout)["data"]["snapshot"])

    def fake_build(self, variant="baseline", text="Built audit trails on PostgreSQL.\n"):
        out = self.path / "build" / CLIENT / variant
        out.mkdir(parents=True)
        (out / "Ada_Lovelace_CV.md").write_text(text)
        return out
