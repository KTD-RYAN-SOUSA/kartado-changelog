import uuid

from django.db.models import Q, TextField, Value
from django.db.models.functions import Concat
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters

from apps.service_orders.models import (
    AdministrativeInformation,
    Procedure,
    ServiceOrder,
)
from helpers.filters import DateFromToRangeCustomFilter, ListFilter, UUIDListFilter
from helpers.permissions import PermissionManager
from helpers.strings import keys_to_snake_case

from .models import (
    AccessRequest,
    Company,
    CompanyUsage,
    Entity,
    Firm,
    InspectorInFirm,
    SingleCompanyUsage,
    SubCompany,
    UserInCompany,
    UserInFirm,
    UserUsage,
)


def service_order_queryset(request):
    if "company" not in request.query_params:
        return ServiceOrder.objects.none()
    company = uuid.UUID(request.query_params["company"])
    return ServiceOrder.objects.filter(company=company)


class CompanyFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    active = filters.BooleanFilter(method="get_active")
    user_permission = UUIDListFilter(method="get_permissions")

    class Meta:
        model = Company
        fields = {"name": ["exact"]}

    def get_active(self, queryset, name, value):
        filter_user = {
            "userincompany__user": self.request.user,
            "userincompany__is_active": value,
        }

        return queryset.filter(**filter_user).distinct()

    def get_permissions(self, queryset, name, value):
        values = value.split(",")

        return queryset.filter(permission_companies__uuid__in=values).distinct()


class SubCompanyFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company = UUIDListFilter()
    responsible = UUIDListFilter()
    hired_by_subcompany = UUIDListFilter()
    contract_start_date = filters.DateFilter()
    contract_end_date = filters.DateFilter()
    subcompany_type = filters.ChoiceFilter(
        choices=[("HIRING", "HIRING"), ("HIRED", "HIRED")]
    )

    search = filters.CharFilter(label="search", method="get_search")
    active = filters.BooleanFilter()
    can_rdo_view = filters.BooleanFilter(method="filter_can_rdo_view")
    can_rdo_create = filters.BooleanFilter(method="filter_can_rdo_create")
    active = filters.BooleanFilter()

    class Meta:
        model = SubCompany
        fields = [
            "uuid",
            "subcompany_type",
            "company",
            "name",
            "cnpj",
            "responsible",
            "contract",
            "contract_start_date",
            "contract_end_date",
            "office",
            "construction_name",
            "hired_by_subcompany",
            "legacy_uuid",
        ]

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "name", Value(" "), "cnpj", Value(" "), output_field=TextField()
            )
        )

        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )

    def filter_can_rdo_view(self, queryset, name, value):
        if value is True:
            user_company = uuid.UUID(self.request.query_params.get("company"))
            permissions = PermissionManager(
                user=self.request.user,
                company_ids=user_company,
                model="SubCompany",
            )

            model_permissions_to_verify = "MultipleDailyReport"

            can_view_all_firms = permissions.get_specific_model_permision(
                model_permissions_to_verify, "can_view_all_firms"
            )

            if can_view_all_firms is True or can_view_all_firms is None:
                return queryset

            can_view = permissions.get_specific_model_permision(
                model_permissions_to_verify, "can_view"
            )

            if can_view_all_firms is False or can_view is True:
                # the user is a member of some firm
                return queryset.filter(
                    Q(subcompany_firms__users__uuid=self.request.user.uuid)
                    | Q(subcompany_firms__inspectors__uuid=self.request.user.uuid)
                    | Q(subcompany_firms__manager_id=self.request.user.uuid)
                )

            return queryset.none()

        else:
            return queryset

    def filter_can_rdo_create(self, queryset, name, value):
        if value is True:
            user_company = uuid.UUID(self.request.query_params.get("company"))
            permissions = PermissionManager(
                user=self.request.user,
                company_ids=user_company,
                model="Firm",
            )
            model_permissions_to_verify = "MultipleDailyReport"

            can_create_and_edit_all_firms = permissions.get_specific_model_permision(
                model_permissions_to_verify, "can_create_and_edit_all_firms"
            )

            if (
                can_create_and_edit_all_firms is True
                or can_create_and_edit_all_firms is None
            ):
                return queryset

            can_create = permissions.get_specific_model_permision(
                model_permissions_to_verify, "can_create"
            )

            if can_create_and_edit_all_firms is False or can_create is True:
                # the user is a member of some subcompany firm
                return queryset.filter(
                    Q(subcompany_firms__users__uuid=self.request.user.uuid)
                    | Q(subcompany_firms__inspectors__uuid=self.request.user.uuid)
                    | Q(subcompany_firms__manager_id=self.request.user.uuid)
                )

            return queryset.none()

        else:
            return queryset


class UserInCompanyFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    access_request = ListFilter(method="filter_access_request")
    user = UUIDListFilter()

    class Meta:
        model = UserInCompany
        fields = {"company": ["exact"], "is_active": ["exact"]}

    def filter_access_request(self, queryset, name, value):
        try:
            access_request = AccessRequest.objects.get(uuid=value)
        except Exception:
            return queryset.none()

        return queryset.filter(user=access_request.user, company=access_request.company)


