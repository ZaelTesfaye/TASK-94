"""Unit tests for pagination utility."""

import math
from unittest.mock import MagicMock

import pytest

from src.utils.pagination import paginate_query


def _mock_query(total, items):
    """Create a mock SQLAlchemy query that supports count/offset/limit/all."""
    query = MagicMock()
    query.count.return_value = total
    offset_q = MagicMock()
    query.offset.return_value = offset_q
    limit_q = MagicMock()
    offset_q.limit.return_value = limit_q
    limit_q.all.return_value = items
    return query


class TestPaginateQuery:
    def test_standard_pagination(self):
        """Standard page/per_page returns correct metadata."""
        items = ["a", "b", "c"]
        query = _mock_query(total=10, items=items)

        result = paginate_query(query, page=1, per_page=3)

        assert result["items"] == items
        p = result["pagination"]
        assert p["page"] == 1
        assert p["per_page"] == 3
        assert p["total"] == 10
        assert p["total_pages"] == 4  # ceil(10/3)
        assert p["has_next"] is True
        assert p["has_prev"] is False
        query.offset.assert_called_once_with(0)

    def test_page_two(self):
        """Page 2 offsets correctly and has_prev is True."""
        query = _mock_query(total=10, items=["d", "e", "f"])

        result = paginate_query(query, page=2, per_page=3)

        p = result["pagination"]
        assert p["page"] == 2
        assert p["has_prev"] is True
        assert p["has_next"] is True
        query.offset.assert_called_once_with(3)

    def test_last_page(self):
        """Last page has has_next=False."""
        query = _mock_query(total=10, items=["j"])

        result = paginate_query(query, page=4, per_page=3)

        p = result["pagination"]
        assert p["page"] == 4
        assert p["has_next"] is False
        assert p["has_prev"] is True

    def test_page_zero_clamped_to_one(self):
        """Page 0 should be clamped to page 1."""
        query = _mock_query(total=5, items=["a"])

        result = paginate_query(query, page=0, per_page=5)

        assert result["pagination"]["page"] == 1
        query.offset.assert_called_once_with(0)

    def test_negative_page_clamped_to_one(self):
        """Negative page should be clamped to page 1."""
        query = _mock_query(total=5, items=["a"])

        result = paginate_query(query, page=-3, per_page=5)

        assert result["pagination"]["page"] == 1

    def test_very_large_page(self):
        """A very large page returns empty items but valid metadata."""
        query = _mock_query(total=5, items=[])

        result = paginate_query(query, page=9999, per_page=5)

        assert result["items"] == []
        p = result["pagination"]
        assert p["page"] == 9999
        assert p["total_pages"] == 1
        assert p["has_next"] is False

    def test_zero_total_items(self):
        """Zero total items should give total_pages=1, no next/prev."""
        query = _mock_query(total=0, items=[])

        result = paginate_query(query, page=1, per_page=10)

        p = result["pagination"]
        assert p["total"] == 0
        assert p["total_pages"] == 1
        assert p["has_next"] is False
        assert p["has_prev"] is False

    def test_per_page_clamped_to_max(self):
        """per_page above max_per_page gets clamped."""
        query = _mock_query(total=200, items=[])

        result = paginate_query(query, page=1, per_page=500, max_per_page=100)

        assert result["pagination"]["per_page"] == 100

    def test_per_page_none_defaults(self):
        """per_page=None defaults to 20."""
        query = _mock_query(total=50, items=[])

        result = paginate_query(query, page=1, per_page=None)

        assert result["pagination"]["per_page"] == 20

    def test_page_none_defaults(self):
        """page=None defaults to 1."""
        query = _mock_query(total=10, items=[])

        result = paginate_query(query, page=None, per_page=10)

        assert result["pagination"]["page"] == 1
