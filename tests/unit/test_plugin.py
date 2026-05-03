import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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


def _pyproject(
    env: str,
    mapping: dict[str, object],
    *,
    packages: list[str] | None = None,
    scripts: list[str] | None = None,
) -> dict:
    """Build a pyproject-like dict containing the actions table and declared targets.

    `mapping` is the contents of `tool.poetry-run-actions.<env>` (e.g.
    `{"packages": {"api": "echo"}}`). `packages` defaults to `["api",
    "worker"]` and `scripts` defaults to `["migrate"]` so the gate passes
    for the names used across these tests.
    """

    if packages is None:
        packages = ["api", "worker"]

    if scripts is None:
        scripts = ["migrate"]

    return {
        "project": {"scripts": {s: f"placeholder.{s}:main" for s in scripts}},
        "tool": {
            "poetry": {"packages": [{"include": p} for p in packages]},
            CONFIG_TABLE: {env: mapping},
        },
    }


class TestResolveTargetEntry:
    """Test that the target entry resolver reads tool.poetry-run-actions tables correctly."""

    def test_returns_empty_when_table_missing(self):
        """Test that resolve returns empty lists when the actions table is absent."""

        setup, commands = RunActionsPlugin._resolve_target_entry({}, "dev", "api")

        assert setup == []
        assert commands == []

    def test_returns_empty_when_environment_missing(self):
        """Test that resolve returns empty lists when the environment table is absent."""

        pyproject = _pyproject("dev", {PACKAGES_KEY: {"api": "echo hi"}})

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "production", "api")

        assert setup == []
        assert commands == []

    def test_returns_empty_when_target_kind_missing(self):
        """Test that resolve returns empty lists when neither packages nor scripts subtables exist."""

        pyproject = _pyproject("dev", {})

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "api")

        assert setup == []
        assert commands == []

    def test_returns_empty_when_name_missing_under_packages(self):
        """Test that resolve returns empty lists when the package key is absent."""

        pyproject = _pyproject("dev", {PACKAGES_KEY: {"api": "echo hi"}})

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "worker")

        assert setup == []
        assert commands == []

    def test_returns_empty_when_name_missing_under_scripts(self):
        """Test that resolve returns empty lists when the script key is absent."""

        pyproject = _pyproject(
            "dev",
            {SCRIPTS_KEY: {"migrate": "echo hi"}},
            scripts=["migrate", "lint"],
        )

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "lint")

        assert setup == []
        assert commands == []

    def test_string_shorthand_under_packages(self):
        """Test that a bare string entry under packages becomes a single pre-start command."""

        pyproject = _pyproject("dev", {PACKAGES_KEY: {"api": "echo hi"}})

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "api")

        assert setup == []
        assert commands == ["echo hi"]

    def test_string_shorthand_under_scripts(self):
        """Test that a bare string entry under scripts becomes a single pre-start command."""

        pyproject = _pyproject("dev", {SCRIPTS_KEY: {"migrate": "echo hi"}})

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "migrate")

        assert setup == []
        assert commands == ["echo hi"]

    def test_list_shorthand_under_packages(self):
        """Test that a list entry under packages becomes the pre-start command list in order."""

        pyproject = _pyproject(
            "dev", {PACKAGES_KEY: {"api": ["echo a", "echo b", "echo c"]}}
        )

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "api")

        assert setup == []
        assert commands == ["echo a", "echo b", "echo c"]

    def test_full_form_under_packages_returns_setup_and_pre_start_commands(self):
        """Test that the full table form under packages populates both lists."""

        pyproject = _pyproject(
            "dev",
            {
                PACKAGES_KEY: {
                    "api": {
                        SETUP_KEY: ["docker compose up -d redis"],
                        COMMANDS_KEY: "echo starting api",
                    }
                }
            },
        )

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "api")

        assert setup == ["docker compose up -d redis"]
        assert commands == ["echo starting api"]

    def test_full_form_under_scripts_returns_setup_and_pre_start_commands(self):
        """Test that the full table form under scripts populates both lists."""

        pyproject = _pyproject(
            "dev",
            {
                SCRIPTS_KEY: {
                    "migrate": {
                        SETUP_KEY: "echo s",
                        COMMANDS_KEY: ["echo c"],
                    }
                }
            },
        )

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "migrate")

        assert setup == ["echo s"]
        assert commands == ["echo c"]

    def test_full_form_with_only_setup_commands(self):
        """Test that the full form works when only setup-commands is provided."""

        pyproject = _pyproject(
            "dev", {PACKAGES_KEY: {"api": {SETUP_KEY: "echo setup"}}}
        )

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "api")

        assert setup == ["echo setup"]
        assert commands == []

    def test_full_form_with_only_pre_start_commands(self):
        """Test that the full form works when only pre-start-commands is provided."""

        pyproject = _pyproject(
            "dev", {PACKAGES_KEY: {"api": {COMMANDS_KEY: ["echo go"]}}}
        )

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "api")

        assert setup == []
        assert commands == ["echo go"]

    @pytest.mark.parametrize(
        ("value", "expected_warning_fragment"),
        [
            (123, "got 123"),
            (("echo a", "echo b"), "got ('echo a'"),
        ],
        ids=["int", "tuple"],
    )
    def test_invalid_top_level_value_logs_warning_and_returns_empty(
        self, value: object, expected_warning_fragment: str, caplog: pytest.LogCaptureFixture
    ):
        """Test that an unsupported top-level entry shape logs a warning and yields nothing."""

        pyproject = _pyproject("dev", {PACKAGES_KEY: {"api": value}})

        with caplog.at_level("WARNING"):
            setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "api")

        assert setup == []
        assert commands == []
        assert any(expected_warning_fragment in record.getMessage() for record in caplog.records)

    def test_invalid_inner_value_logs_warning_with_sub_key(
        self, caplog: pytest.LogCaptureFixture
    ):
        """Test that an invalid inner value warns with the full table.env.kind.name.sub-key path."""

        pyproject = _pyproject("dev", {PACKAGES_KEY: {"api": {SETUP_KEY: 42}}})

        with caplog.at_level("WARNING"):
            setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "api")

        assert setup == []
        assert commands == []
        assert any(
            f"{CONFIG_TABLE}.dev.{PACKAGES_KEY}.api.{SETUP_KEY}" in record.getMessage()
            for record in caplog.records
        )

    def test_mixed_list_inner_value_logs_warning(self, caplog: pytest.LogCaptureFixture):
        """Test that a list mixing strings and non-strings is rejected and warned about."""

        pyproject = _pyproject(
            "dev", {PACKAGES_KEY: {"api": {COMMANDS_KEY: ["echo a", 7]}}}
        )

        with caplog.at_level("WARNING"):
            setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "api")

        assert setup == []
        assert commands == []
        assert any(
            f"{CONFIG_TABLE}.dev.{PACKAGES_KEY}.api.{COMMANDS_KEY}" in record.getMessage()
            for record in caplog.records
        )

    def test_unknown_package_does_not_fire(self):
        """Test that an entry under packages.<name> with no matching declared package is skipped."""

        pyproject = _pyproject(
            "dev",
            {PACKAGES_KEY: {"ghost": "echo nope"}},
            packages=["api", "worker"],
        )

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "ghost")

        assert setup == []
        assert commands == []

    def test_unknown_script_does_not_fire(self):
        """Test that an entry under scripts.<name> with no matching declared script is skipped."""

        pyproject = _pyproject(
            "dev",
            {SCRIPTS_KEY: {"ghost": "echo nope"}},
            scripts=["migrate"],
        )

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "ghost")

        assert setup == []
        assert commands == []

    def test_both_packages_and_scripts_configured_warns_and_returns_empty(
        self, caplog: pytest.LogCaptureFixture
    ):
        """Test that a name configured under both packages and scripts logs a warning and fires neither."""

        pyproject = _pyproject(
            "dev",
            {
                PACKAGES_KEY: {"api": "echo pkg"},
                SCRIPTS_KEY: {"api": "echo script"},
            },
            packages=["api"],
            scripts=["api"],
        )

        with caplog.at_level("WARNING"):
            setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "api")

        assert setup == []
        assert commands == []
        assert any(
            f"{CONFIG_TABLE}.dev.{PACKAGES_KEY}" in record.getMessage()
            and f"{CONFIG_TABLE}.dev.{SCRIPTS_KEY}" in record.getMessage()
            for record in caplog.records
        )

    def test_scripts_picked_up_from_tool_poetry_scripts(self):
        """Test that script names from [tool.poetry.scripts] are honored as a valid declaration."""

        pyproject = {
            "tool": {
                "poetry": {
                    "packages": [{"include": "ignored"}],
                    "scripts": {"migrate": "placeholder.migrate:main"},
                },
                CONFIG_TABLE: {"dev": {SCRIPTS_KEY: {"migrate": "echo m"}}},
            }
        }

        setup, commands = RunActionsPlugin._resolve_target_entry(pyproject, "dev", "migrate")

        assert setup == []
        assert commands == ["echo m"]


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
