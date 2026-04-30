""" Helpers to write custom ModelViewSet endpoints """

from math import ceil

from django.conf import settings
from django.http import HttpRequest


def get_pagination_info(request: HttpRequest, item_count: int) -> dict:
    """
    Returns the pagination metadata since we don't get that for free when not using serializers
    """

    page_size = int(
        request.query_params.get("page_size") or settings.REST_FRAMEWORK["PAGE_SIZE"]
    )
    page_num = int(request.query_params.get("page") or 1)
    page_count = ceil(item_count / page_size) or 1

    return {
        "pagination": {
            "page": page_num,
            "pages": page_count,
            "count": item_count,
        }
    }
