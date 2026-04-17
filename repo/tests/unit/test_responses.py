"""Unit tests for src/utils/responses.py — response envelope builders."""

import json

import pytest

from src.app import create_app


@pytest.fixture(scope="module")
def app():
    app = create_app(testing=True)
    yield app


class TestSuccessResponse:
    def test_basic_envelope_structure(self, app):
        from src.utils.responses import success_response

        with app.test_request_context():
            response, status = success_response({"key": "value"})
            body = json.loads(response.data)

            assert status == 200
            assert "data" in body
            assert "meta" in body
            assert body["data"]["key"] == "value"
            assert "request_id" in body["meta"]
            assert "timestamp" in body["meta"]

    def test_custom_status_code(self, app):
        from src.utils.responses import success_response

        with app.test_request_context():
            response, status = success_response({"created": True}, status_code=201)
            assert status == 201

    def test_extra_meta_merged(self, app):
        from src.utils.responses import success_response

        with app.test_request_context():
            response, status = success_response(
                {"ok": True},
                meta={"custom_field": "abc"},
            )
            body = json.loads(response.data)
            assert body["meta"]["custom_field"] == "abc"
            assert "request_id" in body["meta"]

    def test_empty_data(self, app):
        from src.utils.responses import success_response

        with app.test_request_context():
            response, status = success_response({})
            body = json.loads(response.data)
            assert body["data"] == {}

    def test_none_data(self, app):
        from src.utils.responses import success_response

        with app.test_request_context():
            response, status = success_response(None)
            body = json.loads(response.data)
            assert body["data"] is None

    def test_list_data(self, app):
        from src.utils.responses import success_response

        with app.test_request_context():
            response, status = success_response([1, 2, 3])
            body = json.loads(response.data)
            assert body["data"] == [1, 2, 3]


class TestErrorResponse:
    def test_basic_error_envelope(self, app):
        from src.utils.responses import error_response

        with app.test_request_context():
            response, status = error_response("NOT_FOUND", "Resource not found", status_code=404)
            body = json.loads(response.data)

            assert status == 404
            assert "error" in body
            assert "meta" in body
            assert body["error"]["code"] == "NOT_FOUND"
            assert body["error"]["message"] == "Resource not found"
            assert "details" not in body["error"]

    def test_default_status_code_is_400(self, app):
        from src.utils.responses import error_response

        with app.test_request_context():
            _, status = error_response("VALIDATION_ERROR", "Bad input")
            assert status == 400

    def test_error_with_details(self, app):
        from src.utils.responses import error_response

        with app.test_request_context():
            details = [{"field": "email", "error": "required"}]
            response, status = error_response(
                "VALIDATION_ERROR", "Invalid input",
                details=details,
            )
            body = json.loads(response.data)
            assert body["error"]["details"] == details

    def test_error_with_string_details(self, app):
        from src.utils.responses import error_response

        with app.test_request_context():
            response, _ = error_response(
                "CONFLICT", "Already exists",
                details="Duplicate key",
            )
            body = json.loads(response.data)
            assert body["error"]["details"] == "Duplicate key"

    def test_error_with_none_details_omitted(self, app):
        from src.utils.responses import error_response

        with app.test_request_context():
            response, _ = error_response("ERR", "msg", details=None)
            body = json.loads(response.data)
            assert "details" not in body["error"]

    def test_error_meta_present(self, app):
        from src.utils.responses import error_response

        with app.test_request_context():
            response, _ = error_response("ERR", "msg")
            body = json.loads(response.data)
            assert "request_id" in body["meta"]
            assert "timestamp" in body["meta"]


class TestListResponse:
    def test_list_envelope_structure(self, app):
        from src.utils.responses import list_response

        pagination = {
            "page": 1,
            "per_page": 10,
            "total": 25,
            "total_pages": 3,
            "has_next": True,
            "has_prev": False,
        }

        with app.test_request_context():
            response, status = list_response(
                [{"id": "1"}, {"id": "2"}],
                pagination,
            )
            body = json.loads(response.data)

            assert status == 200
            assert "data" in body
            assert "meta" in body
            assert "pagination" in body
            assert len(body["data"]) == 2
            assert body["pagination"]["total"] == 25
            assert body["pagination"]["has_next"] is True

    def test_empty_list(self, app):
        from src.utils.responses import list_response

        pagination = {
            "page": 1, "per_page": 10, "total": 0,
            "total_pages": 1, "has_next": False, "has_prev": False,
        }

        with app.test_request_context():
            response, status = list_response([], pagination)
            body = json.loads(response.data)
            assert body["data"] == []
            assert body["pagination"]["total"] == 0

    def test_custom_status_code(self, app):
        from src.utils.responses import list_response

        with app.test_request_context():
            _, status = list_response([], {"page": 1}, status_code=206)
            assert status == 206
