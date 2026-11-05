import shutil
import subprocess
import time

import pytest

from finhub_backend import engines, installer


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_install_creates_env_outside_source_dir(tmp_path, monkeypatch):
    # A tiny stand-in project in place of the real engine: same install path, no downloads.
    src = tmp_path / "engines" / "openbb"
    src.mkdir(parents=True)
    (src / "pyproject.toml").write_text(
        '[project]\nname = "stand-in"\nversion = "0"\nrequires-python = ">=3.12"\ndependencies = []\n'
        "[tool.uv]\npackage = false\n"
    )
    subprocess.run(["uv", "lock", "--project", str(src)], check=True, capture_output=True)
    monkeypatch.setenv("FINHUB_ENGINES_DIR", str(tmp_path / "engines"))
    monkeypatch.setenv("FINHUB_ENGINE_ENVS_DIR", str(tmp_path / "envs"))

    st = installer.install("openbb")
    deadline = time.time() + 120
    while st.state == "running" and time.time() < deadline:
        time.sleep(0.2)

    assert st.state == "done", st.public()
    assert engines.engine_python("openbb").exists()
    assert str(engines.engine_python("openbb")).startswith(str(tmp_path / "envs"))
    assert not (src / ".venv").exists()  # the (possibly read-only) source folder is untouched


def test_unknown_engine_is_rejected():
    with pytest.raises(KeyError):
        installer.install("nope")
