#!/bin/bash
set -e
echo "========================================="
echo "  Running All Tests"
echo "========================================="
echo ""

# Unit tests
echo "--- Unit Tests ---"
python -m pytest tests/unit/ -v --tb=short 2>&1
UNIT_EXIT=$?

echo ""
echo "--- API/Integration Tests ---"
python -m pytest tests/api/ -v --tb=short 2>&1
API_EXIT=$?

echo ""
echo "========================================="
echo "  Test Summary"
echo "========================================="

# Run with coverage for summary
python -m pytest tests/ -v --tb=short --cov=src --cov-report=term-missing 2>&1 | tail -20
echo ""

if [ $UNIT_EXIT -ne 0 ] || [ $API_EXIT -ne 0 ]; then
    echo "RESULT: SOME TESTS FAILED"
    exit 1
else
    echo "RESULT: ALL TESTS PASSED"
    exit 0
fi
