from datetime import timedelta

import sentry_sdk
from django.contrib.auth.base_user import BaseUserManager
from django.db.models import Prefetch
from django.utils import timezone
from drf_extra_fields.fields import Base64ImageField
from rest_framework.serializers import BooleanField, UUIDField
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import SerializerMethodResourceRelatedField

from apps.companies.models import Company, Firm, UserInCompany
from apps.monitorings.models import OperationalControl
from apps.permissions.models import UserPermission
from apps.reportings.helpers.default_menus import create_user_menu
from helpers.apps.access_request import create_access_request
from helpers.apps.users import (
    get_notification_accepts,
    get_possible_notifications,
    time_interval_to_label,
)
from helpers.fields import (
    EmptyFileField,
    ResourceRelatedFieldWithName,
    SerializerMethodResourceRelatedFieldWithName,
)
from helpers.files import get_rdo_file_url
from helpers.mixins import EagerLoadingMixin
from helpers.serializers import LabeledChoiceField, get_field_if_provided_or_present
from helpers.strings import keys_to_snake_case

from .const.time_intervals import NOTIFICATION_INTERVALS
from .models import User, UserNotification, UserSignature


class ActiveUserField(BooleanField):
    def to_representation(self, value):
        user_company = self.parent.context.get("user_company")
        if user_company is None:
            return False
        elif hasattr(value, "active"):
            return value.active
        else:
            try:
                is_active = (
                    value.companies_membership.filter(company_id=user_company)
                    .first()
                    .is_active
                )
            except Exception:
                is_active = False
            return is_active

    def to_internal_value(self, data):
        if not isinstance(data, bool):
            raise serializers.ValidationError("active field must be a boolean")
        return {"active": data}


class UserSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "company_group",
        Prefetch("supervisor", queryset=User.objects.all().only("uuid")),
        Prefetch("responsible", queryset=User.objects.all().only("uuid")),
        Prefetch(
            "user_firms_manager",
            queryset=Firm.objects.all().only("uuid", "manager_id"),
        ),
        Prefetch("user_firms", queryset=Firm.objects.all().only("uuid")),
        "user_firms__operational_cycles_creators",
        "user_firms__operational_cycles_creators__operational_control",
        "user_firms__operational_cycle_viewers",
        "user_firms__operational_cycle_viewers__operational_control",
        "companies_membership",
        Prefetch(
            "companies_membership__company",
            queryset=Company.objects.all().only("uuid", "name"),
        ),
        Prefetch(
            "companies_membership__permissions",
            queryset=UserPermission.objects.all().only("uuid"),
        ),
    ]

    uuid = serializers.UUIDField(required=False)
    avatar = Base64ImageField(required=False)
    metadata = serializers.JSONField(required=False)
    memberships = serializers.JSONField(write_only=True, required=False)
    confirm_password = serializers.CharField(write_only=True, required=False)
    full_name = serializers.CharField(source="get_full_name", required=False)
    permission = SerializerMethodResourceRelatedField(
        model=UserPermission, method_name="get_permission", read_only=True
    )
    user_in_company = SerializerMethodResourceRelatedField(
        model=UserInCompany, method_name="get_user_in_company", read_only=True
    )
    companies = SerializerMethodResourceRelatedField(
        model=Company, method_name="get_companies", read_only=True, many=True
    )
    expiration_date = serializers.SerializerMethodField()
    operational_creators = SerializerMethodResourceRelatedField(
        model=OperationalControl,
        method_name="get_operational_creators",
        read_only=True,
        many=True,
    )
    operational_viewers = SerializerMethodResourceRelatedField(
        model=OperationalControl,
        method_name="get_operational_viewers",
        read_only=True,
        many=True,
    )

    active = ActiveUserField(source="*", required=False)
    active_company = UUIDField(write_only=True, required=False, format="hex_verbose")

    RESTRICTED_FIELDS = [
        "first_name",
        "last_name",
        "birth_date",
        "cpf",
        "email",
        "phone",
        "responsible",
        "supervisor",
        "firm_name",
        "saml_nameid",
        "metadata",
    ]

    SENSITIVE_READ_FIELDS = ["cpf", "birth_date", "phone"]

    class Meta:
        model = User
        fields = [
            "uuid",
            "username",
            "first_name",
            "last_name",
            "email",
            "avatar",
            "password",
            "confirm_password",
            "metadata",
            "configuration",
            "memberships",
            "companies",
            "date_joined",
            "user_firms_manager",
            "user_firms",
            "company_group",
            "full_name",
            "permission",
            "user_in_company",
            "saml_nameid",
            "supervisor",
            "is_supervisor",
            "is_internal",
            "birth_date",
            "responsible",
            "firm_name",
            "phone",
            "cpf",
            "has_accepted_tos",
            "expiration_date",
            "operational_creators",
            "operational_viewers",
            "active_company",
            "active",
            "legacy_uuid",
        ]
        read_only_fields = [
            "date_joined",
            "is_active",
            "user_firms_manager",
            "user_firms",
            "companies",
            "has_accepted_tos",
            "operational_creators",
            "operational_viewers",
        ]
        extra_kwargs = {
            "password": {"write_only": True, "required": False},
            "confirm_password": {"write_only": True, "required": False},
            "active": {"required": False},
        }

    def get_operational_creators(self, obj):
        # returns a list of operational_controls that the user
        # is in a creator firm in a active cycle
        now = timezone.now().date()
        operational_controls = [
            cycle.operational_control
            for firm in obj.user_firms.all()
            for cycle in firm.operational_cycles_creators.all()
            if cycle.start_date.date() <= now and cycle.end_date.date() >= now
        ]
        return list(set(operational_controls))

    def get_operational_viewers(self, obj):
        # returns a list of operational_controls that the user
        # is in a viewer firm in a active cycle
        now = timezone.now().date()
        operational_controls = [
            cycle.operational_control
            for firm in obj.user_firms.all()
            for cycle in firm.operational_cycle_viewers.all()
            if cycle.start_date.date() <= now and cycle.end_date.date() >= now
        ]
        return list(set(operational_controls))

    def get_companies(self, obj):
        companies = [
            user_in_company.company
            for user_in_company in obj.companies_membership.all()
        ]
        return list(set(companies))

    def get_permission(self, obj):
        try:
            company = self.context["request"].query_params["company"]
            user_in_company = next(
                a
                for a in obj.companies_membership.all()
                if str(a.company.uuid) == company
            )
            return user_in_company.permissions
        except Exception:
            return None

    def get_user_in_company(self, obj):
        try:
            company = self.context["request"].query_params["company"]
            user_in_company = next(
                a
                for a in obj.companies_membership.all()
                if str(a.company.uuid) == company
            )
            return user_in_company
        except Exception:
            return None

    def get_expiration_date(self, obj):
        try:

            company_uuid = self.context.get("user_company")
            user_in_company = next(
                a
                for a in obj.companies_membership.all()
                if str(a.company.uuid) == str(company_uuid)
            )
            return user_in_company.expiration_date
        except StopIteration:
            return None
        except Exception as e:
            sentry_sdk.capture_exception(e)
            return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if (
            request
            and instance.pk != request.user.pk
            and not self.can_view_sensitive_fields(request.user)
        ):
            for field_name in self.SENSITIVE_READ_FIELDS:
                data.pop(field_name, None)
                if field_name in self.fields:
                    self.fields[field_name].read_only = True
        return data

    def can_view_sensitive_fields(self, user):
        company_uuid = self.context.get("user_company")
        if not company_uuid:
            return False
        user_in_company = user.companies_membership.filter(
            company_id=company_uuid
        ).first()
        if not user_in_company or not user_in_company.permissions:
            return False
        perms = keys_to_snake_case(user_in_company.permissions.permissions)
        return perms.get("user", {}).get("can_edit_all_fields", False)

    def validate(self, data):
        if "responsible" in data and data["responsible"]:
            if not data["responsible"].is_internal:
                raise serializers.ValidationError(
                    "O responsável deve ser um usuário interno."
                )
            if not data["is_internal"]:
                data["supervisor"] = data["responsible"].supervisor
        if "supervisor" in data and data["supervisor"]:
            if not data["supervisor"].is_supervisor:
                raise serializers.ValidationError(
                    "O supervisor selecionado não possui este nível de acesso."
                )

        if self.instance:
            edited = False
            for field in self.RESTRICTED_FIELDS:
                if field in data:
                    # Compara se o valor realmente mudou
                    instance_value = getattr(self.instance, field, None)
                    if instance_value != data[field]:
                        edited = True
                        break
            if edited:
                self.check_can_edit_all_fields()

        return data

    def check_can_edit_all_fields(self):
        """Verifica se o usuário possui permissão canEditAllFields para editar campos restritos"""
        request = self.context.get("request")
        if not request or not request.user:
            raise serializers.ValidationError("Usuário não autenticado.")

        user = request.user
        company_uuid = self.context.get("user_company")

        if not company_uuid:
            raise serializers.ValidationError("Contexto de empresa não fornecido.")

        try:
            user_in_company = user.companies_membership.filter(
                company_id=company_uuid
            ).first()

            raw_permissions = user_in_company.permissions.permissions
            user_permissions = keys_to_snake_case(raw_permissions)

            user_model_permissions = user_permissions.get("user", {})
            can_edit = user_model_permissions.get("can_edit_all_fields", False)

            if not can_edit:
                raise serializers.ValidationError(
                    "Você não possui permissão para alterar estes campos restritos. "
                )

        except Exception as e:
            raise serializers.ValidationError(f"Erro ao verificar permissões: {str(e)}")

    def update_active_company(
        self,
        user_in_company: UserInCompany,
        active_company: Company,
        active: bool,
        user: User,
        req_user: User,
    ):
        user_in_company = UserInCompany.objects.filter(
            company=active_company, user=user
        ).first()
        # prevent the user from deactivating himself

        if active is False and user_in_company and user_in_company.user == req_user:

            raise serializers.ValidationError(
                "kartado.error.user.it_is_not_possible_to_deactivate_the_user_himself"
            )
        if user_in_company:
            if user_in_company.is_active is False and active is True:
                create_user_menu(user, active_company)
            if active is False:
                user_in_company.expiration_date = None
            user_in_company.is_active = active
            user_in_company.save()

    def update(self, instance, validated_data):
        # Autofill SAML idp
        if "company_group" in validated_data and "saml_nameid" in validated_data:
            validated_data["saml_idp"] = validated_data["company_group"].saml_idp
        # Fix empty string duplicated saml_nameid
        if "saml_nameid" in validated_data and validated_data["saml_nameid"] == "":
            validated_data["saml_nameid"] = None
        if (
            validated_data.get("active") is not None
            and validated_data.get("active_company") is not None
        ):
            active_company = Company.objects.get(pk=validated_data["active_company"])
            user_in_company = UserInCompany.objects.filter(
                company=active_company
            ).first()
            active = validated_data["active"]
            self.update_active_company(
                user=instance,
                user_in_company=user_in_company,
                active_company=active_company,
                active=active,
                req_user=self.context["request"].user,
            )

        # Fix empty string duplicated saml_nameid
        if "saml_nameid" in validated_data and validated_data["saml_nameid"] == "":
            validated_data["saml_nameid"] = None
        return super(UserSerializer, self).update(instance, validated_data)

    def create(self, validated_data):
        validated_data.pop("active", None)
        """
        Creates user and links it to company
        """
        # Avoid circular import
        from .notifications import send_email_password

        send_email = False
        fields = ["password", "confirm_password"]

        if set(fields).issubset(validated_data.keys()):
            if validated_data["confirm_password"] != validated_data["password"]:
                raise serializers.ValidationError(
                    "A Senha e Confirmar Senha não são iguais."
                )
            del validated_data["confirm_password"]
        elif (fields[0] in validated_data) or (fields[1] in validated_data):
            raise serializers.ValidationError(
                "É necessário enviar Senha e Confirmar Senha, ou somente um email."
            )
        else:
            if "email" not in validated_data:
                raise serializers.ValidationError("É necessário um email.")
            validated_data["password"] = BaseUserManager().make_random_password()
            if "saml_nameid" not in validated_data:
                send_email = True

        memberships = []

        if "memberships" not in validated_data:
            if "company_group" not in validated_data:
                try:
                    user_creating = self.context["request"].user
                    company_group = user_creating.company_group
                    if company_group:
                        validated_data["company_group"] = company_group
                    else:
                        raise Exception
                except Exception:
                    raise serializers.ValidationError(
                        "É necessário Membership ou Group Company para criar um novo usuário."
                    )
        else:
            memberships_lst = validated_data.pop("memberships")
            for membership in memberships_lst:
                try:
                    memberships.append(
                        (
                            Company.objects.get(pk=membership["company"]),
                            UserPermission.objects.get(pk=membership["permission"]),
                        )
                    )
                except Company.DoesNotExist:
                    raise serializers.ValidationError(
                        {
                            "company": [
                                "Company com id={} não existe!".format(
                                    membership["company"]
                                )
                            ]
                        }
                    )
                except UserPermission.DoesNotExist:
                    raise serializers.ValidationError(
                        {
                            "permissions": [
                                "UserPermission com id={} não existe!".format(
                                    membership["permission"]
                                )
                            ]
                        }
                    )

        # Autofill send_email_notifications
        if "configuration" not in validated_data.keys():
            validated_data["configuration"] = {"send_email_notifications": True}
        else:
            validated_data["configuration"]["send_email_notifications"] = True

        # Autofill SAML idp
        if "company_group" in validated_data and "saml_nameid" in validated_data:
            validated_data["saml_idp"] = validated_data["company_group"].saml_idp

        # Create user
        user = User.objects.create(**validated_data)
        user.set_password(validated_data["password"])
        user.save()

        if send_email:
            send_email_password(validated_data, user)

        # Bind user to company
        for membership in memberships:
            UserInCompany.objects.create(
                company=membership[0], user=user, permissions=membership[1]
            )

        # Create AccessRequest
        if (
            "create_access_request" in self.initial_data
            and self.initial_data["create_access_request"] is True
        ):
            try:
                company_id = self.initial_data["company"]["id"]
                permission_id = self.initial_data["permissions"]["id"]
                data = {
                    "user": user,
                    "expiration_date": self.initial_data.get("expiration_date"),
                    "description": "Solicitação de acesso criada no momento da criação do usuário",
                    "permissions": UserPermission.objects.get(pk=permission_id),
                    "created_by": self.context["request"].user,
                }
                create_access_request(data, company_id, [company_id])
            except Exception:
                raise serializers.ValidationError(
                    "Erro ao criar a Solicitação de Acesso."
                )

        if (
            validated_data.get("active") is not None
            and validated_data.get("active_company") is not None
        ):
            active_company = Company.objects.get(pk=validated_data["active_company"])
            user_in_company = UserInCompany.objects.filter(
                company=active_company
            ).first()
            active = validated_data["active"]
            self.update_active_company(
                company_id=active_company,
                user_in_company=user_in_company,
                active_company=active_company,
                active=active,
            )

        return user


