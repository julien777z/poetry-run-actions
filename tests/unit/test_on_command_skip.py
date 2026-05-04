import subprocess
from unittest.mock import MagicMock

from poetry_run_actions.plugin import (
    CONFIG_TABLE,
    DEFAULT_ENV,
    ENV_VAR,
    PACKAGES_KEY,
    RunActionsPlugin,
)
from tests.unit._helpers import pyproject as _pyproject


class TestOnCommandSkipPaths:
    """Test that the listener does not run actions for non-`run` commands or no-op invocations."""

    def test_ignores_non_run_command(self, make_event, monkeypatch):
        """Test that the listener short-circuits when the command is not `run`."""

        run_mock = MagicMock()
        monkeypatch.setattr(subprocess, "run", run_mock)

        event = make_event(command_name="install", args=None, pyproject_data={})

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        run_mock.assert_not_called()

    def test_ignores_run_with_no_args(self, make_event, monkeypatch):
        """Test that `poetry run` with no script argument is a no-op."""

        run_mock = MagicMock()
        monkeypatch.setattr(subprocess, "run", run_mock)

        event = make_event(args=None)

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        run_mock.assert_not_called()

    def test_passthrough_when_no_actions_configured(self, make_event, monkeypatch):
        """Test that names with no configured entry do not invoke subprocess."""

        run_mock = MagicMock()
        monkeypatch.setattr(subprocess, "run", run_mock)

        event = make_event(args=["api"], pyproject_data={})

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        run_mock.assert_not_called()

    def test_unrelated_name_does_not_trigger_configured_actions(
        self, make_event, monkeypatch
    ):
        """Test that running name A does not execute name B's configured actions."""

        run_mock = MagicMock()
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject = _pyproject(
            DEFAULT_ENV, {PACKAGES_KEY: {"worker": "echo worker-only"}}
        )
        event = make_event(args=["api"], pyproject_data=pyproject)

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        run_mock.assert_not_called()

    def test_undeclared_package_is_passthrough(self, make_event, monkeypatch):
        """Test that a packages.<name> entry with no [tool.poetry] packages declaration is skipped."""

        run_mock = MagicMock()
        monkeypatch.setattr(subprocess, "run", run_mock)
        monkeypatch.delenv(ENV_VAR, raising=False)

        pyproject = {
            "tool": {
                CONFIG_TABLE: {DEFAULT_ENV: {PACKAGES_KEY: {"api": "echo nope"}}},
            }
        }
        event = make_event(args=["api"], pyproject_data=pyproject)

        RunActionsPlugin()._on_command(event, "console.command", MagicMock())

        run_mock.assert_not_called()
