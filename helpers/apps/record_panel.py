from django.conf import settings

from apps.companies.models import UserInCompany
from helpers.notifications import create_push_notifications
from helpers.strings import to_snake_case


def send_panel_notifications(panel):
    users = []
    company = panel.company
    created_by = panel.created_by

    users.extend(panel.viewer_users.all())
    users.extend(panel.editor_users.all())
    for firm in panel.viewer_firms.all():
        users.extend(firm.users.all())
        users.extend(firm.inspectors.all())
        if firm.manager:
            users.append(firm.manager)
    for firm in panel.editor_firms.all():
        users.extend(firm.users.all())
        users.extend(firm.inspectors.all())
        if firm.manager:
            users.append(firm.manager)
    for permission in panel.viewer_permissions.all():
        uics = UserInCompany.objects.filter(company=company, permissions=permission)
        users.extend([item.user for item in uics])
    for permission in panel.editor_permissions.all():
        uics = UserInCompany.objects.filter(company=company, permissions=permission)
        users.extend([item.user for item in uics])

    users = [user for user in set(users) if user.pk != created_by.pk]

    message = f'O painel "{panel.name}" do menu "{panel.menu.name if panel.menu else ""}" foi compartilhado com você'

    url = "{}/#/SharedLink/RecordMenu?company={}&currentTab=hide_menu=false".format(
        settings.FRONTEND_URL, str(company.pk)
    )
    create_push_notifications(users, message, company, panel, url)


def handle_field_name(field_name):
    lookup_table = {
        "title": "search_tag_description",
        "firm": "firm__name",
        "subCompany": "firm__subcompany__name",
        "datetime": "created_at",
        "inventoryNumber": "parent__number",
        "status": "status__name",
        "occurrenceType": "occurrence_type__name",
        "approvalStep": "approval_step__name",
        "job": "job__start_date",
    }

    if field_name in lookup_table:
        return to_snake_case(lookup_table[field_name])

    return to_snake_case(field_name)
