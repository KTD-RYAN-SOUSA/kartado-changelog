import datetime
import uuid
from decimal import Decimal

from django.contrib.postgres.aggregates import StringAgg
from django.db.models import Q, TextField, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Concat
from django_filters import rest_framework as filters

from apps.resources.models import ContractService
from helpers.filters import DateFromToRangeCustomFilter, ListFilter, UUIDListFilter
from helpers.permissions import PermissionManager
from helpers.strings import STRING_UNIT_METRICS


class ContractServiceFilterBase(filters.FilterSet):
    class Meta:
        abstract = True

    def _get_manytomany_balance_from_or_to(
        self,
        queryset: ContractService,
        fields: list,
        attribute: str,
        value: float,
        form_or_to: str,
    ) -> list:
        """
        Args:
            queryset (ContractService): queryset from model ContractService
            fields (list): list manytomany relationship
            attribute (str): attribute in manytomany relationship
            value (float): value to be compared
            form_or_to (str): "from" to greater and "to" less than the set value
        Returns:
            list: Returns a list of fro the queryset
        """
        set_pk = set()
        for m2m in fields:
            for obj in queryset:
                _obj_m2m = getattr(obj, m2m)
                if _obj_m2m:
                    for obj_many in _obj_m2m.all():
                        _attr = getattr(obj_many, attribute, None)
                        if _attr:
                            if form_or_to == "from":
                                if _attr >= value:
                                    set_pk.add(str(obj.pk))
                            elif form_or_to == "to":
                                if _attr <= value:
                                    set_pk.add(obj.pk)

        return list(set_pk)

    def get_has_resources_for_approval(self, queryset, name, value):
        res_waiting_approval_query = (
            Q(
                contract_item_unit_prices__resource__serviceorderresource_procedures__isnull=False
            )
            | Q(
                contract_item_administration__resource__serviceorderresource_procedures__isnull=False
            )
            | Q(
                contract_item_administration__contract_item_administration_workers__isnull=False
            )
            | Q(
                contract_item_administration__contract_item_administration_equipment__isnull=False
            )
            | Q(
                contract_item_administration__contract_item_administration_vehicles__isnull=False
            )
        )

        if value:
            return queryset.filter(res_waiting_approval_query)
        else:
            return queryset.filter(~res_waiting_approval_query)

    def get_measurement_bulletin_filter(self, queryset, name, value):
        return queryset.filter(
            Q(
                contract_item_unit_prices__resource__serviceorderresource_procedures__measurement_bulletin__uuid=value
            )
            | Q(
                contract_item_administration__contract_item_administration_workers__measurement_bulletin__uuid=value
            )
            | Q(
                contract_item_administration__contract_item_administration_equipment__measurement_bulletin__uuid=value
            )
            | Q(
                contract_item_administration__contract_item_administration_vehicles__measurement_bulletin__uuid=value
            )
            | Q(
                contract_item_performance__resource__contract__contract_surveys__measurement_bulletin__uuid=value
            )
        ).distinct()

    def get_entity(self, queryset, name, value: str):
        uuid_value = [x.strip().lower() for x in value.split(",")]

        return queryset.filter(
            Q(contract_item_unit_prices__entity__in=uuid_value)
            | Q(contract_item_administration__entity__in=uuid_value)
            | Q(contract_item_performance__entity__in=uuid_value)
        ).distinct()

    def get_additional_control(self, queryset, name, value: str):
        list_value = [x.strip().lower() for x in value.split(",")]

        return queryset.filter(
            Q(
                contract_item_administration__resource__additional_control_model__in=list_value
            )
            | Q(
                contract_item_unit_prices__resource__additional_control_model__in=list_value
            )
            | Q(
                contract_item_performance__resource__additional_control_model__in=list_value
            )
        ).distinct()

    def get_unit(self, queryset, name, value: str):
        value = STRING_UNIT_METRICS.get(value.lower(), value)
        return queryset.filter(
            Q(contract_item_administration__resource__resource__unit__iexact=value)
            | Q(contract_item_unit_prices__resource__resource__unit__iexact=value)
            | Q(contract_item_performance__resource__resource__unit__iexact=value)
        ).distinct()

    def get_sort_string(self, queryset, name, value: str):
        return queryset.filter(
            Q(contract_item_administration__sort_string=value)
            | Q(contract_item_unit_prices__sort_string=value)
            | Q(contract_item_performance__sort_string=value)
        ).distinct()

    def get_content_type(self, queryset, name, value: str):
        list_value = [x.strip() for x in value.split(",")]
        return queryset.filter(
            Q(contract_item_administration__content_type__model__in=list_value)
        ).distinct()

    def get_balance_from(self, queryset, name, value: Decimal):
        list_pk = self._get_manytomany_balance_from_or_to(
            queryset,
            ["contract_item_unit_prices", "contract_item_administration"],
            "balance",
            value,
            "from",
        )

        return queryset.filter(pk__in=list_pk)

    def get_balance_to(self, queryset, name, value: Decimal):
        list_pk = self._get_manytomany_balance_from_or_to(
            queryset,
            ["contract_item_unit_prices", "contract_item_administration"],
            "balance",
            value,
            "to",
        )

        return queryset.filter(pk__in=list_pk)

    def get_creation_date_after(self, queryset, name, value: datetime.date):
        return queryset.filter(
            Q(
                contract_item_administration__resource__isnull=False,
                contract_item_administration__resource__creation_date__gte=value,
            )
            | Q(
                contract_item_unit_prices__resource__isnull=False,
                contract_item_unit_prices__resource__creation_date__gte=value,
            )
            | Q(
                contract_item_performance__resource__isnull=False,
                contract_item_performance__resource__creation_date__gte=value,
            )
        ).distinct()

    def get_creation_date_before(self, queryset, name, value: datetime.date):
        value += datetime.timedelta(days=1)
        return queryset.filter(
            Q(
                contract_item_administration__resource__isnull=False,
                contract_item_administration__resource__creation_date__lte=value,
            )
            | Q(
                contract_item_unit_prices__resource__isnull=False,
                contract_item_unit_prices__resource__creation_date__lte=value,
            )
            | Q(
                contract_item_performance__resource__isnull=False,
                contract_item_performance__resource__creation_date__lte=value,
            )
        ).distinct()


