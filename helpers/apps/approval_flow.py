from typing import Any, Iterable

from django.db.models import Q

from apps.approval_flows.models import ApprovalStep
from apps.users.models import User, UserNotification
from helpers.apps.json_logic import apply_json_logic
from helpers.strings import to_snake_case


def get_responsibles_uuids(obj: object) -> Iterable[User]:
    """
    Receives an object with an approval_step and returns the UUIDs of the responsible users

    Args:
        obj (object): The object where we're going to extract the responsible users

    Returns:
        Iterable[User]: List of the responsible Users UUIDs
    """

    responsibles = []
    approval_step: ApprovalStep = getattr(obj, "approval_step", None)
    created_by: User = getattr(obj, "created_by", None)

    if approval_step:
        if approval_step.responsible_created_by and created_by:
            responsibles.append(created_by.uuid)

        if approval_step.responsible_users.exists():
            responsible_users = approval_step.responsible_users.all().values_list(
                "uuid", flat=True
            )
            responsibles.extend(responsible_users)

        if approval_step.responsible_firms.exists():
            users_in_resp_firms = approval_step.responsible_firms.all().values_list(
                "uuid", flat=True
            )
            responsibles.extend(users_in_resp_firms)

        if (
            approval_step.responsible_firm_entity
            and obj.firm
            and obj.firm.entity
            and obj.firm.entity.approver_firm
        ):
            users_in_approver_firms = approval_step.responsible_firms.all().values_list(
                "uuid", flat=True
            )
            responsibles.extend(users_in_approver_firms)

    return responsibles


def is_currently_responsible(obj, user, user_firms, user_permissions):
    # object must have an approval_step
    if not obj.approval_step:
        return False

    # check responsible_created_by
    if obj.approval_step.responsible_created_by and obj.created_by == user:
        return True

    # check responsible_users
    if user in obj.approval_step.responsible_users.all():
        return True

    # check responsible_firms
    for firm in obj.approval_step.responsible_firms.all():
        if firm in user_firms:
            return True

    # check responsible_firm_entity
    if (
        obj.approval_step.responsible_firm_entity
        and obj.firm
        and obj.firm.entity
        and obj.firm.entity.approver_firm
        and obj.firm.entity.approver_firm in user_firms
    ):
        return True

    obj_model_name = to_snake_case(obj._meta.model.__name__)

    # check responsible_json_logic
    try:
        data = {
            obj_model_name: obj.__dict__,
            "user": user.__dict__,
            "user_permission": user_permissions,
            "user_firms": user_firms,
        }
        if apply_json_logic(obj.approval_step.responsible_json_logic, data):
            return True
    except Exception:
        pass

    return False


def get_user_notif_of_approval_responsibles(
    instance: Any, notification: str, approval_step_field: str = "approval_step"
) -> Iterable[UserNotification]:
    """
    Return the UserNotification QuerySet containing all instances configured
    to notify the provided notification if that User is part of the responsibles.

    If the field containing the relation to ApprovalStep has an out of ordinary name
    it can be provided using the approval_step_field.

    Args:
        instance (Any): Instance that's part of the approval flow
        notification (str): The notification identifier for the UserNotification instances
        approval_step_field (str, optional): Field for the ApprovalStep relation. Defaults to "approval_step".

    Raises:
        AttributeError: Raised when the provided instance doesn't have the provided approval_step_field
        AssertionError: The provided approval_step_field does not point to a ApprovalStep instance

    Returns:
        Iterable[UserNotification]: QuerySet of the UserNotification of the responsibles
    """

    # Validate the ApprovalStep
    approval_step = getattr(instance, approval_step_field, None)
    if not isinstance(approval_step, ApprovalStep):
        return UserNotification.objects.none()

    # Responsible users
    resp_user_notifs = UserNotification.objects.filter(
        notification=notification, user__user_steps__in=[approval_step]
    )

    # Responsible users and managers in firms
    resp_firms = approval_step.responsible_firms.all().only("uuid", "manager")
    resp_firms_uuids = resp_firms.values_list("uuid", flat=True)
    firm_managers = resp_firms.values_list("manager", flat=True)
    resp_firm_notifs = UserNotification.objects.filter(
        Q(notification=notification)
        & (Q(user__user_firms__in=resp_firms_uuids) | Q(user__in=firm_managers))
    )

    # Responsible creator
    resp_created_by_notif = UserNotification.objects.none()
    if approval_step.responsible_created_by:
        resp_created_by_notif = UserNotification.objects.filter(
            notification=notification, user=instance.created_by
        )

    # Responsible users in approver firms
    resp_entity_notifs = UserNotification.objects.none()
    approver_firm = (
        instance.firm.entity.approver_firm
        if instance.firm and instance.firm.entity
        else None
    )
    if approval_step.responsible_firm_entity and approver_firm:
        approver_firm_users = approver_firm.users.all().values_list("uuid")
        resp_entity_notifs = UserNotification.objects.filter(
            notification=notification, user__in=approver_firm_users
        )

    # Merge all querysets
    # WARN: All querysets must be from the same model and contain the same fields
    ids = set(
        list(resp_user_notifs.values_list("uuid", flat=True))
        + list(resp_firm_notifs.values_list("uuid", flat=True))
        + list(resp_created_by_notif.values_list("uuid", flat=True))
        + list(resp_entity_notifs.values_list("uuid", flat=True))
    )

    user_notifs = UserNotification.objects.filter(uuid__in=ids)

    # Return queryset without duplicates
    return user_notifs
