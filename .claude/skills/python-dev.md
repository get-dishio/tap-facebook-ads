---
name: python-dev
description: Python development tooling — linting, formatting, pre-commit hooks, Poetry dependency management, virtual environments, CI configuration, and testing infrastructure
---

# Python Development Tooling

## Package Management (Poetry)

### Common Commands
```bash
poetry install                  # Install all dependencies (creates venv)
poetry add <package>            # Add a runtime dependency
poetry add --group dev <pkg>    # Add a dev dependency
poetry lock                     # Regenerate lockfile after manual pyproject.toml edits
poetry env use python3.11       # Switch Python version for the venv
poetry env remove --all         # Delete all venvs
poetry run <cmd>                # Run a command inside the venv
```

### pyproject.toml Structure
```toml
[tool.poetry.dependencies]      # Runtime deps
[tool.poetry.group.dev.dependencies]  # Dev-only deps (NOT the deprecated [tool.poetry.dev-dependencies])
[build-system]                  # Build backend (poetry-core, poetry-dynamic-versioning)
[tool.poetry.scripts]           # CLI entry points
```

### Dependency Version Specifiers
- `^1.0.0` — compatible release (>=1.0.0, <2.0.0)
- `~=1.0.0` — compatible minor (>=1.0.0, <1.1.0)
- `>=1.0,<2.0` — explicit range
- Always run `poetry lock` after editing version constraints

### Virtual Environments
- Poetry creates venvs in `~/Library/Caches/pypoetry/virtualenvs/` (macOS)
- Python version must match the `python` constraint in pyproject.toml
- If a transitive dep fails to build (e.g. greenlet on Python 3.14), switch to a supported Python version

## Linting (Ruff)

### Configuration
Ruff is configured in `pyproject.toml` under `[tool.ruff]` and `[tool.ruff.lint]`:

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["ALL"]           # Enable all rules, then ignore what's not applicable
ignore = ["DJ", "PD", ...] # Disable rule categories/codes

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", ...]  # Allow assert in tests, etc.

[tool.ruff.lint.pydocstyle]
convention = "google"
```

**Important**: Use `[tool.ruff.lint.*]` subsections, NOT top-level `[tool.ruff.flake8-import-conventions]` etc. — the top-level versions are deprecated.

### Commands
```bash
poetry run ruff check .           # Check for lint issues
poetry run ruff check . --fix     # Auto-fix what's fixable
poetry run ruff format .          # Format code (like black)
poetry run ruff check . --select E501  # Check specific rule
```

### Common Rule Categories
| Prefix | Meaning | When to Ignore |
|--------|---------|----------------|
| ANN | Type annotations | When codebase doesn't enforce full typing |
| D | Docstrings (pydocstyle) | On private/internal methods |
| E501 | Line too long | When using ruff-format (it handles this) |
| PLR | Pylint refactor (complexity) | On inherently complex methods |
| TRY | tryceratops (exception handling) | On retry/backoff patterns |
| ARG | Unused arguments | On SDK method overrides |
| COM812 | Trailing comma | Conflicts with ruff-format |

## Pre-commit Hooks

### Setup
```bash
pip install pre-commit          # Install pre-commit
pre-commit install              # Install hooks into .git/hooks
pre-commit run --all-files      # Run all hooks manually
pre-commit autoupdate           # Bump hook versions
```

### Configuration (`.pre-commit-config.yaml`)
Hooks run automatically on `git commit`. If a hook fails, the commit is blocked.

Common hooks for Python projects:
```yaml
repos:
- repo: https://github.com/pre-commit/pre-commit-hooks
  hooks:
  - id: check-json
  - id: check-toml
  - id: check-yaml
  - id: end-of-file-fixer
  - id: trailing-whitespace

- repo: https://github.com/astral-sh/ruff-pre-commit
  hooks:
  - id: ruff
    args: ["--fix", "--exit-non-zero-on-fix"]  # Auto-fix, fail if unfixable
  - id: ruff-format

- repo: https://github.com/pre-commit/mirrors-mypy
  hooks:
  - id: mypy
```

### Workflow
1. Make code changes
2. `poetry run ruff check . --fix` — fix lint issues before committing
3. `git add` + `git commit` — pre-commit hooks auto-run
4. If hooks modify files, re-stage and commit again
5. `--exit-non-zero-on-fix` ensures the commit is blocked when auto-fixes are applied, so you review them first

## Testing (pytest)

### Commands
```bash
poetry run pytest                  # Run all tests
poetry run pytest -v               # Verbose output
poetry run pytest tests/test_core.py::test_name  # Run specific test
poetry run pytest -k "not live"    # Skip tests matching pattern
poetry run pytest --capture=no     # Show print output
```

### Test Organization
- Unit tests: use mock config, no API calls, always run
- Integration tests: require live credentials, conditionally loaded
- Use `pytest.mark.skipif` for conditional test execution
- Use `LIVE_TEST_AVAILABLE` pattern to avoid KeyError on missing env vars:

```python
LIVE_TEST_AVAILABLE = bool(os.environ.get("API_TOKEN"))

if LIVE_TEST_AVAILABLE:
    # Only define integration test classes when creds exist
    TestClass = get_test_class(config=live_config)

@pytest.mark.skipif(not LIVE_TEST_AVAILABLE, reason="No API credentials")
def test_live_endpoint():
    ...
```

## CI/CD (GitHub Actions)

### Workflow Patterns
- **Lint job**: runs on all PRs, no secrets needed
- **Integration test job**: gated behind `workflow_dispatch` or secret availability
- **Release job**: triggered by tags, publishes to PyPI

### Python Version Matrix
```yaml
strategy:
  matrix:
    python-version: ["3.10", "3.11", "3.12", "3.13"]
```

### Key Actions
- `actions/checkout@v6` — checkout code
- `actions/setup-python@v6` — install Python
- `pipx install poetry` — install Poetry in CI

### CI Constraints File
`.github/workflows/constraints.txt` pins CI tool versions:
```
nox==2025.10.16
pip==25.3
poetry==2.2.1
```

## Type Checking (mypy)

### Configuration (`mypy.ini` or `pyproject.toml`)
```ini
[mypy]
ignore_missing_imports = True
```

### Running
```bash
poetry run mypy tap_facebook/
```

## Dependency Security

### Dependabot
Configure in `.github/dependabot.yml` to auto-create PRs for outdated deps:
```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: "/"
    schedule: { interval: daily }
  - package-ecosystem: github-actions
    directory: "/"
    schedule: { interval: weekly }
```

### Implicit Dependencies
If your code imports a package directly (e.g. `import pendulum`), it MUST be listed in `pyproject.toml` even if it's a transitive dependency of another package. Transitive deps can be removed in minor version bumps.
