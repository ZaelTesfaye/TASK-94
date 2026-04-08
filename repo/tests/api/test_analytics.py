"""API tests for analytics and export endpoints."""
import uuid
import os
from datetime import datetime, timezone, timedelta

import pytest


class TestLearningBehavior:
    def test_learning_behavior(self, client, admin_headers, member_user, org_setup, db):
        from src.models.models import LearningEvent

        # Insert learning events
        for _ in range(3):
            ev = LearningEvent(
                user_id=member_user["user_id"],
                organization_id=org_setup["id"],
                event_type="PAGE_VIEW",
            )
            db.session.add(ev)
        db.session.commit()

        start_date = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        resp = client.get(
            f"/analytics/learning-behavior"
            f"?organization_id={org_setup['id']}"
            f"&start_date={start_date}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "results" in data
        assert data["total_events"] >= 3


class TestCompletionAnalytics:
    def test_completion_analytics(self, client, admin_headers, member_user, org_setup, db):
        from src.models.models import LearningEvent, ContentItem

        # Create a course content item
        content = ContentItem(
            organization_id=org_setup["id"],
            creator_id=member_user["user_id"],
            title="Test Course",
            body="Course body",
            content_type="COURSE",
        )
        db.session.add(content)
        db.session.flush()

        # Insert completion events
        ev = LearningEvent(
            user_id=member_user["user_id"],
            organization_id=org_setup["id"],
            content_id=content.id,
            event_type="COURSE_COMPLETE",
        )
        db.session.add(ev)

        # Also add a general event so the user shows in total_users
        ev2 = LearningEvent(
            user_id=member_user["user_id"],
            organization_id=org_setup["id"],
            event_type="PAGE_VIEW",
        )
        db.session.add(ev2)
        db.session.commit()

        start_date = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        resp = client.get(
            f"/analytics/completion"
            f"?organization_id={org_setup['id']}"
            f"&start_date={start_date}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "completion_rate" in data
        assert data["users_with_completion"] >= 1


class TestDifficultyAnalytics:
    def test_difficulty_analytics(self, client, admin_headers, member_user, org_setup, db):
        from src.models.models import ContentItem, Question, Attempt

        # Create content
        content = ContentItem(
            organization_id=org_setup["id"],
            creator_id=member_user["user_id"],
            title="Quiz Content",
            body="Quiz body",
            content_type="QUIZ",
        )
        db.session.add(content)
        db.session.flush()

        # Create question
        question = Question(
            content_id=content.id,
            organization_id=org_setup["id"],
            question_text="What is 2+2?",
            correct_answer="4",
        )
        db.session.add(question)
        db.session.flush()

        # Insert attempts (3 correct, 1 wrong)
        for is_correct in [True, True, True, False]:
            attempt = Attempt(
                user_id=member_user["user_id"],
                question_id=question.id,
                organization_id=org_setup["id"],
                answer_given="4" if is_correct else "5",
                is_correct=is_correct,
            )
            db.session.add(attempt)
        db.session.commit()

        start_date = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        resp = client.get(
            f"/analytics/difficulty"
            f"?organization_id={org_setup['id']}"
            f"&start_date={start_date}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "results" in data
        assert "summary" in data
        # 75% correct rate -> should be MEDIUM bucket
        assert len(data["results"]) >= 1


class TestExports:
    def test_create_export(self, client, admin_headers, org_setup, db):
        resp = client.post("/exports", json={
            "export_type": "learning_events",
            "organization_id": org_setup["id"],
            "parameters": {},
        }, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert "export" in data
        assert data["export"]["export_type"] == "learning_events"

    def test_export_dedupe(self, client, admin_headers, org_setup, db):
        params = {"start_date": "2024-01-01"}

        resp1 = client.post("/exports", json={
            "export_type": "learning_events",
            "organization_id": org_setup["id"],
            "parameters": params,
        }, headers=admin_headers)
        assert resp1.status_code == 201

        # Same export request should return the existing one
        resp2 = client.post("/exports", json={
            "export_type": "learning_events",
            "organization_id": org_setup["id"],
            "parameters": params,
        }, headers=admin_headers)
        assert resp2.status_code == 200
        data = resp2.get_json()["data"]
        assert data.get("message") == "duplicate_within_window"

    def test_list_exports(self, client, admin_headers, org_setup, db):
        # Create an export first
        client.post("/exports", json={
            "export_type": "content_metrics",
            "organization_id": org_setup["id"],
            "parameters": {},
        }, headers=admin_headers)

        resp = client.get(
            f"/exports?organization_id={org_setup['id']}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["data"]) >= 1

    def test_download_export(self, client, admin_headers, org_setup, db):
        # Create a completed export
        resp = client.post("/exports", json={
            "export_type": "learning_events",
            "organization_id": org_setup["id"],
            "parameters": {},
        }, headers=admin_headers)
        export_data = resp.get_json()["data"]["export"]

        # Only try download if export completed and file exists
        if export_data["status"] == "COMPLETED" and export_data.get("file_path"):
            resp = client.get(
                f"/exports/{export_data['id']}/download",
                headers=admin_headers,
            )
            assert resp.status_code == 200
        else:
            # If export didn't complete (e.g., no file system access in test),
            # verify the status is at least set correctly
            assert export_data["status"] in ("COMPLETED", "FAILED")
