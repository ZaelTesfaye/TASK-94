"""
Response envelope helpers.

Every API endpoint should return responses through these helpers to ensure
a consistent JSON structure across the entire application.
"""

import uuid
from datetime import datetime, timezone

from flask import g, jsonify


def _meta() -> dict:
    """Build the common meta block."""
    return {
        "request_id": getattr(g, "request_id", str(uuid.uuid4())),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def success_response(data, status_code: int = 200, meta: dict | None = None):
    """Return a standard success envelope.

    Args:
        data: Payload to include under the ``data`` key.
        status_code: HTTP status code (default 200).
        meta: Optional extra meta fields merged into the meta block.

    Returns:
        Flask response tuple ``(json_body, status_code)``.
    """
    response_meta = _meta()
    if meta:
        response_meta.update(meta)

    body = {
        "data": data,
        "meta": response_meta,
    }
    return jsonify(body), status_code


def list_response(data, pagination: dict, status_code: int = 200):
    """Return a paginated list envelope.

    Args:
        data: List payload.
        pagination: Dict with page, per_page, total, total_pages, has_next, has_prev.
        status_code: HTTP status code (default 200).

    Returns:
        Flask response tuple ``(json_body, status_code)``.
    """
    body = {
        "data": data,
        "meta": _meta(),
        "pagination": pagination,
    }
    return jsonify(body), status_code


def error_response(code: str, message: str, details=None, status_code: int = 400):
    """Return a standard error envelope.

    Args:
        code: Machine-readable error code (e.g. ``VALIDATION_ERROR``).
        message: Human-readable error message.
        details: Optional additional error details (list, dict, or string).
        status_code: HTTP status code (default 400).

    Returns:
        Flask response tuple ``(json_body, status_code)``.
    """
    error_block: dict = {
        "code": code,
        "message": message,
    }
    if details is not None:
        error_block["details"] = details

    body = {
        "error": error_block,
        "meta": _meta(),
    }
    return jsonify(body), status_code
