"""Unit tests for audit.py internal helper functions."""

import json

import pytest

from src.api.audit import _redact_state_json


class TestRedactStateJson:
    def test_redacts_decision_notes(self):
        raw = json.dumps({"action": "SUPPRESS", "decision_notes": "secret"})
        result = json.loads(_redact_state_json(raw))
        assert result["decision_notes"] == "[REDACTED]"
        assert result["action"] == "SUPPRESS"

    def test_redacts_appeal_notes(self):
        raw = json.dumps({"appeal_notes": "private appeal text"})
        result = json.loads(_redact_state_json(raw))
        assert result["appeal_notes"] == "[REDACTED]"

    def test_redacts_appeal_decision_notes(self):
        raw = json.dumps({"appeal_decision_notes": "denied because..."})
        result = json.loads(_redact_state_json(raw))
        assert result["appeal_decision_notes"] == "[REDACTED]"

    def test_redacts_multiple_sensitive_keys(self):
        raw = json.dumps({
            "decision_notes": "a",
            "appeal_notes": "b",
            "appeal_decision_notes": "c",
            "safe_field": "visible",
        })
        result = json.loads(_redact_state_json(raw))
        assert result["decision_notes"] == "[REDACTED]"
        assert result["appeal_notes"] == "[REDACTED]"
        assert result["appeal_decision_notes"] == "[REDACTED]"
        assert result["safe_field"] == "visible"

    def test_leaves_non_sensitive_keys_untouched(self):
        raw = json.dumps({"case_action": "SUPPRESS", "status": "CLOSED"})
        result = json.loads(_redact_state_json(raw))
        assert result["case_action"] == "SUPPRESS"
        assert result["status"] == "CLOSED"

    def test_returns_none_for_none_input(self):
        assert _redact_state_json(None) is None

    def test_returns_empty_string_for_empty_input(self):
        assert _redact_state_json("") == ""

    def test_returns_original_for_invalid_json(self):
        assert _redact_state_json("not json") == "not json"

    def test_returns_original_for_non_dict_json(self):
        raw = json.dumps([1, 2, 3])
        assert _redact_state_json(raw) == raw
