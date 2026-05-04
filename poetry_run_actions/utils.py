import logging
import os
import re

logger = logging.getLogger(__name__)

_PYTHON_INTERPRETER_RE = re.compile(r"python\d*(?:\.\d+)?")


def is_python_interpreter(token: str) -> bool:
    """Return True if `token` looks like a python interpreter executable."""

    return bool(_PYTHON_INTERPRETER_RE.fullmatch(os.path.basename(token)))


def extract_target_name(raw_args: list[str]) -> str | None:
    """Return the logical target name, unwrapping `python -m <module>` to its top-level package."""

    if not raw_args:
        return None

    first = raw_args[0]

    if is_python_interpreter(first):
        for index in range(1, len(raw_args) - 1):
            if raw_args[index] == "-m":
                module = raw_args[index + 1]
                top_level = module.split(".", 1)[0]

                return top_level or raw_args[0]

    return raw_args[0]


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
            location = (
                f"{config_table}.{environment}.{kind}.{name}"
                if sub_key is None
                else f"{config_table}.{environment}.{kind}.{name}.{sub_key}"
            )
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
