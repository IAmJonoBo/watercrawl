#!/usr/bin/env bash
# Test and verify dependency download configuration
# This script checks that all timeout and retry configurations are properly set

set -euo pipefail

echo "==================================================================="
echo "Dependency Download Configuration Test"
echo "==================================================================="
echo ""

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track test results
PASSED=0
FAILED=0

test_config() {
	local name="$1"
	local command="$2"
	local expected="$3"

	echo -n "Testing $name... "
	local result=0
	# Temporarily disable pipefail for this command
	set +o pipefail
	result=$(eval "$command" 2>/dev/null | grep -c "$expected" || true)
	set -o pipefail

	if [ "$result" -gt 0 ]; then
		echo -e "${GREEN}✓ PASS${NC}"
		PASSED=$((PASSED + 1))
	else
		echo -e "${RED}✗ FAIL${NC}"
		echo "  Expected to find: $expected"
		FAILED=$((FAILED + 1))
	fi
}

test_file() {
	local name="$1"
	local file="$2"

	echo -n "Testing $name exists... "
	if [ -f "$file" ]; then
		echo -e "${GREEN}✓ PASS${NC}"
		PASSED=$((PASSED + 1))
	else
		echo -e "${RED}✗ FAIL${NC}"
		echo "  File not found: $file"
		FAILED=$((FAILED + 1))
	fi
}

# Test pip configuration
echo "--- Pip Configuration ---"
test_file "pip config file" ".config/pip/pip.conf"
test_config "pip timeout" "cat .config/pip/pip.conf" "timeout = 60"
test_config "pip retries" "cat .config/pip/pip.conf" "retries = 5"
echo ""

# Test Poetry configuration
echo "--- Poetry Configuration ---"
test_file "poetry config file" "poetry.toml"
test_config "poetry max-workers" "cat poetry.toml" "max-workers = 10"
echo ""

# Test pnpm configuration
echo "--- pnpm Configuration ---"
test_file "pnpm config file" ".npmrc"
test_config "pnpm network-timeout" "cat .npmrc" "network-timeout=60000"
test_config "pnpm fetch-retries" "cat .npmrc" "fetch-retries=5"
echo ""

# Test GitHub Actions workflows
echo "--- GitHub Actions Workflows ---"
test_config "CI workflow pip timeout" "cat .github/workflows/ci.yml" "timeout 60"
test_config "CI workflow pip retries" "cat .github/workflows/ci.yml" "retries 5"
test_config "CI workflow PIP_TIMEOUT env" "cat .github/workflows/ci.yml" "PIP_TIMEOUT: 60"
test_config "CI workflow PNPM_NETWORK_TIMEOUT env" "cat .github/workflows/ci.yml" "PNPM_NETWORK_TIMEOUT: 60000"
echo ""

# Test Dockerfile
echo "--- Dockerfile ---"
test_config "Dockerfile pip timeout" "cat Dockerfile" "timeout 60"
test_config "Dockerfile pip retries" "cat Dockerfile" "retries 5"
test_config "Dockerfile PIP_TIMEOUT env" "cat Dockerfile" "PIP_TIMEOUT=60"
echo ""

# Test bundled binaries
echo "--- Bundled Binaries ---"
test_file "hadolint binary" "tools/bin/hadolint-linux-x86_64"
test_file "actionlint binary" "tools/bin/actionlint-linux-x86_64"
echo ""

# Summary
echo "==================================================================="
echo "Test Summary"
echo "==================================================================="
echo -e "Passed: ${GREEN}${PASSED}${NC}"
echo -e "Failed: ${RED}${FAILED}${NC}"
echo ""

if [ "$FAILED" -eq 0 ]; then
	echo -e "${GREEN}All dependency download configuration tests passed!${NC}"
	exit 0
else
	echo -e "${RED}Some tests failed. Please review the configuration.${NC}"
	exit 1
fi
