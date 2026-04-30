from datetime import datetime

from django.db.models import Exists, OuterRef, Prefetch, Q
from drf_extra_fields.fields import Base64ImageField
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import (
    ResourceRelatedField,
    SerializerMethodResourceRelatedField,
)
from simple_history.utils import bulk_create_with_history

from apps.approval_flows.models import ApprovalFlow
from apps.daily_reports.models import MultipleDailyReport
from apps.users.models import User
from helpers.apps.access_request import create_access_request
from helpers.apps.companies import is_energy_company
from helpers.apps.firms import verify_firm_deletion
from helpers.apps.users import create_panels
from helpers.mixins import EagerLoadingMixin
from helpers.serializers import get_field_if_provided_or_present
from helpers.strings import get_obj_from_path

from .models import (
    AccessRequest,
    Company,
    CompanyGroup,
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


class CompanySerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["owner"]
    _PREFETCH_RELATED_FIELDS = ["users", "key_users", "company_group"]

    uuid = serializers.UUIDField(required=False)
    logo = Base64ImageField(required=False)
    provider_logo = Base64ImageField(required=False)
    bounding_box = serializers.SerializerMethodField()
    is_energy = serializers.SerializerMethodField()
    company_group_name = serializers.SerializerMethodField()
    mobile_app = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            "uuid",
            "name",
            "cnpj",
            "logo",
            "provider_logo",
            "active",
            "owner",
            "users",
            "street_address",
            "custom_options",
            "metadata",
            "shape",
            "bounding_box",
            "company_group",
            "company_group_name",
            "key_users",
            "is_energy",
            "mobile_app",
        ]
        read_only_fields = ["users"]

    def get_bounding_box(self, obj):
        if obj.shape:
            return list(obj.shape.extent)
        return []

    def get_is_energy(self, obj):
        return is_energy_company(obj)

    def get_mobile_app(self, obj):
        if obj.mobile_app_override:
            return obj.mobile_app_override
        return obj.company_group.mobile_app if obj.company_group else "undefined"

    def get_company_group_name(self, obj):
        return obj.company_group.name if obj.company_group else ""

    def validate_cnpj(self, value):
        if value:
            return value.upper()
        return value


class SubCompanySerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["company", "responsible", "hired_by_subcompany"]

    uuid = serializers.UUIDField(required=False)
    logo = Base64ImageField(required=False)

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
            "logo",
            "hired_by_subcompany",
            "active",
            "legacy_uuid",
        ]

    def validate_cnpj(self, value):
        if value:
            return value.upper()
        return value

    def to_internal_value(self, attrs):
        # Allow empty string for contract_start_date and contract_end_date
        if attrs.get("contract_start_date", None) == "":
            attrs["contract_start_date"] = None
        if attrs.get("contract_end_date", None) == "":
            attrs["contract_end_date"] = None
        return super().to_internal_value(attrs)

    def validate(self, attrs):
        # Check if hired_by_subcompany field is available
        hired_by_subcompany = get_field_if_provided_or_present(
            "hired_by_subcompany", attrs, self.instance
        )
        subcompany_type = get_field_if_provided_or_present(
            "subcompany_type", attrs, self.instance
        )
        if subcompany_type == "HIRED" and hired_by_subcompany is None:
            raise serializers.ValidationError(
                "kartado.error.subcompany.hired_subcompanies_need_to_fill_hired_by_subcompany_field"
            )
        elif subcompany_type == "HIRING" and hired_by_subcompany:
            raise serializers.ValidationError(
                "kartado.error.subcompany.hiring_subcompanies_cant_fill_hired_by_subcompany_field"
            )

        # Check contract dates
        contract_start_date = get_field_if_provided_or_present(
            "contract_start_date", attrs, self.instance
        )
        contract_end_date = get_field_if_provided_or_present(
            "contract_end_date", attrs, self.instance
        )
        start_and_end_present = contract_start_date and contract_end_date

        if start_and_end_present and contract_start_date > contract_end_date:
            raise serializers.ValidationError(
                "kartado.error.subcompany.contract_end_date_should_be_after_contract_start_date"
            )

        return super().validate(attrs)

    def update(self, instance, validated_data):
        if instance.active is True and validated_data.get("active") is False:
            instance.subcompany_firms.update(active=False)

        return super(SubCompanySerializer, self).update(instance, validated_data)


