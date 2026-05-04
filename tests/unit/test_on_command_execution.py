import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from poetry_run_actions.plugin import (
    COMMANDS_KEY,
    CONFIG_TABLE,
    DEFAULT_ENV,
    ENV_VAR,
    PACKAGES_KEY,
    SCRIPTS_KEY,
    SETUP_KEY,
    RunActionsPlugin,
)
from tests.unit._helpers import pyproject as _pyproject


class TestOnCommandExecution:
    """Test that the listener executes setup and pre-start actions in order with the correct cwd."""

    def test_runs_pre_start_commands_in_project_root(
        self, make_event, monkeypatch, tmp_path: Path
    ):
        """Test that pre-start commands run from the directory containing pyproject.toml."""

        run_mock = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject = _pyproject(
            DEFAULT_ENV, {PACKAGES_KEY: {"api": ["echo a", "echo b"]}}
        )
        event = make_event(args=["api"], pyproject_data=pyproject, pyproject_path=pyproject_path)

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        assert run_mock.call_count == 2
        for call, expected in zip(run_mock.call_args_list, ["echo a", "echo b"], strict=True):
            assert call.args[0] == expected
            assert call.kwargs["cwd"] == tmp_path
            assert call.kwargs["shell"] is True
            assert call.kwargs["check"] is False

    def test_runs_setup_before_pre_start_commands(
        self, make_event, monkeypatch, tmp_path: Path
    ):
        """Test that setup-commands run before pre-start-commands, both in declaration order."""

        run_mock = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject = _pyproject(
            DEFAULT_ENV,
            {
                PACKAGES_KEY: {
                    "api": {
                        SETUP_KEY: ["echo setup1", "echo setup2"],
                        COMMANDS_KEY: ["echo api"],
                    }
                }
            },
        )
        event = make_event(args=["api"], pyproject_data=pyproject, pyproject_path=pyproject_path)

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        executed = [call.args[0] for call in run_mock.call_args_list]

        assert executed == ["echo setup1", "echo setup2", "echo api"]

    def test_runs_only_setup_commands_when_pre_start_absent(
        self, make_event, monkeypatch, tmp_path: Path
    ):
        """Test that setup-only entries run their setup actions and nothing more."""

        run_mock = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject = _pyproject(
            DEFAULT_ENV, {PACKAGES_KEY: {"api": {SETUP_KEY: "echo setup"}}}
        )
        event = make_event(args=["api"], pyproject_data=pyproject, pyproject_path=pyproject_path)

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        assert run_mock.call_count == 1
        assert run_mock.call_args.args[0] == "echo setup"

    def test_uses_environment_variable_to_select_table(
        self, make_event, monkeypatch, tmp_path: Path
    ):
        """Test that POETRY_ENVIRONMENT selects which environment table is read."""

        run_mock = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.setenv(ENV_VAR, "staging")

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject = {
            "tool": {
                "poetry": {"packages": [{"include": "api"}]},
                CONFIG_TABLE: {
                    "dev": {PACKAGES_KEY: {"api": "echo dev"}},
                    "staging": {PACKAGES_KEY: {"api": "echo staging"}},
                },
            }
        }
        event = make_event(args=["api"], pyproject_data=pyproject, pyproject_path=pyproject_path)

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        assert run_mock.call_count == 1
        assert run_mock.call_args.args[0] == "echo staging"

    def test_unset_environment_falls_back_to_default(
        self, make_event, monkeypatch, tmp_path: Path
    ):
        """Test that an unset POETRY_ENVIRONMENT falls back to the dev table."""

        run_mock = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject = _pyproject(DEFAULT_ENV, {PACKAGES_KEY: {"api": "echo dev"}})
        event = make_event(args=["api"], pyproject_data=pyproject, pyproject_path=pyproject_path)

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        assert run_mock.call_count == 1
        assert run_mock.call_args.args[0] == "echo dev"

    def test_nonzero_exit_continues_remaining_actions(
        self, make_event, monkeypatch, tmp_path: Path
    ):
        """Test that a failing action prints a warning but does not stop subsequent actions."""

        run_mock = MagicMock(
            side_effect=[
                MagicMock(returncode=1),
                MagicMock(returncode=0),
            ]
        )
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject = _pyproject(
            DEFAULT_ENV, {PACKAGES_KEY: {"api": ["echo first", "echo second"]}}
        )
        event = make_event(args=["api"], pyproject_data=pyproject, pyproject_path=pyproject_path)

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        executed = [call.args[0] for call in run_mock.call_args_list]

        assert executed == ["echo first", "echo second"]
        event.io.write_error_line.assert_called_once()
        assert "code 1" in event.io.write_error_line.call_args.args[0]

    def test_setup_label_includes_target_name(
        self, make_event, monkeypatch, tmp_path: Path
    ):
        """Test that setup-command log lines are labelled `<name>/setup-commands`."""

        run_mock = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject = _pyproject(
            DEFAULT_ENV, {PACKAGES_KEY: {"api": {SETUP_KEY: "echo s"}}}
        )
        event = make_event(args=["api"], pyproject_data=pyproject, pyproject_path=pyproject_path)

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        log_messages = [call.args[0] for call in event.io.write_line.call_args_list]

        assert any(f"api/{SETUP_KEY}" in message for message in log_messages)

    def test_script_target_executes(self, make_event, monkeypatch, tmp_path: Path):
        """Test that scripts.<name> entries execute when invoked."""

        run_mock = MagicMock(return_value=MagicMock(returncode=0))
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject = _pyproject(
            DEFAULT_ENV, {SCRIPTS_KEY: {"migrate": "echo migrate"}}
        )
        event = make_event(
            args=["migrate"], pyproject_data=pyproject, pyproject_path=pyproject_path
        )

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        assert run_mock.call_count == 1
        assert run_mock.call_args.args[0] == "echo migrate"
