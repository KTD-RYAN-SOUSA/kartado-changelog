from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.db.models import Count, Q, TextField, Value
from django.db.models.functions import Concat
from django_filters import rest_framework as filters
from django_filters.filters import CharFilter, ModelChoiceFilter
from django_filters.rest_framework.filters import BooleanFilter

from apps.companies.models import Company, Firm
from helpers.filters import DateFromToRangeCustomFilter, UUIDListFilter

from .models import User, UserNotification, UserSignature


class UserFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    only_company = ModelChoiceFilter(
        field_name="companies", queryset=Company.objects.all()
    )
    firm = ModelChoiceFilter(field_name="user_firms", queryset=Firm.objects.all())
    inspector_firm = ModelChoiceFilter(
        field_name="inspector_firms", queryset=Firm.objects.all()
    )
    subcompany = UUIDListFilter(field_name="user_firms__subcompany")
    exclude_firm = UUIDListFilter(field_name="user_firms", exclude=True)
    only_internal = BooleanFilter(label="only_internal", method="is_only_internal")
    search = CharFilter(label="search", method="get_search")
    is_supervisor = BooleanFilter()
    is_internal = BooleanFilter()
    is_active = BooleanFilter(method="filter_is_active")
    has_expiration_date = BooleanFilter(method="filter_has_expiration_date")
    manager_service_order = UUIDListFilter(method="get_managers")
    responsible_for_service_order = UUIDListFilter(method="get_responsibles")
    permission = UUIDListFilter(method="get_permission")
    expiration_date = DateFromToRangeCustomFilter(
        field_name="companies_membership__expiration_date",
        company_field="companies",
        is_date=True,
        is_null=True,
    )
    responsible_for_service_order_action = UUIDListFilter(
        method="get_responsibles_action"
    )
    can_be_service_responsible = BooleanFilter(
        label="can_be_service_responsible",
        method="has_can_be_responsible_permission",
    )
    can_be_service_manager = BooleanFilter(
        label="can_be_service_manager", method="has_can_be_manager_permission"
    )
    responsibles_hired_for_contract_survey = UUIDListFilter(
        method="get_responsibles_hirers"
    )
    active = BooleanFilter(method="filter_active")

    responsibles_hirer = UUIDListFilter(method="get_responsibles_hirer")
    responsibles_hired = UUIDListFilter(method="get_responsibles_hired")

    def filter_is_active(self, queryset, name, value):
        company = self.data.get("only_company")

        if not company:
            return queryset

        if value:
            return queryset.filter(
                companies_membership__is_active=True,
                companies_membership__company=company,
            ).distinct()

        return queryset.annotate(
            active_count=Count(
                "companies_membership",
                filter=Q(
                    companies_membership__is_active=True,
                    companies_membership__company=company,
                ),
                distinct=True,
            )
        ).filter(active_count=0)

    def filter_has_expiration_date(self, queryset, name, value):

        company = self.data.get("only_company")

        if value:
            return queryset.annotate(
                count_expiration=Count(
                    "companies_membership",
                    filter=Q(
                        companies_membership__expiration_date__isnull=False,
                    ),
                    distinct=True,
                )
            ).filter(count_expiration__gt=0)

        return queryset.filter(
            companies_membership__expiration_date__isnull=True,
            companies_membership__company=company,
        ).distinct()

    class Meta:
        model = User
        fields = {"uuid": ["exact"], "username": ["exact"], "legacy_uuid": ["exact"]}

    def get_responsibles_hirers(self, queryset, name, value):
        values = value.split(",")
        if values:
            return queryset.filter(
                user_firms__firm_contract_services__performance_service_contracts__in=values
            ).distinct()
        return queryset

    def get_managers(self, queryset, name, value):
        values = value.split(",")
        if values:
            return queryset.filter(managers_service_orders__in=values).distinct()
        return queryset

    def get_permission(self, queryset, name, value):
        values = value.split(",")

        try:
            company = self.request.query_params["company"]
        except Exception:
            company = ""

        if values and company:
            return queryset.filter(
                companies_membership__company=company,
                companies_membership__permissions__in=values,
            ).distinct()
        return queryset

    def get_responsibles(self, queryset, name, value):
        values = value.split(",")
        if values:
            return queryset.filter(responsibles_service_orders__in=values).distinct()
        return queryset

    def get_responsibles_action(self, queryset, name, value):
        values = value.split(",")
        if values:
            return queryset.filter(
                responsibles_service_orders__actions__in=values
            ).distinct()
        return queryset

    def is_only_internal(self, queryset, name, value):
        if value:
            firms = Firm.objects.filter(
                company_id=self.request.query_params["company"],
                is_company_team=True,
            ).values_list("uuid", flat=True)
            return queryset.filter(
                Q(user_firms__in=firms) | Q(user_firms_manager__in=firms)
            ).distinct()
        else:
            return queryset

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "username",
                Value(" "),
                "first_name",
                Value(" "),
                "last_name",
                Value(" "),
                "email",
                Value(" "),
                "cpf",
                Value(" "),
                KeyTextTransform("role", "metadata"),
                Value(" "),
                KeyTextTransform("occupation", "metadata"),
                Value(" "),
                KeyTextTransform("board_registration", "metadata"),
                output_field=TextField(),
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )

    def has_can_be_responsible_permission(self, queryset, name, value):
        return queryset.filter(
            Q(
                companies_membership__permissions__permissions__service_order__can_be_responsible=value
            )
            | Q(
                companies_membership__permissions__permissions__ServiceOrder__can_be_responsible=value
            )
        ).distinct()

    def has_can_be_manager_permission(self, queryset, name, value):
        return queryset.filter(
            Q(
                companies_membership__permissions__permissions__service_order__can_be_manager=value
            )
            | Q(
                companies_membership__permissions__permissions__ServiceOrder__can_be_manager=value
            )
        ).distinct()

    def filter_active(self, queryset, name, value):
        user_company = self.request.query_params.get("company")
        return queryset.filter(
            companies_membership__is_active=value,
            companies_membership__company_id=user_company,
        ).distinct()

    def get_responsibles_hirer(self, queryset, name, value):
        values = [str(x).strip() for x in value.split(",")]
        # TODO: try referente a modificação na staging onde company de subcompany
        # passa ser many to many remover remove exception assim que for implementando
        try:
            qs = queryset.filter(
                Q(hirer_contracts__firm__company__pk__in=values)
                | Q(hirer_contracts__subcompany__companies__pk__in=values)
            ).distinct()
        except Exception:
            qs = queryset.filter(
                Q(hirer_contracts__firm__company__pk__in=values)
                | Q(hirer_contracts__subcompany__company__pk__in=values)
            ).distinct()
        return qs

    def get_responsibles_hired(self, queryset, name, value):
        values = [str(x).strip() for x in value.split(",")]
        # TODO: try referente a modificação na staging onde company de subcompany
        # passa ser many to many remover remove exception assim que for implementando
        try:
            qs = queryset.filter(
                Q(hired_contracts__firm__company__pk__in=values)
                | Q(hired_contracts__subcompany__companies__pk__in=values)
            ).distinct()
        except Exception:
            qs = queryset.filter(
                Q(hired_contracts__firm__company__pk__in=values)
                | Q(hired_contracts__subcompany__company__pk__in=values)
            ).distinct()

        return qs


class UserNotificationFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    user = UUIDListFilter()
    companies = UUIDListFilter()

    class Meta:
        model = UserNotification
        fields = [
            "uuid",
            "user",
            "companies",
            "notification",
            "notification_type",
            "time_interval",
            "preferred_time",
        ]


class UserSignatureFilter(filters.FilterSet):

    uuid = UUIDListFilter()
    company = UUIDListFilter()
    user = UUIDListFilter()
    created_at = DateFromToRangeCustomFilter()

    class Meta:
        model = UserSignature
        fields = ["uuid", "company", "user", "created_at"]