class FirmFilter(filters.FilterSet):
    uuid = UUIDListFilter()

    service_order = filters.ModelChoiceFilter(
        label="service_order",
        queryset=service_order_queryset,
        method="filter_service_order",
    )
    is_company_team = filters.BooleanFilter()
    entity = UUIDListFilter()
    firm_contracts = UUIDListFilter()
    subcompany = UUIDListFilter()
    search = filters.CharFilter(label="search", method="get_search")
    firm_type = filters.ChoiceFilter(
        choices=[("INTERNAL", "INTERNAL"), ("EXTERNAL", "EXTERNAL")]
    )
    active = filters.BooleanFilter()
    manager = UUIDListFilter()
    inspectors = UUIDListFilter()
    users = UUIDListFilter()
    active = filters.BooleanFilter()
    can_rdo_view = filters.BooleanFilter(method="filter_can_rdo_view")
    can_rdo_create = filters.BooleanFilter(method="filter_can_rdo_create")

    is_judiciary = filters.BooleanFilter()

    class Meta:
        model = Firm
        fields = {"company": ["exact"], "manager": ["exact"], "legacy_uuid": ["exact"]}

    def filter_service_order(self, queryset, name, value):
        contract_firms = (
            AdministrativeInformation.objects.filter(service_order=value)
            .exclude(contract__isnull=True)
            .prefetch_related("contract__firm")
        )
        contract_firms_pk = []
        for item in contract_firms:
            if item.contract and item.contract.firm:
                contract_firms_pk.append(item.contract.firm.pk)
        all_firms = list(
            set(
                [
                    item.firm.pk
                    for item in Procedure.objects.filter(
                        action__service_order=value
                    ).select_related("firm")
                ]
                + contract_firms_pk
            )
        )
        return queryset.filter(pk__in=all_firms).distinct()

    def get_search(self, queryset, name, value):
        user_company = self.request.query_params.get("company")
        user_membership = get_object_or_404(
            self.request.user.companies_membership, company=user_company
        )

        permissions = keys_to_snake_case(user_membership.permissions.permissions)

        key = "inspector_in_firm"

        is_permissions_inspectors = key in permissions and permissions[key].get(
            "can_view", False
        )

        if is_permissions_inspectors:
            qs_annotate = queryset.annotate(
                search=Concat(
                    "name",
                    Value(" "),
                    "cnpj",
                    Value(" "),
                    "city__name",
                    Value(" "),
                    "street_address",
                    Value(" "),
                    "subcompany__name",
                    Value(" "),
                    "users__first_name",
                    Value(" "),
                    "users__last_name",
                    Value(" "),
                    "inspectors__first_name",
                    Value(" "),
                    "inspectors__last_name",
                    Value(" "),
                    "manager__first_name",
                    Value(" "),
                    "manager__last_name",
                    output_field=TextField(),
                )
            )
        else:
            qs_annotate = queryset.annotate(
                search=Concat(
                    "name",
                    Value(" "),
                    "cnpj",
                    Value(" "),
                    "city__name",
                    Value(" "),
                    "street_address",
                    Value(" "),
                    "subcompany__name",
                    Value(" "),
                    "users__first_name",
                    Value(" "),
                    "users__last_name",
                    Value(" "),
                    "manager__first_name",
                    Value(" "),
                    "manager__last_name",
                    output_field=TextField(),
                )
            )

        pk_found = set(
            qs_annotate.filter(search__unaccent__icontains=value).values_list(
                "pk", flat=True
            )
        )

        return queryset.filter(pk__in=pk_found)

    def filter_can_rdo_view(self, queryset, name, value):
        if value is True:
            user_company = uuid.UUID(self.request.query_params.get("company"))
            permissions = PermissionManager(
                user=self.request.user,
                company_ids=user_company,
                model="Firm",
            )

            model_permissions_to_verify = "MultipleDailyReport"

            can_view_all_firms = permissions.get_specific_model_permision(
                model_permissions_to_verify, "can_view_all_firms"
            )

            if can_view_all_firms is True or can_view_all_firms is None:
                return queryset

            can_view = permissions.get_specific_model_permision(
                model_permissions_to_verify, "can_view"
            )

            if can_view_all_firms is False or can_view is True:
                return queryset.filter(
                    Q(users__uuid=self.request.user.uuid)
                    | Q(inspectors__uuid=self.request.user.uuid)
                    | Q(manager_id=self.request.user.uuid)
                )

            return queryset.none()

        else:
            return queryset

    def filter_can_rdo_create(self, queryset, name, value):
        if value is True:
            user_company = uuid.UUID(self.request.query_params.get("company"))
            permissions = PermissionManager(
                user=self.request.user,
                company_ids=user_company,
                model="Firm",
            )
            model_permissions_to_verify = "MultipleDailyReport"

            can_create_and_edit_all_firms = permissions.get_specific_model_permision(
                model_permissions_to_verify, "can_create_and_edit_all_firms"
            )

            if (
                can_create_and_edit_all_firms is True
                or can_create_and_edit_all_firms is None
            ):
                return queryset

            can_create = permissions.get_specific_model_permision(
                model_permissions_to_verify, "can_create"
            )
            if can_create_and_edit_all_firms is False or can_create is True:
                return queryset.filter(
                    Q(users__uuid=self.request.user.uuid)
                    | Q(inspectors__uuid=self.request.user.uuid)
                    | Q(manager_id=self.request.user.uuid)
                )

            return queryset.none()

        else:
            return queryset


