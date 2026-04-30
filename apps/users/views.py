import json
import logging
import uuid
from datetime import timedelta
from typing import List

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connections
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import render
from django.utils import timezone
from django_rest_passwordreset.models import (
    ResetPasswordToken,
    get_password_reset_token_expiry_time,
)
from django_rest_passwordreset.serializers import PasswordTokenSerializer
from django_rest_passwordreset.signals import (
    post_password_reset,
    pre_password_reset,
    reset_password_token_created,
)
from django_rest_passwordreset.views import (
    ResetPasswordConfirm,
    ResetPasswordRequestToken,
    clear_expired_tokens,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_json_api import serializers

from apps.companies.models import Company, UserInCompany
from apps.email_handler.models import QueuedEmail
from apps.notifications.helpers.device import create_device
from apps.users.filters import UserFilter, UserNotificationFilter, UserSignatureFilter
from apps.users.helpers import get_uic_history
from helpers.apps.engie_idm_rh import EngieIdmRH
from helpers.apps.engie_rh import (
    EngieRH,
    NoResultsError,
    ServiceUnavailableError,
    UnknownError,
    UserAlreadyExistsError,
)
from helpers.apps.users import (
    get_notification_accepts,
    get_notification_summary,
    get_possible_notifications,
    label_to_time_interval,
)
from helpers.error_messages import error_message
from helpers.files import check_endpoint
from helpers.json_parser import JSONRenderer
from helpers.mixins import ListCacheMixin
from helpers.permissions import PermissionManager, join_queryset
from helpers.strings import dict_to_casing, iter_items_to_str
from helpers.validators.password_validations import validate_password

from .models import User, UserNotification, UserSignature
from .permissions import (
    IsUserAuthenticated,
    UserNotificationPermissions,
    UserPermissions,
    UserSignaturePermissions,
)
from .serializers import (
    ListCompaniesSerializer,
    UserNotificationSerializer,
    UserSerializer,
    UserSignatureObjectSerializer,
    UserSignatureSerializer,
)


class UserViewSet(ListCacheMixin, viewsets.ModelViewSet):
    resource_name = "User"
    serializer_class = UserSerializer
    filterset_class = UserFilter
    permissions = None

    ordering_fields = [
        "uuid",
        "cpf",
        "first_name",
        "last_name",
        "username",
        "saml_nameid",
        "email",
        "metadata__occupation",
        "metadata__role",
        "configuration__send_email_notifications",
        "active",
    ]
    ordering = "uuid"

    def get_serializer_context(self):
        context = super(UserViewSet, self).get_serializer_context()
        request_method = self.request.method.lower()
        if request_method == "get":
            company_id = self.request.query_params.get("company")
            if company_id is not None:
                context.update({"user_company": company_id})

        elif request_method == "patch" or request_method == "put":
            company_id = self.request.data.get("active_company")
            if company_id is not None:
                context.update({"user_company": company_id})
        return context

    def get_permissions(self):
        if self.action in [
            "email_unsubscribe",
            "email_unsubscribe_user_notification",
        ]:
            self.permission_classes = []
        elif not self.request.user or not self.request.user.is_authenticated:
            self.permission_classes = [IsAuthenticated]
        elif UserInCompany.objects.filter(user=self.request.user).exists():
            self.permission_classes = [UserPermissions]
        else:
            self.permission_classes = [IsUserAuthenticated]

        return super(UserViewSet, self).get_permissions()

    def get_queryset(self):
        if not self.request.user or not self.request.user.is_authenticated:
            return User.objects.none()

        queryset = None
        request_user = self.request.user
        if UserPermissions in self.permission_classes:
            # On list action: limit queryset
            if self.action == "list":
                if "company" not in self.request.query_params:
                    return User.objects.none()

                user_company = uuid.UUID(self.request.query_params["company"])
                if not self.permissions:
                    self.permissions = PermissionManager(
                        user=request_user,
                        company_ids=user_company,
                        model="User",
                    )

                allowed_queryset = self.permissions.get_allowed_queryset()

                if "none" in allowed_queryset:
                    queryset = join_queryset(
                        queryset,
                        User.objects.filter(uuid=request_user.uuid),
                    )
                if "self" in allowed_queryset:
                    queryset = join_queryset(
                        queryset,
                        User.objects.filter(uuid=request_user.uuid),
                    )
                if "all" in allowed_queryset:
                    user_companies = request_user.companies.all()
                    queryset = join_queryset(
                        queryset,
                        User.objects.filter(
                            Q(companies__in=user_companies)
                            | Q(company_group_id=request_user.company_group_id)
                        ),
                    )

                # Annotate if user is active or not for that company
                queryset = (
                    queryset.annotate(
                        active=Exists(
                            UserInCompany.objects.filter(
                                is_active=True,
                                company=user_company,
                                user=OuterRef("pk"),
                            )
                        )
                    )
                    if queryset is not None
                    else queryset
                )

            # If queryset isn't set by any means above
            if queryset is None:
                user_companies = request_user.companies.all()
                queryset = User.objects.filter(
                    Q(companies__in=user_companies)
                    | Q(company_group=request_user.company_group)
                )
        elif hasattr(request_user, "uuid"):
            queryset = User.objects.filter(uuid=request_user.uuid)
        else:
            return User.objects.none()

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["post"], url_path="RegisterPush", detail=True)
    def register_push(self, request, pk=None):
        user = self.get_object()

        if request.user != user:
            return error_message(400, "Não foi possível realizar esta operação")

        if "token" in request.data.keys() and "is_dev" in request.data.keys():
            device = create_device(request.data["token"], request.data["os"])
            user.push_devices.add(device)

            return error_message(200, "OK")

        return error_message(400, "Request inválido ou mal-formado")

    @action(methods=["post"], url_path="AcceptTOS", detail=True)
    def accept_tos(self, request, pk=None):
        user = self.get_object()

        if request.user != user:
            return error_message(400, "Não foi possível realizar esta operação")

        if "has_accepted_tos" in request.data.keys():
            user.has_accepted_tos = request.data["has_accepted_tos"]
            user.save()

            return error_message(200, "OK")

        return error_message(400, "Request inválido ou mal-formado")

    @action(methods=["get"], url_path="EngiePreview", detail=False)
    def engie_preview(self, request, pk=None):
        company = Company.objects.get(uuid=self.permissions.company_id)
        if (
            "matricula" not in request.query_params
            or not request.query_params["matricula"]
        ):
            return error_message(400, "kartado.error.user.matricula")

        matricula = request.query_params["matricula"]

        rh_api = EngieRH(matricula, company)
        try:
            result = rh_api.preview_user()
        except UserAlreadyExistsError:
            return error_message(400, "kartado.error.user.already_exists")
        except ServiceUnavailableError:
            return error_message(400, "kartado.error.user.service_unavailable")
        except UnknownError:
            return error_message(400, "kartado.error.user.service_unavailable")
        except NoResultsError:
            return error_message(404, "kartado.error.user.no_results")
        except Exception:
            return error_message(400, "Request inválido ou mal-formado")
        else:
            return Response([{"attributes": result}])

    @action(methods=["post"], url_path="EngieCreate", detail=False)
    def engie_create(self, request, pk=None):
        company = Company.objects.get(uuid=self.permissions.company_id)
        if "matricula" not in request.data or not request.data["matricula"]:
            return error_message(400, "kartado.error.user.matricula")

        matricula = request.data["matricula"]

        rh_api = EngieRH(matricula, company)
        try:
            result = rh_api.create_user()
        except UserAlreadyExistsError:
            return error_message(400, "kartado.error.user.already_exists")
        except ServiceUnavailableError:
            return error_message(400, "kartado.error.user.service_unavailable")
        except UnknownError:
            return error_message(400, "kartado.error.user.service_unavailable")
        except NoResultsError:
            return error_message(404, "kartado.error.user.no_results")
        except Exception:
            return error_message(400, "Request inválido ou mal-formado")
        else:
            return Response(
                json.loads(
                    JSONRenderer().render(
                        UserSerializer(result).data,
                        renderer_context={"view": UserViewSet},
                    )
                )["data"]
            )

    @action(methods=["get"], url_path="EngieIdmPreview", detail=False)
    def engie_idm_preview(self, request, pk=None):
        company = Company.objects.get(uuid=self.permissions.company_id)
        if (
            "group_id" not in request.query_params
            or not request.query_params["group_id"]
        ):
            return error_message(400, "kartado.error.user.group_id")

        group_id = request.query_params["group_id"]

        rh_api = EngieIdmRH(group_id, company.company_group)
        try:
            result = rh_api.preview_user()
        except UserAlreadyExistsError:
            return error_message(400, "kartado.error.user.already_exists")
        except ServiceUnavailableError:
            return error_message(400, "kartado.error.user.service_unavailable")
        except UnknownError:
            return error_message(400, "kartado.error.user.service_unavailable")
        except NoResultsError:
            return error_message(404, "kartado.error.user.no_results")
        except Exception:
            return error_message(400, "Request inválido ou mal-formado")
        else:
            return Response([{"attributes": result}])

    @action(methods=["post"], url_path="EngieIdmCreate", detail=False)
    def engie_idm_create(self, request, pk=None):
        company = Company.objects.get(uuid=self.permissions.company_id)
        if "group_id" not in request.data or not request.data["group_id"]:
            return error_message(400, "kartado.error.user.group_id")

        group_id = request.data["group_id"]

        rh_api = EngieIdmRH(group_id, company.company_group)
        try:
            result = rh_api.create_user()
        except UserAlreadyExistsError:
            return error_message(400, "kartado.error.user.already_exists")
        except ServiceUnavailableError:
            return error_message(400, "kartado.error.user.service_unavailable")
        except UnknownError:
            return error_message(400, "kartado.error.user.service_unavailable")
        except NoResultsError:
            return error_message(404, "kartado.error.user.no_results")
        except Exception:
            return error_message(400, "Request inválido ou mal-formado")
        else:
            return Response(
                json.loads(
                    JSONRenderer().render(
                        UserSerializer(result).data,
                        renderer_context={"view": UserViewSet},
                    )
                )["data"]
            )

    @action(methods=["get"], url_path="Unsubscribe", detail=True)
    def email_unsubscribe(self, request, pk=None):
        try:
            # Get user who want's to unsubscribe
            user = User.objects.get(pk=pk)

            # Confirm the unsubscription comes from a real email to that user
            queued_email_id = request.query_params["qe"]
            queued_email = QueuedEmail.objects.get(pk=queued_email_id)
            queued_email.send_to_users.get(pk=user.uuid)

            user.configuration["send_email_notifications"] = False
            user.save()
            context = {"message": "Sucesso."}
        except Exception:

            context = {
                "message": "Houve um erro na sua solicitação. Entre em contato com nossa equipe."
            }

        return render(request, "users/email/unsubscribe.html", context)

    @action(methods=["get"], url_path="UnsubscribeUserNotification", detail=True)
    def email_unsubscribe_user_notification(self, request, pk=None):
        try:
            # Get user who want's to unsubscribe
            user = User.objects.get(pk=pk)

            # Confirm the unsubscription comes from a real email to that user
            queued_email_id = request.query_params["qe"]
            queued_email = QueuedEmail.objects.get(pk=queued_email_id)
            queued_email.send_to_users.get(pk=user.uuid)

            # Remove the config for that notification for that user
            UserNotification.objects.filter(
                notification=request.query_params["un"], user=user
            ).delete()

            context = {
                "message": "Sucesso. Você não receberá mais notificações desse tipo."
            }
        except Exception:

            context = {
                "message": "Houve um erro na sua solicitação. Entre em contato com nossa equipe."
            }

        return render(request, "users/email/unsubscribe.html", context)

    @action(methods=["GET"], url_path="History", detail=True)
    def history(self, request, pk=None):
        try:
            company_id = request.query_params["company"]
        except Exception:
            return error_message(
                400,
                'Parâmetro "Unidade" é obrigatório',
            )
        try:
            uic = UserInCompany.objects.get(user_id=pk, company_id=company_id)
            data = get_uic_history(uic)
        except Exception:
            data = {"history": []}
        return Response(data=data, status=status.HTTP_200_OK)


