from typing import Optional


def paginate_params(page: Optional[int] = 1, page_size: Optional[int] = 20) -> dict:
    """Return offset and limit for SQL pagination."""
    page = max(1, page or 1)
    page_size = min(100, max(1, page_size or 20))
    return {
        "offset": (page - 1) * page_size,
        "limit": page_size,
        "page": page,
        "page_size": page_size,
    }
