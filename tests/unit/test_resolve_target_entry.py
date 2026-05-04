import pytest

from poetry_run_actions.plugin import (
    COMMANDS_KEY,
    CONFIG_TABLE,
    PACKAGES_KEY,
    SCRIPTS_KEY,
    SETUP_KEY,
    RunActionsPlugin,
)
from tests.unit._helpers import pyproject as _pyproject


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
