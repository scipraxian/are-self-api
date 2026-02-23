"""Common Django Rest functions and mixins."""

from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

COUNT = 'count'
NEXT = 'next'
PAGE_COUNT = 'page_count'
PAGE_NUMBER = 'page_number'
PAGE_SIZE = 'page_size'
PARTIAL = 'partial'
PREVIOUS = 'previous'
RESULTS = 'results'


class DescriptivePagination(PageNumberPagination):
    """This adds key information to the response of Django Rest pagination."""

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    (COUNT, self.page.paginator.count),
                    (NEXT, self.get_next_link()),
                    (PAGE_COUNT, self.page.paginator.num_pages),
                    (PAGE_NUMBER, self.page.number),
                    (PAGE_SIZE, self.page_size),
                    (PREVIOUS, self.get_previous_link()),
                    (RESULTS, data),
                ]
            )
        )


class LargeResultsSetPagination(DescriptivePagination):
    """Allows very large resultants in a single call. Data=Small."""

    page_size = 1000
    page_size_query_param = PAGE_SIZE
    max_page_size = 10000


class MediumResultsSetPagination(DescriptivePagination):
    """Allows rather large results. Data=Medium/Small."""

    page_size = 100
    page_size_query_param = PAGE_SIZE
    max_page_size = 10000


class StandardResultsSetPagination(DescriptivePagination):
    """Default, small pages, with regulated page size."""

    page_size = 10
    page_size_query_param = PAGE_SIZE
    max_page_size = 1000
