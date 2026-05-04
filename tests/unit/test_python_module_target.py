import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from poetry_run_actions.plugin import (
    COMMANDS_KEY,
    DEFAULT_ENV,
    ENV_VAR,
    PACKAGES_KEY,
    RunActionsPlugin,
)
from tests.unit._helpers import pyproject as _pyproject


class TestPythonModuleTargetResolution:
    """Test that `poetry run python -m <module>` resolves to the matching package entry."""

    def test_python_dash_m_module_resolves_to_package(
        self, make_event, monkeypatch, tmp_path: Path
    ):
        """Test that `python -m api` fires the actions configured for the `api` package."""

        run_mock = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject = _pyproject(
            DEFAULT_ENV,
            {PACKAGES_KEY: {"api": {COMMANDS_KEY: ["docker compose up -d redis"]}}},
        )
        event = make_event(
            args=["python", "-m", "api"],
            pyproject_data=pyproject,
            pyproject_path=pyproject_path,
        )

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        assert run_mock.call_count == 1
        assert run_mock.call_args.args[0] == "docker compose up -d redis"

    def test_python_dash_m_dotted_module_resolves_to_top_level_package(
        self, make_event, monkeypatch, tmp_path: Path
    ):
        """Test that `python -m api.cli` matches the `api` package entry."""

        run_mock = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject = _pyproject(DEFAULT_ENV, {PACKAGES_KEY: {"api": "echo api"}})
        event = make_event(
            args=["python3.12", "-m", "api.cli"],
            pyproject_data=pyproject,
            pyproject_path=pyproject_path,
        )

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        assert run_mock.call_count == 1
        assert run_mock.call_args.args[0] == "echo api"

    def test_python_with_flags_before_dash_m_is_resolved(
        self, make_event, monkeypatch, tmp_path: Path
    ):
        """Test that interpreter flags between `python` and `-m` do not break resolution."""

        run_mock = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject = _pyproject(DEFAULT_ENV, {PACKAGES_KEY: {"api": "echo api"}})
        event = make_event(
            args=["python", "-u", "-m", "api"],
            pyproject_data=pyproject,
            pyproject_path=pyproject_path,
        )

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        assert run_mock.call_count == 1
        assert run_mock.call_args.args[0] == "echo api"

    def test_python_running_a_script_path_falls_through(
        self, make_event, monkeypatch, tmp_path: Path
    ):
        """Test that `python script.py` keeps `python` as the lookup name."""

        run_mock = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject = _pyproject(DEFAULT_ENV, {PACKAGES_KEY: {"api": "echo api"}})
        event = make_event(
            args=["python", "script.py"],
            pyproject_data=pyproject,
            pyproject_path=pyproject_path,
        )

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        run_mock.assert_not_called()
