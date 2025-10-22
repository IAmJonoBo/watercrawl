# Watercrawl Environment Guide for Ephemeral Agents

This document provides comprehensive guidance for agents working in ephemeral runners to quickly understand and access the available development environments.

## Quick Discovery

Run the environment discovery script to see what's currently available:

```bash
python scripts/discover_environment.py
```

This will show you:

- Python version and interpreter location
- Available package managers (pip, poetry, uv, pnpm, npm)
- Project structure (pyproject.toml, poetry.lock, .venv, etc.)
- Bootstrap scripts availability
- Recommendations for setting up the environment

## Environment Types

### 1. Poetry Environment (Primary)

**Location**: `.venv/` (in-project virtual environment)

**Configuration**: `poetry.toml` specifies in-project virtualenv creation

**Setup**:

```bash
# Install Poetry if not available
pip install poetry

# Install dependencies
PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 poetry install --no-root --with dev

# Verify installation
poetry run python --version
```

> The bootstrap scripts and Just recipes export `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1`
> automatically. Include the same flag when running raw `poetry install` commands so
> PyO3-based wheels (such as `libcst`) build successfully on Python 3.14 runtimes.

**Usage**:

```bash
# Run any command in the Poetry environment
poetry run python script.py
poetry run pytest
poetry run mypy .

# Activate the virtual environment (optional)
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows
```

**Accessing installed packages**:

- All dependencies from `pyproject.toml` are available
- Dev dependencies are installed with `--with dev`
- Import paths: `firecrawl_demo`, `apps`, etc.

### 2. UV Environment (Optional)

**Purpose**: Fast Python package installer and version manager

**Setup**:

```bash
# Install UV
pip install uv

# Or use the bootstrap script
python -m scripts.bootstrap_python --install-uv --poetry
```

**Usage**:

```bash
# Install a specific Python version
uv python install 3.13.0

# Use UV to install packages faster
uv pip install <package>
```

### 3. Node.js Environment (For documentation)

**Location**: `node_modules/` (root and `docs-starlight/`)

**Package Manager**: pnpm (preferred) or npm

**Setup**:

```bash
# Enable corepack (includes pnpm)
corepack enable
corepack prepare pnpm@latest --activate

# Install dependencies
pnpm install --frozen-lockfile
```

**Usage**:

```bash
# Build docs
cd docs-starlight && pnpm run build

# Lint markdown
pnpm dlx markdownlint-cli2 '**/*.md'
```

## Bootstrap Process

### For Fresh Clones

1. **Run the comprehensive bootstrap script**:

   ```bash
   python -m scripts.bootstrap_env
   ```

   This will:
   - Install UV and Poetry if needed
   - Set up Poetry virtual environment
   - Install pre-commit hooks
   - Verify type stubs
   - Install Node.js dependencies (if needed)

2. **Verify the setup**:

    ```bash
    poetry run pytest -q
    poetry run ruff check .
    ```

### For CI/Ephemeral Runners

The `.github/workflows/copilot-setup-steps.yml` workflow automatically:

1. Sets up Python 3.13
2. Installs Poetry
3. Installs Python dependencies with `poetry install --no-root`
4. Sets up Node.js and pnpm
5. Installs Node dependencies
6. Verifies all tools are available

## Accessing Environments in Code

### From Python Scripts

```python
import sys
from pathlib import Path

# Check if running in Poetry venv
in_venv = hasattr(sys, 'real_prefix') or (
    hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
)

# Get project root
project_root = Path(__file__).parent.parent

# Access .venv directly
venv_python = project_root / ".venv" / "bin" / "python"
```

### From Shell Scripts

```bash
#!/bin/bash

# Use Poetry to run commands
poetry run python my_script.py

# Or activate the venv first
source .venv/bin/activate
python my_script.py

# Check if in venv
if [ -n "$VIRTUAL_ENV" ]; then
    echo "Running in virtual environment: $VIRTUAL_ENV"
fi
```

## Environment Variables

### Poetry-Related

- `POETRY_VIRTUALENVS_IN_PROJECT=true` - Create .venv in project (set in poetry.toml)
- `POETRY_VIRTUALENVS_CREATE=true` - Auto-create virtualenvs
- `VIRTUAL_ENV` - Path to active virtual environment

### Python-Related

- `PYTHONPATH` - Additional import paths (usually not needed with Poetry)
- `PYTHON_VERSION` - Target Python version (for CI)

### Project-Specific

Check `.env.example` for application-specific environment variables:

```bash
cp .env.example .env
# Edit .env with your configuration
```

## Common Tasks

### Running Tests

```bash
# All tests
poetry run pytest -q

# With coverage
poetry run pytest --cov=firecrawl_demo --cov-report=term-missing

# Specific test file
poetry run pytest tests/test_pipeline.py -v
```

### Code Quality

```bash
# Run individual checks
poetry run ruff check .
poetry run black --check .
poetry run isort --check-only .
poetry run mypy .

# Auto-fix issues
poetry run ruff check . --fix
poetry run black .
poetry run isort .
```

### Building

```bash
# Build Python package
poetry build

# Build documentation
cd docs-starlight && pnpm run build
```

## Troubleshooting

### "Poetry command not found"

```bash
# Install Poetry
pip install poetry

# Or use pipx (recommended)
pipx install poetry
```

### "Module not found" errors

```bash
# Ensure dependencies are installed
poetry install --no-root --with dev

# Verify you're using Poetry's Python
poetry run which python
```

### ".venv not found"

```bash
# Create the virtual environment
poetry install --no-root

# Verify creation
ls -la .venv/
```

### Network/PyPI issues

```bash
# Use UV for faster downloads
pip install uv
uv pip install -r requirements.txt

# Or use cached dependencies
poetry install --no-root --sync
```

### Permission issues

```bash
# Install to user directory
pip install --user poetry

# Or use sudo (not recommended)
sudo pip install poetry
```

## For Agent Authors

### Checking Environment State

```python
from scripts.discover_environment import (
    discover_python_environment,
    discover_project_structure,
    check_tool,
)

# Get current state
python_env = discover_python_environment()
project = discover_project_structure(Path.cwd())
poetry_info = check_tool("poetry")

if not poetry_info["available"]:
    print("Poetry not available, bootstrapping...")
    subprocess.run(["pip", "install", "poetry"])
```

### Running Commands Safely

```python
import subprocess
from pathlib import Path

def run_in_poetry(command: list[str], cwd: Path | None = None):
    """Run a command in the Poetry environment."""
    return subprocess.run(
        ["poetry", "run"] + command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )

# Example
result = run_in_poetry(["python", "-m", "pytest", "-q"])
```

### Bootstrap Check

```python
def ensure_environment():
    """Ensure the development environment is ready."""
    from scripts.discover_environment import check_tool, discover_project_structure
    
    project = discover_project_structure(Path.cwd())
    poetry = check_tool("poetry")
    
    if not poetry["available"]:
        subprocess.run([sys.executable, "-m", "pip", "install", "poetry"], check=True)
    
    if not project["venv_dir"]:
        subprocess.run(["poetry", "install", "--no-root"], check=True)
```

## References

- Bootstrap scripts: `scripts/bootstrap_*.py`
- CI workflow: `.github/workflows/ci.yml`
- Setup workflow: `.github/workflows/copilot-setup-steps.yml`
- Poetry config: `poetry.toml`, `pyproject.toml`
- Copilot instructions: `.github/copilot-instructions.md`
