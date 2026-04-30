import io
import json
from typing import List, Union
from uuid import UUID

from django.db.models import Model
from django.db.models.query import QuerySet
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.utils.serializer_helpers import ReturnList
from rest_framework_json_api.parsers import JSONParser

from apps.users.models import User
from helpers.json_parser import JSONRenderer
from helpers.permissions import PermissionManager


class BaseModelViewSet(viewsets.ModelViewSet):
    """Base view containing common logic packaged in a more friendly API"""

    model_class: Union[Model, None] = None
    permissions: Union[PermissionManager, None] = None
    ordering = "uuid"

    def perform_create(self, serializer) -> None:
        """Add the instance's creator when saving"""
        serializer.save(created_by=self.request.user)

    def get_permissioned_queryset(
        self, user: User, user_company: UUID, allowed_queryset: List[str]
    ) -> Union[QuerySet, None]:
        """
        Implements the conditional logic for each possibility in the
        allowed_queryset list.
        IMPORTANT: You should always return None if there are no matches.

        The arguments are present to allow old code to be adapted. If you don't
        need an argument in particular you can always rename it to _ and ignore it.

        Args:
            user (User): The User making the request
            user_company (UUID): UUID of the Company used in the request
            allowed_queryset (List[str]): List containing that User's allowed
            queryset types.

        Raises:
            NotImplementedError: Raised when the subclass doesn't implement the method

        Returns:
            Union[QuerySet, None]: Either returns the permissioned QuerySet or
            None

        Example:
            ```python
            def get_permissioned_queryset(self, user: User, user_company: UUID, allowed_queryset: List[str]) -> Union[QuerySet, None]:
                queryset = None

                if "none" in allowed_queryset:
                    queryset = join_queryset(
                        queryset, self.model_class.objects.none()
                    )
                if "all" in allowed_queryset:
                    queryset = join_queryset(
                        queryset,
                        self.model_class.objects.filter(
                            Q(firm__company_id=user_company)
                            | Q(company__uuid=user_company)
                        ),
                    )

                return queryset
            ```
        """

        raise NotImplementedError(
            "Please implement the get_permissioned_queryset method"
        )

    def get_general_queryset(self, user: User, user_companies: QuerySet) -> QuerySet:
        """
        Implements the more permissive general queryset when the User doesn't
        other means of defining the queryset (with get_permissioned_queryset).
        IMPORTANT: More permissive doen't mean "everything in the database", so
        always limit the querysets according to, at least, the user_companies.
        IMPORTANT: Always return a QuerySet.

        The arguments are present to allow old code to be adapted. If you don't
        need an argument in particular you can always rename it to _ and ignore it.

        Args:
            user (User): The User making the request
            user_companies (QuerySet[Company]): All Company instances that are
            related to the request User

        Raises:
            NotImplementedError: Raised when the subclass doesn't implement the method

        Returns:
            QuerySet: The general QuerySet.

        Example:
            ```python
            def get_general_queryset(self, user: User, user_companies: QuerySet[Company]) -> QuerySet:
                return self.model_class.objects.filter(
                    Q(firm__company__in=user_companies)
                    | Q(company__in=user_companies)
                )
            ```
        """

        raise NotImplementedError("Please implement the get_general_queryset method")

    def get_queryset(self):
        """Get list of items for the view according to the User's permissions"""

        if self.model_class is None:
            raise ValueError("Please set the model_class field")

        user: User = self.request.user
        queryset: Union[QuerySet, None] = None
        if self.action == "list":
            # Get the User's Company
            if "company" not in self.request.query_params:
                return self.model_class.objects.none()
            user_company = UUID(self.request.query_params["company"])

            # Determine permissions for that model_class
            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model=self.model_class.__name__,
                )
            allowed_queryset = self.permissions.get_allowed_queryset()

            queryset = self.get_permissioned_queryset(
                user, user_company, allowed_queryset
            )

            assert (
                isinstance(queryset, QuerySet) or queryset is None
            ), "get_permissioned_queryset return should either be a QuerySet or None"

        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = self.get_general_queryset(user, user_companies)

            assert isinstance(
                queryset, QuerySet
            ), "get_general_queryset return should be a QuerySet"

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())


class ModelSortViewSet(viewsets.ModelViewSet):
    def get_serializer_data(self, serializer):
        if self.sorting_fields and self.sort in self.sorting_fields:
            if self.sort_type == "DESC":
                data = sorted(serializer.data, key=lambda k: (k[self.sort],))
            else:
                data = sorted(
                    serializer.data, key=lambda k: (k[self.sort],), reverse=True
                )

            results = ReturnList(data, serializer=serializer)
        else:
            results = serializer.data

        return results

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Get sort fields from Class
        try:
            self.sorting_fields = self.sort_fields
        except Exception:
            self.sorting_fields = []

        # Get sort field from request
        self.sort = request.query_params.get("sort", None)
        self.sort_type = request.query_params.get("order", "ASC")

        # Return queryset paginated
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            results = self.get_serializer_data(serializer)
            return self.get_paginated_response(results)

        # Return queryset not paginated
        serializer = self.get_serializer(queryset, many=True)
        results = self.get_serializer_data(serializer)
        return Response(results)


def render_data(request):
    data = request.data
    rendered_data = json.loads(JSONRenderer().render(data).decode("utf-8"))
    return rendered_data


def format_item_payload(request):
    """Generate a formatted variable to insert in a serializer as data

    Args:
        request (Request): Incoming request with all data needed

    Returns:
        formatted_data (dict): Data needed to insert in a serializer correctly
    """

    parser_context = request.parser_context
    rendered_data = render_data(request)
    item_payload = rendered_data.get("item_payload")
    bytes_object = json.dumps(item_payload).encode("utf-8")
    stream = io.BytesIO(bytes_object)
    formatted_data = JSONParser().parse(stream, parser_context=parser_context)
    return formatted_data