class ContractFilterBase(filters.FilterSet):
    class Meta:
        abstract = True

    def get_search(self, queryset, name, value):
        qs_annotate = queryset.annotate(
            search=Concat(
                "name",
                Value(" ", output_field=TextField()),
                "firm__name",
                Value(" ", output_field=TextField()),
                "unit_price_services__firms__name",
                Value(" ", output_field=TextField()),
                "administration_services__firms__name",
                Value(" ", output_field=TextField()),
                "performance_services__firms__name",
                Value(" ", output_field=TextField()),
                StringAgg("resources__resource__name", " "),
                Value(" ", output_field=TextField()),
                KeyTextTransform("r_c_number", "extra_info", output_field=TextField()),
                Value(" ", output_field=TextField()),
                KeyTextTransform(
                    "contract_object", "extra_info", output_field=TextField()
                ),
                Value(" ", output_field=TextField()),
                KeyTextTransform(
                    "accounting_classification", "extra_info", output_field=TextField()
                ),
                output_field=TextField(),
            )
        )
        return queryset.filter(
            pk__in=qs_annotate.filter(search__unaccent__icontains=value)
            .values_list("pk", flat=True)
            .distinct()
        )

    def get_company_filter(self, queryset, name, value: str):
        uuid_list = [x.strip() for x in value.split(",")]

        return queryset.filter(
            Q(firm__company__uuid__in=uuid_list)
            | Q(subcompany__company__uuid__in=uuid_list)
        )

    def get_is_internal(self, queryset, name, value):
        if value is True:
            return queryset.filter(
                Q(firm__is_company_team=True) | Q(subcompany__subcompany_type="HIRING")
            )
        elif value is False:
            return queryset.filter(
                Q(firm__is_company_team=False) | Q(subcompany__subcompany_type="HIRED")
            )
        else:
            return queryset

    def get_firm(self, queryset, name, value: str):
        firm_ids = [x.strip() for x in value.split(",")]
        return queryset.filter(
            Q(unit_price_services__firms__in=firm_ids)
            | Q(administration_services__firms__in=firm_ids)
            | Q(performance_services__firms__in=firm_ids)
        )

    def get_date(self, queryset, name, value):
        return queryset.filter(contract_start__lte=value, contract_end__gte=value)

    def get_contract_type(self, queryset, name, value: str):
        services = [x.strip().lower() for x in value.split(",")]

        services_filter = Q()
        if "administrationservices" in services:
            services_filter = services_filter | Q(administration_services__isnull=False)

        if "performanceservices" in services:
            services_filter = services_filter | Q(performance_services__isnull=False)

        if "unitpriceservices" in services:
            services_filter = services_filter | Q(unit_price_services__isnull=False)

        return queryset.filter(services_filter)

    def get_accounting_classification(self, queryset, name, value):
        return queryset.filter(
            extra_info__contains={"accounting_classification": value}
        )

    def get_unit_price_or_administration_service(self, queryset, name, value):
        if value is True:
            user_company = uuid.UUID(self.request.query_params.get("company"))
            permissions = PermissionManager(
                user=self.request.user,
                company_ids=user_company,
                model="ContractItemAdministration",
            )
            can_view_adm = permissions.has_permission(permission="can_view")
            can_view_unit = permissions.get_specific_model_permision(
                "ContractItemUnitPrice", "can_view"
            )

            if can_view_adm and can_view_unit:
                return queryset.filter(
                    Q(unit_price_services__isnull=False)
                    | Q(administration_services__isnull=False)
                ).distinct()
            elif can_view_adm and not can_view_unit:
                return queryset.filter(administration_services__isnull=False).distinct()
            elif can_view_unit and not can_view_adm:
                return queryset.filter(unit_price_services__isnull=False).distinct()
            else:
                return queryset.none()
        elif value is False:
            return queryset.filter(
                unit_price_services__isnull=True, administration_services__isnull=True
            ).distinct()
        return queryset