class AuthUserSerializer(UserSerializer):
    companies = SerializerMethodResourceRelatedFieldWithName(
        model=Company, method_name="get_companies", read_only=True, many=True
    )
    company_group = ResourceRelatedFieldWithName(read_only=True)


class UserNotificationSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["user"]
    _PREFETCH_RELATED_FIELDS = [
        Prefetch("companies", queryset=Company.objects.all().only("uuid"))
    ]

    uuid = serializers.UUIDField(required=False)
    time_interval = LabeledChoiceField(choices=NOTIFICATION_INTERVALS)

    companies = serializers.ResourceRelatedField(queryset=Company.objects, many=True)

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

    def validate(self, attrs):
        notification_user = self.context["request"].user
        notification = get_field_if_provided_or_present(
            "notification", attrs, self.instance
        )
        notification_type = get_field_if_provided_or_present(
            "notification_type", attrs, self.instance
        )
        preferred_time = get_field_if_provided_or_present(
            "preferred_time", attrs, self.instance
        )
        time_interval = get_field_if_provided_or_present(
            "time_interval", attrs, self.instance
        )
        companies = get_field_if_provided_or_present(
            "companies", attrs, self.instance, many_to_many=True
        )

        # Check notification permissions
        allowed_notifications = get_possible_notifications(
            notification_user, companies=companies
        )
        if notification not in allowed_notifications:
            raise serializers.ValidationError(
                "kartado.error.user_notification.valid_notification_identifier_for_this_user_is_required"
            )

        accepts = get_notification_accepts(notification)
        accepted_types = accepts.get("notification_types", [])
        accepted_intervals = accepts.get("time_intervals", [])

        # Ensure chosen notification_type is valid for that notification
        if notification_type not in accepted_types:
            raise serializers.ValidationError(
                f"kartado.error.user_notification.invalid_notification_type_for_{notification}"
            )

        # Ensure chosen time_interval is valid for that notification
        if time_interval_to_label(time_interval) not in accepted_intervals:
            raise serializers.ValidationError(
                f"kartado.error.user_notification.invalid_time_interval_for_{notification}"
            )

        # Ensure preferred time is only set if time interval is at least one day
        if preferred_time and time_interval < timedelta(days=1):
            raise serializers.ValidationError(
                "kartado.error.user_notification.preferred_time_requires_time_interval_of_at_least_a_day"
            )

        return super().validate(attrs)


class ListCompaniesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["name"]


class UserSignatureSerializer(serializers.ModelSerializer, EagerLoadingMixin):

    _PREFETCH_RELATED_FIELDS = ["user", "company"]

    uuid = serializers.UUIDField(required=False)
    upload = EmptyFileField()
    upload_url = serializers.SerializerMethodField()

    class Meta:
        model = UserSignature
        fields = [
            "uuid",
            "user",
            "company",
            "created_at",
            "md5",
            "upload",
            "upload_url",
        ]

    def get_upload_url(self, obj):
        return {}
        # kept this field here to maintain compatibility

    def create(self, validated_data):

        uploaded_file_name = validated_data["upload"].name
        is_photo = uploaded_file_name.split(".")[-1].lower() in ["png", "jpeg", "jpg"]

        if not is_photo:
            raise serializers.ValidationError(
                "kartado.error.user_signature.uploaded_file_is_not_a_photo"
            )

        return super().create(validated_data)


class UserSignatureObjectSerializer(UserSignatureSerializer):
    def get_upload_url(self, obj):
        return get_rdo_file_url(obj)
