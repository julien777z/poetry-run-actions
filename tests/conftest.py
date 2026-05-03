from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def make_event():
    """Build a fake ConsoleCommandEvent for the `poetry run` command."""

    def _build(
        *,
        command_name: str = "run",
        args: list[str] | None,
        pyproject_data: dict | None = None,
        pyproject_path: Path | None = None,
    ) -> MagicMock:
        event = MagicMock()
        event.command.name = command_name
        event.io.input.argument.return_value = args
        event.command.poetry.pyproject.data = pyproject_data or {}
        event.command.poetry.pyproject_path = pyproject_path or Path("/tmp/pyproject.toml")

        return event

    return _build
