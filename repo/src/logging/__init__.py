"""
Centralized Logger - Structured format with [stub][sub-stub] message pattern.
Mandatory interception: route requests, exceptions, promise rejections.
Automatic redaction of sensitive data.
"""

import logging
import re
import json
from datetime import datetime, timezone


SENSITIVE_PATTERNS = [
    (re.compile(r'"password"\s*:\s*"[^"]*"', re.IGNORECASE), '"password": "***REDACTED***"'),
    (re.compile(r'"token"\s*:\s*"[^"]*"', re.IGNORECASE), '"token": "***REDACTED***"'),
    (re.compile(r'"refresh_token"\s*:\s*"[^"]*"', re.IGNORECASE), '"refresh_token": "***REDACTED***"'),
    (re.compile(r'"access_token"\s*:\s*"[^"]*"', re.IGNORECASE), '"access_token": "***REDACTED***"'),
    (re.compile(r'"secret"\s*:\s*"[^"]*"', re.IGNORECASE), '"secret": "***REDACTED***"'),
    (re.compile(r'"ssn"\s*:\s*"[^"]*"', re.IGNORECASE), '"ssn": "***REDACTED***"'),
    (re.compile(r'"encryption_key"\s*:\s*"[^"]*"', re.IGNORECASE), '"encryption_key": "***REDACTED***"'),
    (re.compile(r'"authorization"\s*:\s*"[^"]*"', re.IGNORECASE), '"authorization": "***REDACTED***"'),
]


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts sensitive data from log output."""

    def format(self, record):
        msg = super().format(record)
        for pattern, replacement in SENSITIVE_PATTERNS:
            msg = pattern.sub(replacement, msg)
        return msg


class StructuredLogger:
    """Structured logger using [category][subcategory] message format."""

    def __init__(self, name: str = "app"):
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            formatter = RedactingFormatter(
                "%(asctime)s %(levelname)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z"
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)

    def _format_msg(self, category: str, subcategory: str, message: str, **kwargs) -> str:
        base = f"[{category}][{subcategory}] {message}"
        if kwargs:
            extras = " ".join(f"{k}={json.dumps(v) if isinstance(v, (dict, list)) else v}"
                              for k, v in kwargs.items())
            base = f"{base} | {extras}"
        return base

    def info(self, category: str, subcategory: str, message: str, **kwargs):
        self._logger.info(self._format_msg(category, subcategory, message, **kwargs))

    def warning(self, category: str, subcategory: str, message: str, **kwargs):
        self._logger.warning(self._format_msg(category, subcategory, message, **kwargs))

    def error(self, category: str, subcategory: str, message: str, **kwargs):
        self._logger.error(self._format_msg(category, subcategory, message, **kwargs))

    def debug(self, category: str, subcategory: str, message: str, **kwargs):
        self._logger.debug(self._format_msg(category, subcategory, message, **kwargs))

    def set_level(self, level: str):
        self._logger.setLevel(getattr(logging, level.upper(), logging.INFO))


logger = StructuredLogger("app")