class UserNotificationView(viewsets.ModelViewSet):
    serializer_class = UserNotificationSerializer
    filterset_class = UserNotificationFilter
    permissions = None
    permission_classes = [IsAuthenticated, UserNotificationPermissions]

    ordering = "uuid"
    ordering_fields = [
        "user",
        "companies",
        "notification",
        "notification_type",
        "time_interval",
        "preferred_time",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return UserNotification.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="UserNotification",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, UserNotification.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    UserNotification.objects.filter(
                        companies=user_company, user=self.request.user
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = UserNotification.objects.filter(
                companies__in=user_companies, user=self.request.user
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    @action(methods=["GET"], url_path="Summary", detail=False)
    def summary(self, request, pk=None):
        user = self.request.user
        company = Company.objects.get(uuid=request.query_params["company"])

        return Response(get_notification_summary(company, user))

    @action(methods=["POST"], url_path="Change", detail=False)
    def change(self, request, pk=None):
        try:
            input_data = dict_to_casing(json.loads(request.body), "underscore")
            assert type(input_data["data"]) is list
            assert all([type(item) is dict for item in input_data["data"]])
        except Exception:
            raise serializers.ValidationError(
                "kartado.error.user_notification.invalid_json_body_was_sent"
            )

        user = self.request.user

        activate = []
        deactivate = []
        for item in input_data["data"]:
            notification: str = item.get("notification", "")
            _, notif_short_name = notification.split(".")
            notification_type: str = item.get("notification_type", "")
            time_interval: str = item.get("time_interval", "")
            companies: List = item.get("companies", [])

            # If the old `company` field was provided, add it to the `companies` list and update the item.
            # NOTE: This is done for backwards compatibility and should be phased out.
            company = item.get("company", None)
            if company and company not in companies:
                companies.append(company)
                item["companies"] = companies
                logging.warning(
                    "/UserNotification/Change/: Legacy company field was used. Please use companies field instead."
                )

            # Company IDs validation
            if not companies:
                raise serializers.ValidationError(
                    f"kartado.error.user_notification.please_provide_companies_field_for_{notif_short_name}_with_at_least_one_company_id"
                )
            if Company.objects.filter(uuid__in=companies).count() != len(companies):
                raise serializers.ValidationError(
                    f"kartado.error.user_notification.at_least_one_provided_company_for_{notif_short_name}_doesnt_exist"
                )

            # Validate that the User is permitted to set that notification
            if notification not in get_possible_notifications(
                user, companies_ids=companies
            ):
                raise serializers.ValidationError(
                    "kartado.error.user_notification.valid_notification_identifier_for_this_user_is_required"
                )

            # Validate that the data matches what's accepted for that particular notification
            accepts = get_notification_accepts(notification)
            accepted_types = accepts.get("notification_types", [])
            accepted_intervals = accepts.get("time_intervals", [])

            if notification_type not in accepted_types:
                raise serializers.ValidationError(
                    f"kartado.error.user_notification.invalid_notification_type_for_{notif_short_name}"
                )

            if time_interval not in accepted_intervals:
                raise serializers.ValidationError(
                    f"kartado.error.user_notification.invalid_time_interval_for_{notif_short_name}"
                )

            # Separate the item according to the desired action
            if item["enable"]:
                activate.append(item)
            else:
                deactivate.append(item)

        # Response report
        report = {"activated": [], "deactivated": []}

        # NOTE: The deactivation will be applied only for the provided Company UUIDs
        if deactivate:
            for item in deactivate:
                time_interval = label_to_time_interval(item["time_interval"])

                try:
                    usr_notif = UserNotification.objects.get(
                        companies__in=item["companies"],
                        notification=item["notification"],
                        notification_type=item["notification_type"].upper(),
                        time_interval=time_interval,
                        user=user,
                    )

                    # Get the IDs of the Company instances that are in the instance
                    instance_companies_ids = iter_items_to_str(
                        usr_notif.companies.values_list("uuid", flat=True)
                    )

                    # Which provided companies are actually present in the instance
                    present_companies = [
                        company_id
                        for company_id in item["companies"]
                        if company_id in instance_companies_ids
                    ]

                    # If removing for all Company instances that exist on that UserNotification,
                    # just delete the UserNotification instead
                    if len(instance_companies_ids) == len(present_companies):
                        usr_notif.delete()
                    # Remove only some of the UserNotification's Company instances
                    else:
                        usr_notif.companies.remove(*present_companies)

                except UserNotification.DoesNotExist:
                    # If it doesn't exist there is no need to stop
                    pass

                report["deactivated"].append(item)

        if activate:
            for item in activate:
                time_interval = label_to_time_interval(item["time_interval"])

                usr_notif = UserNotification.objects.filter(
                    notification=item["notification"],
                    notification_type=item["notification_type"].upper(),
                    time_interval=time_interval,
                    user=user,
                ).first()

                # If a instance already exists for that combination just add the new companies (if any)
                if usr_notif:
                    # Get the IDs of the Company instances that are in the instance
                    instance_companies_ids = iter_items_to_str(
                        usr_notif.companies.values_list("uuid", flat=True)
                    )

                    # Which provided companies are actually present in the instance
                    companies_to_add = [
                        company_id
                        for company_id in item["companies"]
                        if company_id not in instance_companies_ids
                    ]

                    # Add the new Company instances (if there's any to be added)
                    if companies_to_add:
                        usr_notif.companies.add(*companies_to_add)

                # If no instance exists for that combination, create it
                else:
                    kwargs = {
                        "notification": item["notification"],
                        "notification_type": item["notification_type"].upper(),
                        "time_interval": time_interval,
                        "user": user,
                    }

                    if "preferred_time" in item:
                        kwargs["preferred_time"] = item["preferred_time"]

                    # NOTE: Have to create on each iteration instead of using bulk_create
                    # because direct assignment to many to many fields is prohibited :(
                    user_notif = UserNotification.objects.create(**kwargs)
                    user_notif.companies.add(*item["companies"])

            report["activated"] = activate

        return Response(dict_to_casing(report))


class ListCompaniesViewSet(viewsets.ReadOnlyModelViewSet):
    """
    A simple ViewSet for showing all Company names.
    """

    queryset = Company.objects.all()
    serializer_class = ListCompaniesSerializer
    permission_classes = []
    permissions = None
    ordering = "name"


class CheckGidView(APIView):
    permission_classes = []

    def post(self, request, format=None):
        if "username" not in request.data or not request.data["username"]:
            return error_message(400, "kartado.error.user.username_required")

        username = request.data["username"]

        DBS_AND_API_URLS = [
            ["default", settings.DEFAULT_BACKEND_URL],
            ["engie_prod", settings.ENGIE_BACKEND_URL],
            ["ccr_prod", settings.CCR_BACKEND_URL],
        ]

        for db_alias, api_url in DBS_AND_API_URLS:
            if db_alias in connections.databases:
                gid_exists = (
                    User.objects.using(db_alias).filter(saml_nameid=username).exists()
                )
                if gid_exists:
                    return Response({"exists": True, "api_url": api_url})

        return Response({"exists": False, "api_url": ""})


class CheckEmailView(APIView):
    permission_classes = []

    def post(self, request, format=None):
        if "email" not in request.data or not request.data["email"]:
            return error_message(400, "kartado.error.user.email_required")

        email = request.data["email"]
        query_dict = {"email__iexact": email}

        username = request.data.get("username")
        if username:
            query_dict["username__iexact"] = username

        DBS_AND_API_URLS = [
            ["default", settings.DEFAULT_BACKEND_URL],
            ["engie_prod", settings.ENGIE_BACKEND_URL],
            ["ccr_prod", settings.CCR_BACKEND_URL],
        ]

        for db_alias, api_url in DBS_AND_API_URLS:
            if db_alias in connections.databases:
                user_exists = User.objects.using(db_alias).filter(**query_dict).exists()
                if user_exists:
                    return Response({"exists": True, "api_url": api_url})

        return Response({"exists": False, "api_url": ""})


class ResetPasswordRequestTokenCustom(ResetPasswordRequestToken):
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        initial_data = serializer.initial_data

        email = validated_data["email"]
        query_dict = {"email__iexact": email}

        if "username" in initial_data and initial_data["username"]:
            username = initial_data["username"]
            query_dict["username__iexact"] = username

        clear_expired_tokens()

        # find a user by email address (case insensitive search)
        users = User.objects.filter(**query_dict)

        active_user_found = False

        # iterate over all users and check if there is any user that is active
        # also check whether the password can be changed (is useable), as there could be users that are not allowed
        # to change their password (e.g., LDAP user)
        for user in users:
            if user.eligible_for_reset():
                active_user_found = True
                break

        # No active user found, raise a validation error
        if not active_user_found:
            raise serializers.ValidationError(
                "kartado.error.email_not_associated_with_system"
            )

        # last but not least: iterate over all users that are active and can change their password
        # and create a Reset Password Token and send a signal with the created token
        for user in users:
            if user.eligible_for_reset():

                password_reset_tokens = user.password_reset_tokens.all()
                # check if the user already has a token
                if password_reset_tokens.count():
                    # yes, already has a token, re-use this token
                    token = password_reset_tokens.first()
                else:
                    # no token exists, generate a new token
                    token = ResetPasswordToken.objects.create(
                        user=user,
                        user_agent=request.META["HTTP_USER_AGENT"],
                        ip_address=request.META["REMOTE_ADDR"],
                    )
                # send a signal that the password token was created
                # let whoever receives this signal handle sending the email for the password reset
                reset_password_token_created.send(
                    sender=self.__class__, instance=self, reset_password_token=token
                )
        # done
        return error_message(200, "kartado.success.password.new_password_link_sent")


class ResetPasswordConfirmCustom(ResetPasswordConfirm):
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        password = serializer.validated_data["password"]
        token = serializer.validated_data["token"]

        # get token validation time
        password_reset_token_validation_time = get_password_reset_token_expiry_time()

        # find token
        reset_password_token = ResetPasswordToken.objects.filter(key=token).first()

        if reset_password_token is None:
            raise serializers.ValidationError("kartado.error.password.expired_request")

        # check expiry date
        expiry_date = reset_password_token.created_at + timedelta(
            hours=password_reset_token_validation_time
        )

        if timezone.now() > expiry_date:
            # delete expired token
            reset_password_token.delete()
            raise serializers.ValidationError("kartado.error.password.expired_request")
        # change users password
        if reset_password_token.user.eligible_for_reset():
            pre_password_reset.send(
                sender=self.__class__,
                user=reset_password_token.user,
                reset_password_token=reset_password_token,
            )
            try:
                # validate the password against existing validators
                validate_password(password, user=reset_password_token.user)
            except ValidationError as e:
                # raise a validation error for the serializer
                raise serializers.ValidationError({"password": e.messages})

            reset_password_token.user.set_password(password)
            reset_password_token.user.save()
            post_password_reset.send(
                sender=self.__class__,
                user=reset_password_token.user,
                reset_password_token=reset_password_token,
            )

        # Delete all password reset tokens for this user
        ResetPasswordToken.objects.filter(user=reset_password_token.user).delete()

        return error_message(200, "kartado.success.password.new_password_confirmed")


class IsNewPasswordValid(APIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = PasswordTokenSerializer

    def post(self, request, format=None):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        password = serializer.validated_data["password"]
        token = serializer.validated_data["token"]

        # find token
        reset_password_token = ResetPasswordToken.objects.filter(key=token).first()

        if reset_password_token is None:
            raise serializers.ValidationError("kartado.error.password.expired_request")

        try:
            # validate the password against existing validators
            validate_password(password, user=reset_password_token.user, general=True)
        except ValidationError as e:
            # raise a validation error for the serializer
            raise serializers.ValidationError({"password": e.messages})

        return Response({"status": "OK"})


class UserSignatureView(ListCacheMixin, viewsets.ModelViewSet):

    permission_classes = [IsAuthenticated, UserSignaturePermissions]
    filterset_class = UserSignatureFilter
    permissions = None
    ordering = "uuid"

    def get_serializer_class(self):
        if self.action in ["retrieve", "update", "partial_update", "create"]:
            return UserSignatureObjectSerializer
        return UserSignatureSerializer

    def get_queryset(self):
        queryset = None

        # On list or retrieve action: limit queryset
        if self.action in ["list", "retrieve"]:
            if "company" not in self.request.query_params:
                return UserSignature.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="UserSignature",
                )
            allowed_queryset = self.permissions.get_allowed_queryset()

            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, UserSignature.objects.none())

            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    UserSignature.objects.filter(company_id=user_company),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = UserSignature.objects.filter(company__in=user_companies)
        queryset = self.get_serializer_class().setup_eager_loading(queryset.distinct())

        return queryset

    @action(methods=["get"], url_path="Check", detail=True)
    def check(self, request, pk=None):
        return check_endpoint(self.get_object())
