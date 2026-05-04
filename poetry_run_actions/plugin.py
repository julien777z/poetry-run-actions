import logging
import os
import subprocess
from typing import Final

from cleo.events.console_command_event import ConsoleCommandEvent
from cleo.events.console_events import COMMAND
from cleo.events.event_dispatcher import EventDispatcher
from poetry.console.application import Application
from poetry.plugins.application_plugin import ApplicationPlugin

from poetry_run_actions.utils import (
    coerce_commands,
    extract_target_name,
    get_configured_packages,
    get_configured_scripts,
)

logger = logging.getLogger(__name__)

ENV_VAR: Final[str] = "POETRY_ENVIRONMENT"
DEFAULT_ENV: Final[str] = "dev"
CONFIG_TABLE: Final[str] = "poetry-run-actions"
PACKAGES_KEY: Final[str] = "packages"
SCRIPTS_KEY: Final[str] = "scripts"
SETUP_KEY: Final[str] = "setup-commands"
COMMANDS_KEY: Final[str] = "pre-start-commands"


class RunActionsPlugin(ApplicationPlugin):
    """Run declarative shell actions before `poetry run <name>`, gated by environment."""

    def activate(self, application: Application) -> None:
        """Register the COMMAND event listener on the Poetry application."""

        application.event_dispatcher.add_listener(COMMAND, self._on_command)

    def _on_command(
        self,
        event: ConsoleCommandEvent,
        event_name: str,
        dispatcher: EventDispatcher,
    ) -> None:
        """Look up and execute configured actions for the package or script invoked by `poetry run`."""

        command = event.command

        if command.name != "run":
            return

        raw_args = event.io.input.argument("args")

        if not raw_args:
            return

        name = extract_target_name(raw_args)

        if name is None:
            return

        environment = os.environ.get(ENV_VAR, DEFAULT_ENV)

        setup_actions, pre_start_actions = self._resolve_target_entry(
            command.poetry.pyproject.data, environment, name
        )

        if not setup_actions and not pre_start_actions:
            return

        project_root = command.poetry.pyproject_path.parent

        for label, action in [
            *((f"{name}/{SETUP_KEY}", action) for action in setup_actions),
            *((name, action) for action in pre_start_actions),
        ]:
            event.io.write_line(
                f"<info>[poetry-run-actions]</info> "
                f"<comment>{environment}/{label}</comment> -> {action}"
            )

            result = subprocess.run(
                action,
                cwd=project_root,
                shell=True,
                check=False,
            )

            if result.returncode != 0:
                event.io.write_error_line(
                    f"<warning>[poetry-run-actions] action exited with "
                    f"code {result.returncode}; continuing.</warning>"
                )

    @classmethod
    def _resolve_target_entry(
        cls, pyproject_data: dict, environment: str, name: str
    ) -> tuple[list[str], list[str]]:
        """Return (setup, pre-start) lists for the configured package or script entry."""

        env_table = pyproject_data.get("tool", {}).get(CONFIG_TABLE, {}).get(environment, {})

        if not isinstance(env_table, dict):
            return [], []

        packages_table = env_table.get(PACKAGES_KEY, {})
        scripts_table = env_table.get(SCRIPTS_KEY, {})

        configured_packages = get_configured_packages(pyproject_data)
        configured_scripts = get_configured_scripts(pyproject_data)

        pkg_entry = (
            packages_table.get(name)
            if isinstance(packages_table, dict) and name in configured_packages
            else None
        )
        script_entry = (
            scripts_table.get(name)
            if isinstance(scripts_table, dict) and name in configured_scripts
            else None
        )

        if pkg_entry is not None and script_entry is not None:
            logger.warning(
                "poetry-run-actions: %r is configured under both %s.%s.%s and %s.%s.%s; "
                "firing neither.",
                name,
                CONFIG_TABLE,
                environment,
                PACKAGES_KEY,
                CONFIG_TABLE,
                environment,
                SCRIPTS_KEY,
            )

            return [], []

        if pkg_entry is not None:
            return cls._coerce_entry(pkg_entry, environment, PACKAGES_KEY, name)

        if script_entry is not None:
            return cls._coerce_entry(script_entry, environment, SCRIPTS_KEY, name)

        return [], []

    @classmethod
    def _coerce_entry(
        cls, value: object, environment: str, kind: str, name: str
    ) -> tuple[list[str], list[str]]:
        """Coerce an entry value (str | list | full table) into (setup, pre-start) lists."""

        match value:
            case None:
                return [], []
            case str() | list():
                return [], coerce_commands(value, environment, kind, name, None, CONFIG_TABLE)
            case dict():
                setup = coerce_commands(
                    value.get(SETUP_KEY), environment, kind, name, SETUP_KEY, CONFIG_TABLE
                )
                commands = coerce_commands(
                    value.get(COMMANDS_KEY), environment, kind, name, COMMANDS_KEY, CONFIG_TABLE
                )

                return setup, commands
            case _:
                logger.warning(
                    "poetry-run-actions: ignoring %s.%s.%s.%s; "
                    "expected str, list[str], or table, got %r",
                    CONFIG_TABLE,
                    environment,
                    kind,
                    name,
                    value,
                )

                return [], []
