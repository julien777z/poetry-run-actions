# Poetry Run Actions Plugin

A Poetry plugin that runs declarative shell actions immediately
before `poetry run <name>`, gated by the active environment.

Use it to attach side effects (e.g. `docker compose up -d redis`) to a package
or script without baking them into the entry point itself, so the same
`pyproject.toml` can be deployed in production without firing dev-only setup.

## Install

Install via Poetry:

```bash
poetry self add poetry-run-actions
```

To uninstall:

```bash
poetry self remove poetry-run-actions
```

## Configure

Actions attach to a **package** declared in `[tool.poetry] packages` or a
**script** declared in `[project.scripts]` / `[tool.poetry.scripts]`.
Configure them under separate subtables:

```toml
[tool.poetry]
packages = [{include = "api"}, {include = "worker"}]

[project.scripts]
migrate = "myapp.db:migrate"

# Package target: fires on `poetry run api` because `api` is in [tool.poetry] packages
[tool.poetry-run-actions.dev.packages.api]
setup-commands = ["docker compose up -d redis"]
pre-start-commands = ["echo 'starting api'"]

# Script target: fires on `poetry run migrate` because `migrate` is in [project.scripts]
[tool.poetry-run-actions.dev.scripts.migrate]
pre-start-commands = "echo 'about to migrate'"
```

Each entry under `packages.<name>` or `scripts.<name>` can take one of three
shapes:

```toml
# 1. Shorthand: a single shell command (treated as `pre-start-commands`)
[tool.poetry-run-actions.dev.packages]
worker = "docker compose up -d postgres"

# 2. Shorthand: a list of shell commands (treated as `pre-start-commands`)
[tool.poetry-run-actions.dev.packages]
cli = ["docker compose up -d redis", "docker compose up -d postgres"]

# 3. Full form: a table with `setup-commands` and/or `pre-start-commands`
[tool.poetry-run-actions.dev.packages.api]
setup-commands = ["docker compose up -d redis"]
pre-start-commands = ["echo 'starting api'"]
```

### `setup-commands` vs. `pre-start-commands`

Both are optional and accept either a single string or a list of strings.
On every matching `poetry run <name>` invocation, the plugin runs:

Setup commands should be idempotent and run before the pre-start commands. This can be used to install dependencies.
Pre-start commands are for application dependencies, such as Redis.

## Environment Selection

The active environment is read from `POETRY_ENVIRONMENT`, defaulting to `dev`.

Example:

| `POETRY_ENVIRONMENT` | Behavior                                                                             |
|----------------------|--------------------------------------------------------------------------------------|
| unset (default)      | Looks up `tool.poetry-run-actions.dev.{packages,scripts}.<name>`                     |
| `dev`                | Same as default                                                                      |
| `production`         | Looks up `tool.poetry-run-actions.production.{packages,scripts}.<name>`              |
| any other value      | Looks up `tool.poetry-run-actions.<value>.{packages,scripts}.<name>`                 |

## Run Tests

Install development dependencies:

```bash
poetry install -E dev
```

Run tests:

```bash
poetry run pytest .
```