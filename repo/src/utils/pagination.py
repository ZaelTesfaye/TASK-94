"""
Pagination helper for SQLAlchemy queries.
"""

import math


def paginate_query(query, page: int, per_page: int, max_per_page: int = 100) -> dict:
    """Paginate a SQLAlchemy query and return items with pagination metadata.

    Args:
        query: SQLAlchemy query object.
        page: Requested page number (clamped to >= 1).
        per_page: Requested items per page (clamped between 1 and *max_per_page*).
        max_per_page: Upper bound for per_page (default 100).

    Returns:
        Dict with ``items`` (list) and ``pagination`` (dict) keys.
    """
    # Clamp inputs
    page = max(1, int(page) if page is not None else 1)
    per_page = max(1, min(int(per_page) if per_page is not None else 20, max_per_page))

    total = query.count()
    total_pages = max(1, math.ceil(total / per_page))

    items = query.offset((page - 1) * per_page).limit(per_page).all()

    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }

    return {
        "items": items,
        "pagination": pagination,
    }
