# Watercrawl Development Tasks
# https://github.com/casey/just

# Default recipe (show help)
default:
    @just --list

# Bootstrap development environment
bootstrap:
    @echo "Bootstrapping development environment..."
    python -m scripts.bootstrap_env

# Install dependencies with Poetry
install:
    @echo "Installing dependencies..."
    poetry install --no-root

# Install with development dependencies
install-dev:
    @echo "Installing with dev dependencies..."
    poetry install --no-root --with dev

# Run all tests
test:
    @echo "Running tests..."
    poetry run pytest --maxfail=5 --disable-warnings

# Run tests with coverage
test-cov:
    @echo "Running tests with coverage..."
    poetry run pytest --cov=firecrawl_demo --cov-report=term-missing --cov-report=xml

# Run specific test file
test-file FILE:
    @echo "Running tests in {{FILE}}..."
    poetry run pytest {{FILE}} -v

# Run linting checks
lint:
    @echo "Running linters..."
    poetry run ruff check .
    poetry run black --check .
    poetry run isort --check-only --profile black .

# Auto-fix linting issues
fmt:
    @echo "Formatting code..."
    poetry run ruff check . --fix
    poetry run black .
    poetry run isort --profile black .

# Run type checking
typecheck:
    @echo "Running type checks..."
    ./scripts/run_with_stubs.sh -- poetry run mypy . --show-error-codes

# Run security scan
security:
    @echo "Running security scan..."
    poetry run bandit -r firecrawl_demo

# Run all quality checks
qa: lint typecheck security test
    @echo "All quality checks passed!"

# Run data contracts
contracts:
    @echo "Running data contracts..."
    poetry run python -m apps.analyst.cli contracts data/sample.csv --format json

# Check contract coverage
coverage:
    @echo "Checking contract coverage..."
    poetry run python -m apps.analyst.cli coverage --format json

# Aggregate problems report
problems:
    @echo "Generating problems report..."
    poetry run python scripts/collect_problems.py --output problems_report.json

# Clean build artifacts and caches
clean:
    @echo "Cleaning artifacts..."
    poetry run python -m scripts.cleanup --dry-run
    @read -p "Proceed with cleanup? (y/N) " confirm && [ "$$confirm" = "y" ] && poetry run python -m scripts.cleanup || echo "Cleanup cancelled"

# Build distribution packages
build:
    @echo "Building distribution..."
    poetry build

# Generate SBOM
sbom:
    @echo "Generating SBOM..."
    mkdir -p artifacts/sbom
    cyclonedx-bom --poetry pyproject.toml --format json --output artifacts/sbom/cyclonedx.json

# Run analyst CLI overview
overview:
    @echo "Running analyst overview..."
    poetry run python -m apps.analyst.cli overview

# Validate dataset
validate FILE:
    @echo "Validating {{FILE}}..."
    poetry run python -m apps.analyst.cli validate {{FILE}} --format json

# Enrich dataset
enrich INPUT OUTPUT:
    @echo "Enriching {{INPUT}} to {{OUTPUT}}..."
    poetry run python -m apps.analyst.cli enrich {{INPUT}} --output {{OUTPUT}}

# Run MCP server
mcp:
    @echo "Starting MCP server..."
    poetry run python -m app.cli mcp-server

# Build and preview documentation
docs:
    @echo "Building documentation..."
    poetry run mkdocs serve

# Run Streamlit analyst UI
ui:
    @echo "Starting Streamlit UI..."
    poetry run streamlit run apps/analyst/app.py

# Run accessibility smoke test
axe:
    @echo "Running accessibility tests..."
    poetry run python apps/analyst/accessibility/axe_smoke.py

# Docker build
docker-build:
    @echo "Building Docker image..."
    docker build -t watercrawl:latest .

# Docker run with security hardening
docker-run:
    @echo "Running Docker container..."
    docker-compose up

# Dependency audit
audit:
    @echo "Auditing dependencies..."
    poetry run python -m tools.security.offline_safety --requirements requirements.txt --requirements requirements-dev.txt

# Wheel status check
wheel-status:
    @echo "Checking wheel compatibility..."
    poetry run python -m scripts.wheel_status --output tools/dependency_matrix/wheel_status.json

# Export requirements
export:
    @echo "Exporting requirements..."
    poetry export -f requirements.txt --output requirements.txt --without-hashes
    poetry export -f requirements.txt --with dev --output requirements-dev.txt --without-hashes

# Run mutation tests (pilot)
mutation:
    @echo "Running mutation tests..."
    poetry run python -m apps.automation.cli qa mutation

# Run pre-commit hooks
pre-commit:
    @echo "Running pre-commit hooks..."
    poetry run pre-commit run --all-files

# Check dependency updates
outdated:
    @echo "Checking for outdated dependencies..."
    poetry show --outdated

# Update dependencies
update:
    @echo "Updating dependencies..."
    poetry update

# Sync type stubs
sync-stubs:
    @echo "Syncing type stubs..."
    poetry run python -m scripts.sync_type_stubs --sync

# Run SQLFluff
sqlfluff:
    @echo "Running SQLFluff..."
    poetry run python -m tools.sql.sqlfluff_runner

# Run YAML lint
yamllint:
    @echo "Running yamllint..."
    poetry run yamllint --strict -c .yamllint.yaml .

# Measure run timing (DevEx telemetry)
time COMMAND:
    @echo "Timing: {{COMMAND}}"
    @time -p just {{COMMAND}}

# Run CI simulation locally
ci-local: install-dev lint typecheck test contracts
    @echo "Local CI simulation complete!"

# Show DevEx metrics
metrics:
    @echo "=== DevEx Metrics ==="
    @echo "Test count:"
    @poetry run pytest --collect-only -q | tail -1
    @echo ""
    @echo "Coverage:"
    @poetry run pytest --cov=firecrawl_demo --cov-report=term | grep "^TOTAL"
    @echo ""
    @echo "Code size:"
    @find firecrawl_demo -name "*.py" | xargs wc -l | tail -1
    @echo ""
    @echo "Test size:"
    @find tests -name "*.py" | xargs wc -l | tail -1
