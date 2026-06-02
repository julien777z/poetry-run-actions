import logging
import os
import re

logger = logging.getLogger(__name__)

PYTHON_INTERPRETER_RE = re.compile(r"python\d*(?:\.\d+)?")


def is_python_interpreter(token: str) -> bool:
    """Return True if `token` looks like a python interpreter executable."""

    return bool(PYTHON_INTERPRETER_RE.fullmatch(os.path.basename(token)))


def extract_target_name(raw_args: list[str]) -> str:
    """Return the logical target name, unwrapping `python -m <module>` to its top-level package."""

    first = raw_args[0]

    if not is_python_interpreter(first):
        return first

    flags = raw_args[1:]

    if "-m" not in flags:
        return first

    module_index = flags.index("-m") + 1

    if module_index >= len(flags):
        return first

    return flags[module_index].split(".", 1)[0] or first


def coerce_commands(
    value: object,
    environment: str,
    kind: str,
    name: str,
    sub_key: str | None,
    config_table: str,
) -> list[str]:
    """Coerce a str or list[str] config value into a list, warning on other shapes."""

    match value:
        case None:
            return []
        case str():
            return [value]
        case list() if all(isinstance(item, str) for item in value):
            return list(value)
        case _:
            parts = [config_table, environment, kind, name, sub_key]
            location = ".".join(part for part in parts if part is not None)

            logger.warning(
                "poetry-run-actions: ignoring %s; expected str or list[str], got %r",
                location,
                value,
            )

            return []


def get_configured_packages(pyproject_data: dict) -> set[str]:
    """Return the set of package names from `[tool.poetry] packages`."""

    packages = pyproject_data.get("tool", {}).get("poetry", {}).get("packages", [])

    if not isinstance(packages, list):
        return set()

    return {
        entry["include"]
        for entry in packages
        if isinstance(entry, dict) and isinstance(entry.get("include"), str)
    }


def get_configured_scripts(pyproject_data: dict) -> set[str]:
    """Return the set of script names from `[project.scripts]` and `[tool.poetry.scripts]`."""

    project_scripts = pyproject_data.get("project", {}).get("scripts", {})
    tool_scripts = pyproject_data.get("tool", {}).get("poetry", {}).get("scripts", {})

    out: set[str] = set()

    for src in (project_scripts, tool_scripts):
        if isinstance(src, dict):
            out.update(k for k in src if isinstance(k, str))

    return out
