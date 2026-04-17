#!/usr/bin/env bash
set -euo pipefail

echo "========================================="
echo "  Running All Tests"
echo "========================================="
echo ""

ROOT="$(cd "$(dirname "$0")" && pwd)"

compose_cmd() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        echo "docker compose"
        return 0
    fi

    if command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
        return 0
    fi

    return 1
}

COMPOSE="$(compose_cmd)" || {
    echo "Docker is required to run tests. Please install Docker."
    exit 1
}

run_pytest() {
    ${COMPOSE} run --rm --no-deps -v "${ROOT}:/app" api python -m pytest "$@"
}

# Unit tests
echo "--- Unit Tests ---"
UNIT_EXIT=0
run_pytest tests/unit/ -v --tb=short 2>&1 || UNIT_EXIT=$?

echo ""
echo "--- API/Integration Tests ---"
API_EXIT=0
run_pytest tests/api/ -v --tb=short 2>&1 || API_EXIT=$?

echo ""
echo "========================================="
echo "  Test Summary"
echo "========================================="

# Run with coverage for summary
run_pytest tests/ -v --tb=short --cov=src --cov-report=term-missing 2>&1 | tail -20
echo ""

if [ $UNIT_EXIT -ne 0 ] || [ $API_EXIT -ne 0 ]; then
    echo "RESULT: SOME TESTS FAILED"
    exit 1
else
    echo "RESULT: ALL TESTS PASSED"
    exit 0
fi
