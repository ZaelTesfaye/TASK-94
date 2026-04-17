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


class TestWrongAnswers:
    def test_wrong_answers(self, client, admin_headers, member_user, org_setup, db):
        from src.models.models import ContentItem, Question, Attempt

        content = ContentItem(
            organization_id=org_setup["id"],
            creator_id=member_user["user_id"],
            title="WA Quiz",
            body="body",
            content_type="QUIZ",
        )
        db.session.add(content)
        db.session.flush()

        question = Question(
            content_id=content.id,
            organization_id=org_setup["id"],
            question_text="What is 1+1?",
            correct_answer="2",
        )
        db.session.add(question)
        db.session.flush()

        # 2 wrong, 1 correct
        for is_correct in [False, False, True]:
            attempt = Attempt(
                user_id=member_user["user_id"],
                question_id=question.id,
                organization_id=org_setup["id"],
                answer_given="2" if is_correct else "3",
                is_correct=is_correct,
            )
            db.session.add(attempt)
        db.session.commit()

        start_date = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        resp = client.get(
            f"/analytics/wrong-answers"
            f"?organization_id={org_setup['id']}"
            f"&start_date={start_date}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "results" in data
        assert len(data["results"]) >= 1
        row = data["results"][0]
        assert "question_id" in row
        assert "question_text" in row
        assert "wrong_count" in row
        assert "total_attempts" in row
        assert "correct_rate" in row
        assert row["wrong_count"] == 2


class TestCourseEffectiveness:
    def test_course_effectiveness(self, client, admin_headers, member_user, org_setup, db):
        from src.models.models import LearningEvent, ContentItem

        course = ContentItem(
            organization_id=org_setup["id"],
            creator_id=member_user["user_id"],
            title="Effectiveness Course",
            body="body",
            content_type="COURSE",
        )
        db.session.add(course)
        db.session.flush()

        for etype in ["PAGE_VIEW", "PAGE_VIEW", "COURSE_COMPLETE"]:
            ev = LearningEvent(
                user_id=member_user["user_id"],
                organization_id=org_setup["id"],
                content_id=course.id,
                event_type=etype,
            )
            db.session.add(ev)
        db.session.commit()

        start_date = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        resp = client.get(
            f"/analytics/course-effectiveness"
            f"?organization_id={org_setup['id']}"
            f"&start_date={start_date}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "results" in data
        assert len(data["results"]) >= 1
        item = data["results"][0]
        assert "content_id" in item
        assert "title" in item
        assert "total_events" in item
        assert "completions" in item
        assert "engagement_score" in item
        assert item["total_events"] >= 3
        assert item["completions"] >= 1

    def test_course_effectiveness_unauthenticated(self, client, db):
        resp = client.get("/analytics/course-effectiveness?start_date=2024-01-01")
        assert resp.status_code == 401


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
        export_id = export_data["id"]

        # Ensure the export completed and has a file path before downloading
        assert export_data["status"] == "COMPLETED", (
            f"Export should be COMPLETED but was {export_data['status']}"
        )
        assert export_data.get("file_path"), "Export must have a file_path set"

        resp = client.get(
            f"/exports/{export_id}/download",
            headers=admin_headers,
        )
        assert resp.status_code in (200, 202)
        assert len(resp.data) > 0
        assert "text/csv" in resp.content_type
