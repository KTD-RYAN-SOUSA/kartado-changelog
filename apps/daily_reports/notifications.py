from django.conf import settings

from helpers.apps.json_logic import apply_json_logic
from helpers.notifications import create_push_notifications
from helpers.permissions import PermissionManager
from helpers.strings import to_snake_case


def report_transition(report, message, request_user):
    company = report.company
    model_name = type(report).__name__

    permissions = PermissionManager(
        user=request_user,
        company_ids=str(company.uuid),
        model=type(report).__name__,
    )

    data = {
        to_snake_case(model_name): report.__dict__,
        "user": request_user.__dict__,
        "user_permission": permissions.all_permissions,
    }

    responsibles = []

    user_in_responsibles = apply_json_logic(
        report.approval_step.responsible_json_logic, data
    )
    if user_in_responsibles:
        responsibles.append(request_user)

    if report.approval_step.responsible_created_by:
        responsibles.append(report.created_by)

    for user in report.approval_step.responsible_users.all():
        responsibles.append(user)

    for firm in report.approval_step.responsible_firms.all():
        if firm.manager:
            responsibles.append(firm.manager)
        for user in firm.users.all():
            responsibles.append(user)

    # Remove duplicates
    responsibles = list(set(responsibles))

    url = "{}/#/SharedLink/{}/{}/show?company={}".format(
        settings.FRONTEND_URL, model_name, str(report.uuid), str(company.pk)
    )

    create_push_notifications(responsibles, message, company, report, url)
