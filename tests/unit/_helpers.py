from poetry_run_actions.plugin import CONFIG_TABLE


def pyproject(
    env: str,
    mapping: dict[str, object],
    *,
    packages: list[str] | None = None,
    scripts: list[str] | None = None,
) -> dict:
    """Build a pyproject-like dict containing the actions table and declared targets."""

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
