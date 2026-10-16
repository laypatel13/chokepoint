"""A command run without its argument says what goes there, with an example (not a bare usage error)."""

import subprocess
import sys


def test_missing_argument_shows_an_example(tmp_path):
    env = {"CHOKEPOINT_DATA_DIR": str(tmp_path), "CHOKEPOINT_CACHE_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"}
    r = subprocess.run([sys.executable, "-c", "from chokepoint.cli import main; main()", "share"],
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 2
    assert "chokepoint share needs OWNER/REPO" in r.stderr and "chokepoint share axios/axios" in r.stderr