class UserInFirmFilter(filters.FilterSet):
    uuid = UUIDListFilter()

    class Meta:
        model = UserInFirm
        fields = {"firm": ["exact"], "user": ["exact"]}


class InspectorInFirmFilter(filters.FilterSet):
    uuid = UUIDListFilter()

    class Meta:
        model = InspectorInFirm
        fields = {"firm": ["exact"], "user": ["exact"]}


class AccessRequestFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    permissions = UUIDListFilter()
    approved = filters.BooleanFilter()
    done = filters.BooleanFilter()
    created_at = DateFromToRangeCustomFilter()
    expiration_date = DateFromToRangeCustomFilter()
    user__username = filters.CharFilter(lookup_expr="unaccent__icontains")
    user__full_name = filters.CharFilter(method="get_user_full_name")
    created_by__full_name = filters.CharFilter(method="get_created_by_full_name")
    company = UUIDListFilter(method="get_company")

    class Meta:
        model = AccessRequest
        fields = {"done": ["exact"]}

    def get_user_full_name(self, queryset, name, value):
        queryset = queryset.annotate(
            user_full_name=Concat(
                "user__first_name",
                Value(" "),
                "user__last_name",
                output_field=TextField(),
            )
        )
        return queryset.filter(user_full_name__unaccent__icontains=value).distinct()

    def get_created_by_full_name(self, queryset, name, value):
        queryset = queryset.annotate(
            created_by_full_name=Concat(
                "created_by__first_name",
                Value(" "),
                "created_by__last_name",
                output_field=TextField(),
            )
        )
        return queryset.filter(
            created_by_full_name__unaccent__icontains=value
        ).distinct()

    def get_company(self, queryset, name, value):
        values = value.split(",")
        return queryset.filter(
            Q(company__uuid__in=values) | Q(companies__uuid__in=values)
        ).distinct()


class EntityFilter(filters.FilterSet):
    uuid = UUIDListFilter()

    class Meta:
        model = Entity
        fields = {"company": ["exact"]}


class CompanyUsageFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    users = UUIDListFilter()

    date = DateFromToRangeCustomFilter()
    created_at = DateFromToRangeCustomFilter()
    updated_at = DateFromToRangeCustomFilter()

    search = filters.CharFilter(label="search", method="get_search")

    class Meta:
        model = CompanyUsage
        fields = [
            "uuid",
            "plan_name",
            "date",
            "cnpj",
            "created_at",
            "updated_at",
            "users",
            "search",
        ]

    def get_search(self, queryset, name, value):
        filtered_queryset = queryset.annotate(
            search=Concat("plan_name", Value(" "), "cnpj", output_field=TextField())
        ).filter(search__unaccent__icontains=value)

        return filtered_queryset.distinct()


class UserUsageFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    user = UUIDListFilter()
    company_usage = UUIDListFilter()

    usage_date = DateFromToRangeCustomFilter()
    created_at = DateFromToRangeCustomFilter()
    updated_at = DateFromToRangeCustomFilter()

    search = filters.CharFilter(label="search", method="get_search")

    class Meta:
        model = UserUsage
        fields = [
            "uuid",
            "is_counted",
            "created_at",
            "updated_at",
            "full_name",
            "email",
            "username",
            "usage_date",
            "search",
            "user",
            "company_usage",
        ]

    def get_search(self, queryset, name, value):
        filtered_queryset = queryset.annotate(
            search=Concat(
                "full_name",
                Value(" "),
                "email",
                Value(" "),
                "username",
                output_field=TextField(),
            )
        ).filter(search__unaccent__icontains=value)

        return filtered_queryset.distinct()


class SingleCompanyUsageFilter(filters.FilterSet):
    uuid = UUIDListFilter()
    company_usage = UUIDListFilter()

    created_at = DateFromToRangeCustomFilter()
    updated_at = DateFromToRangeCustomFilter()

    search = filters.CharFilter(label="search", method="get_search")

    class Meta:
        model = SingleCompanyUsage
        fields = [
            "uuid",
            "company_usage",
            "created_at",
            "updated_at",
            "search",
        ]

    def get_search(self, queryset, name, value):
        return queryset.filter(company__name__unaccent__icontains=value).distinct()
