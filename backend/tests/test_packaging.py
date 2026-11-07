import tomllib
from pathlib import Path


def test_upgrades_reinstall_the_backend_when_its_source_changes():
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    keys = [key.get("file") for key in project["tool"]["uv"]["cache-keys"]]
    assert "src/**/*.py" in keys
    assert "pyproject.toml" in keys