class PermissionsSubCompanySerializer(SubCompanySerializer):
    _PREFETCH_RELATED_FIELDS = SubCompanySerializer._PREFETCH_RELATED_FIELDS

    can_rdo_create = serializers.SerializerMethodField()
    can_rdo_view = serializers.SerializerMethodField()

    class Meta(SubCompanySerializer.Meta):
        fields = SubCompanySerializer.Meta.fields + [
            "can_rdo_create",
            "can_rdo_view",
        ]

    def cache_subcompanies_firms_permissions(self):
        if not hasattr(self, "_firms_permission_cache"):
            company = self.context["request"].query_params["company"]
            user = self.context["request"].user

            self._firms_permission_cache = (
                SubCompany.objects.filter(company=company)
                .annotate(
                    has_permission=Exists(
                        Firm.objects.filter(subcompany=OuterRef("pk")).filter(
                            Q(manager_id=user.uuid)
                            | Q(users__uuid=user.uuid)
                            | Q(inspectors__uuid=user.uuid)
                        )
                    )
                )
                .values("pk", "has_permission")
            )

            self._firms_permission_cache = {
                str(item["pk"]): item["has_permission"]
                for item in self._firms_permission_cache
            }
        return self._firms_permission_cache

    def get_can_rdo_create(self, obj):
        can_create = self.context.get("can_create")

        if can_create is False:
            return False
        elif can_create == "verify_firm":
            subcompany_firms_check = self.cache_subcompanies_firms_permissions()
            return subcompany_firms_check.get(str(obj.uuid), False)
        return True

    def get_can_rdo_view(self, obj):
        can_view = self.context.get("can_view")
        if can_view is False:
            return False
        elif can_view == "verify_firm":
            subcompany_firms_check = self.cache_subcompanies_firms_permissions()
            return subcompany_firms_check.get(str(obj.uuid), False)
        return True


class UserInCompanySerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company", "user", "permissions"]
    _PREFETCH_RELATED_FIELDS = ["permissions__companies"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = UserInCompany
        fields = [
            "uuid",
            "user",
            "company",
            "expiration_date",
            "permissions",
            "level",
            "added_permissions",
            "is_active",
        ]


class ShareableUserInCompanySerializer(serializers.ModelSerializer):
    _PREFETCH_RELATED_FIELDS = [
        "company",
        "user",
        "permissions",
        "permissions__companies",
    ]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = UserInCompany
        fields = ["uuid", "user", "company", "expiration_date", "is_active"]


class FirmSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        Prefetch("users", queryset=User.objects.all().only("uuid")),
        Prefetch("inspectors", queryset=User.objects.all().only("uuid")),
        "company",
        "subcompany",
        "manager",
        "entity",
        "created_by",
    ]

    uuid = serializers.UUIDField(required=False)
    logo = Base64ImageField(required=False)
    custom_options = serializers.JSONField(required=False)
    metadata = serializers.JSONField(required=False)
    subcompany_name = serializers.SerializerMethodField()
    rdo_found_on_date = serializers.SerializerMethodField()

    class Meta:
        model = Firm
        fields = [
            "uuid",
            "name",
            "manager",
            "users",
            "inspectors",
            "company",
            "subcompany",
            "entity",
            "cnpj",
            "logo",
            "is_company_team",
            "active",
            "custom_options",
            "metadata",
            "street_address",
            "city",
            "members_amount",
            "can_use_ecm_integration",
            "created_by",
            "subcompany_name",
            "rdo_found_on_date",
            "is_judiciary",
            "delete_in_progress",
            "legacy_uuid",
        ]
        read_only_fields = ["created_by", "delete_in_progress"]

    def validate_cnpj(self, value):
        if value:
            return value.upper()
        return value

    def get_subcompany_name(self, obj):
        return obj.subcompany.name if obj.subcompany else ""

    def get_rdo_found_on_date(self, obj):
        # context["request"] is required since you can't access it through the serializer
        # returns the request obj with all its data.

        date_rdo = self.context["request"].query_params.get(
            "has_rdo_on_date", None  # string formated date. YYYY-MM-DD
        )

        if date_rdo:
            try:
                date = datetime.strptime(date_rdo, "%Y-%m-%d")
            except Exception:
                raise serializers.ValidationError(
                    "kartado.error.companies.invalid_date_format"
                )

            # Otimização: Usar prefetch ao invés de fazer uma nova query
            # O prefetch foi configurado no get_queryset da view
            if hasattr(obj, "prefetched_rdo_on_date"):
                if obj.prefetched_rdo_on_date:
                    # prefetched_rdo_on_date é uma lista (to_attr de Prefetch)
                    # mas deve conter no máximo 1 item devido ao unique_together
                    mdr = obj.prefetched_rdo_on_date[0]
                else:
                    mdr = None
            else:
                # Fallback: se o prefetch não foi aplicado, faz a query
                # (pode acontecer em casos edge ou quando não é uma list action)
                user = self.context["request"].user
                try:
                    mdr = MultipleDailyReport.objects.get(
                        date=date, created_by=user, firm=obj
                    )
                except MultipleDailyReport.DoesNotExist:
                    mdr = None

            return mdr.uuid if mdr else None
        return None

    def update(self, instance, validated_data):
        users_in_firm_list = []
        users_added_ids = []

        if (
            "delete" in self.initial_data
            and self.initial_data.get("delete", False) is True
        ):
            validated_data["delete_in_progress"] = True
            instance = super(FirmSerializer, self).update(instance, validated_data)
            verify_firm_deletion(
                str(instance.uuid), str(self.context["request"].user.uuid)
            )
            return instance

        if "add_users" in self.initial_data:
            for user_ids in self.initial_data["add_users"]:
                try:
                    # though this causes a query explosion, let's keep it as
                    # usually there's not gonna be many users being added
                    user = User.objects.exclude(user_firms__in=[instance]).get(
                        pk=user_ids["id"]
                    )
                except Exception:
                    raise serializers.ValidationError(
                        "Um ou mais usuários não existe ou já faz parte dessa equipe"
                    )
                users_added_ids.append(user_ids["id"])
                users_in_firm_list.append(UserInFirm(user=user, firm=instance))

        if (
            ("manager" in validated_data)
            and (str(validated_data["manager"].pk) not in users_added_ids)
            and (validated_data["manager"] not in instance.users.all())
        ):
            users_in_firm_list.append(
                UserInFirm(user=validated_data["manager"], firm=instance)
            )

        if users_in_firm_list:
            users_in_firm_list_with_id = bulk_create_with_history(
                users_in_firm_list, UserInFirm
            )
            create_panels([str(item.uuid) for item in users_in_firm_list_with_id])

        self.add_inspectors(instance)

        return super(FirmSerializer, self).update(instance, validated_data)

    def create(self, validated_data):
        users_in_firm_list = []
        users_added_ids = []

        instance = Firm.objects.create(**validated_data)

        if "add_users" in self.initial_data:
            for user_ids in self.initial_data["add_users"]:
                try:
                    # though this causes a query explosion, let's keep it as
                    # usually there's not gonna be many users being added
                    user = User.objects.exclude(user_firms__in=[instance]).get(
                        pk=user_ids["id"]
                    )
                except Exception:
                    raise serializers.ValidationError(
                        "Um ou mais usuários não existe ou já faz parte dessa equipe"
                    )
                users_added_ids.append(user_ids["id"])
                users_in_firm_list.append(UserInFirm(user=user, firm=instance))

        if ("manager" in validated_data) and (
            str(validated_data["manager"].pk) not in users_added_ids
        ):
            users_in_firm_list.append(
                UserInFirm(user=validated_data["manager"], firm=instance)
            )

        if users_in_firm_list:
            users_in_firm_list_with_id = bulk_create_with_history(
                users_in_firm_list, UserInFirm
            )
            create_panels([str(item.uuid) for item in users_in_firm_list_with_id])

        self.add_inspectors(instance)

        return instance

    def add_inspectors(self, instance):
        inspectors_in_firm_list = []

        if "add_inspectors" in self.initial_data:
            for user_ids in self.initial_data["add_inspectors"]:
                try:
                    # though this causes a query explosion, let's keep it as
                    # usually there's not gonna be many users being added
                    user = User.objects.exclude(inspector_firms__in=[instance]).get(
                        pk=user_ids["id"]
                    )
                except Exception:
                    raise serializers.ValidationError(
                        "kartado.error.firm.user_does_not_exist_or_is_already_an_inspector"
                    )
                inspectors_in_firm_list.append(
                    InspectorInFirm(user=user, firm=instance)
                )

        if inspectors_in_firm_list:
            bulk_create_with_history(inspectors_in_firm_list, InspectorInFirm)


class PermissionsFirmSerializer(FirmSerializer):
    _PREFETCH_RELATED_FIELDS = FirmSerializer._PREFETCH_RELATED_FIELDS + [
        "users",
        "inspectors",
    ]
    _SELECT_RELATED_FIELDS = ["manager"]

    can_rdo_create = serializers.SerializerMethodField()
    can_rdo_view = serializers.SerializerMethodField()

    class Meta(FirmSerializer.Meta):
        fields = FirmSerializer.Meta.fields + ["can_rdo_create", "can_rdo_view"]

    def get_can_rdo_create(self, obj):
        user = self.context["request"].user
        can_create = self.context.get("can_create")
        if can_create is False:
            return False
        elif can_create == "verify_firm":
            return bool(
                user.pk == obj.manager.pk
                or user in obj.users.all()
                or user in obj.inspectors.all()
            )
        else:
            return True

    def get_can_rdo_view(self, obj):
        user = self.context["request"].user
        can_view = self.context.get("can_view")
        if can_view is False:
            return False
        elif can_view == "verify_firm":
            return bool(
                user.pk == obj.manager.pk
                or user in obj.users.all()
                or user in obj.inspectors.all()
            )
        else:
            return True


class UserInFirmSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["firm", "user"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = UserInFirm
        fields = ["uuid", "firm", "user"]


class InspectorInFirmSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["firm", "user"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = InspectorInFirm
        fields = ["uuid", "firm", "user"]


class CompanyGroupSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["key_user"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = CompanyGroup
        fields = [
            "uuid",
            "name",
            "key_user",
            "saml_idp",
            "metadata",
            "mobile_app",
        ]


class AccessRequestSerializer(serializers.ModelSerializer, EagerLoadingMixin):

    _PREFETCH_RELATED_FIELDS = [
        "permissions",
        "user",
        "created_by",
        "company",
        "approval_step",
        "approval_step__approval_flow",
        "approval_step__responsible_users",
        "approval_step__responsible_firms__users",
        "user__supervisor",
        Prefetch("companies", queryset=Company.objects.all().only("uuid", "name")),
    ]

    uuid = serializers.UUIDField(required=False)

    approval_flow = SerializerMethodResourceRelatedField(
        model=ApprovalFlow, method_name="get_approval_flow", read_only=True
    )

    current_responsibles = SerializerMethodResourceRelatedField(
        model=User, method_name="get_current_responsibles", read_only=True, many=True
    )

    companies = ResourceRelatedField(queryset=Company.objects, many=True)

    approval_step_name = serializers.SerializerMethodField()

    class Meta:
        model = AccessRequest
        fields = [
            "uuid",
            "company",
            "companies",
            "user",
            "expiration_date",
            "created_at",
            "description",
            "approved",
            "permissions",
            "created_by",
            "approval_step",
            "approval_flow",
            "done",
            "current_responsibles",
            "approval_step_name",
        ]
        extra_kwargs = {"company": {"required": False}}

    def get_approval_flow(self, obj):
        if obj.approval_step:
            return obj.approval_step.approval_flow
        return None

    def get_current_responsibles(self, obj):
        responsibles = []
        if obj.approval_step:
            for user in obj.approval_step.responsible_users.all():
                responsibles.append(user)

            for firm in obj.approval_step.responsible_firms.all():
                if firm.manager:
                    responsibles.append(firm.manager)
                for user in firm.users.all():
                    responsibles.append(user)

            if obj.approval_step.responsible_supervisor:
                responsibles.append(obj.user.supervisor)

        return responsibles

    def get_approval_step_name(self, obj):
        if obj.approval_step:
            return obj.approval_step.name
        return ""

    def create(self, validated_data):
        if "companies" not in self.initial_data:
            raise serializers.ValidationError("É necessário enviar Companies.")

        companies_ids = [
            item["id"] for item in self.initial_data["companies"] if "id" in item
        ]

        is_clustered_access_request = get_obj_from_path(
            Company.objects.get(uuid=companies_ids[0]).metadata,
            "is_clustered_access_request",
            default_return=False,
        )
        companies = validated_data.pop("companies", [])
        if is_clustered_access_request:
            instance = create_access_request(
                validated_data, companies_ids[0], companies
            )
        else:
            for company_id in companies_ids:
                instance = create_access_request(validated_data, company_id, companies)

        return instance


class AccessRequestObjectSerializer(AccessRequestSerializer):
    history = serializers.SerializerMethodField()

    class Meta(AccessRequestSerializer.Meta):
        model = AccessRequest
        fields = AccessRequestSerializer.Meta.fields + ["history"]

    def get_history(self, obj):
        history_list = []
        for history in obj.history.all():
            history_dict = history.__dict__
            del history_dict["_state"]
            history_list.append(history_dict)
        return history_list


class EntitySerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["company", "approver_firm"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = Entity
        fields = ["uuid", "name", "company", "approver_firm", "address"]


class CompanyUsageSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        Prefetch("companies", queryset=Company.objects.all().only("uuid", "name")),
        "users",
    ]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = CompanyUsage
        fields = [
            "uuid",
            "plan_name",
            "date",
            "company_names",
            "cnpj",
            "user_count",
            "companies",
            "created_at",
            "updated_at",
            "users",
        ]
        read_only_fields = [
            "company_names",
            "cnpj",
            "user_count",
            "created_at",
            "updated_at",
        ]


class UserUsageSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["company_usage", "user"]

    uuid = serializers.UUIDField(required=False)

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
            "companies",
            "usage_date",
            "company_usage",
            "user",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
            "full_name",
            "email",
            "username",
            "companies",
            "usage_date",
        ]


class SingleCompanyUsageSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        Prefetch("company_usage", queryset=CompanyUsage.objects.all()),
        Prefetch("company", queryset=Company.objects.all().only("uuid", "name")),
    ]

    uuid = serializers.UUIDField(required=False)
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = SingleCompanyUsage
        fields = [
            "uuid",
            "company_usage",
            "company",
            "company_name",
            "user_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "company_name"]