class ContractItemFilterBasic(filters.FilterSet):
    """
    Fields:
        uuid: UUIDListFilter
        entity: UUIDListFilter
        resource: UUIDListFilter
        contract: UUIDListFilter: filter_contract
        creation_date: DateFromToRangeCustomFilter
        created_at: DateFromToRangeCustomFilter
        sort_string : CharField
    """

    class Meta:
        abstract = True

    uuid = UUIDListFilter()
    entity = UUIDListFilter()
    resource = UUIDListFilter()
    contract = filters.UUIDFilter(method="filter_contract")
    creation_date = DateFromToRangeCustomFilter(field_name="resource__creation_date")
    created_at = DateFromToRangeCustomFilter()

    sort_string = filters.CharFilter()

    order = filters.NumberFilter()

    def filter_contract(self, queryset, name, value):
        return queryset.filter(resource__contract__uuid=value).distinct()


class ContractItemFilter(ContractItemFilterBasic):
    """

    Fields:
        uuid: UUIDListFilter
        entity: UUIDListFilter
        resource: UUIDListFilter
        contract: UUIDListFilter: filter_contract
        creation_date: DateFromToRangeCustomFilter
        created_at: DateFromToRangeCustomFilter
        sort_string : CharField
        additional_control: ListFilter: get additional_control
        unit: CharFilter: get unit
        balance_from: NumberFilter: get_balance_from
        balance_to: NumberFilter: get_balance_to
        contract_in_force: BooleanFilter
    """

    class Meta:
        abstract = True

    additional_control = ListFilter(method="get_additional_control")
    unit = filters.CharFilter(method="get_unit")
    contract_in_force = filters.BooleanFilter(method="filter_contract_in_force")
    balance_from = filters.NumberFilter(method="get_balance_from")
    balance_to = filters.NumberFilter(method="get_balance_to")

    def filter_contract_in_force(self, queryset, name, value):
        today = datetime.datetime.now()
        if value:
            return queryset.filter(
                resource__contract__contract_start__lte=today,
                resource__contract__contract_end__gte=today,
            ).distinct()
        else:
            return queryset.exclude(
                resource__contract__contract_start__lte=today,
                resource__contract__contract_end__gte=today,
            ).distinct()

    def get_additional_control(self, queryset, name, value: str):
        list_value = [x.strip() for x in value.split(",")]
        return queryset.filter(Q(resource__additional_control_model__in=list_value))

    def get_unit(self, queryset, name, value: str):
        value = STRING_UNIT_METRICS.get(value.lower(), value)
        return queryset.filter(resource__resource__unit__iexact=value)

    def get_balance_from(self, queryset, name, value: float):
        return queryset.filter(balance__gte=float(value))

    def get_balance_to(self, queryset, name, value: float):
        return queryset.filter(balance__lte=float(value))
