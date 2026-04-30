from datetime import timedelta

from django.conf import settings

from helpers.notifications import create_single_notification, get_disclaimer
from helpers.testing.auth_testing import get_user_token

from .models import UserInCompany


def send_approval_step_email(instance, access_request):
    """
    Trigger email to the responsible(s) of
    the new ApprovalStep presenting buttons to take
    action directly from the email.
    """
    needs_to_execute = instance.approval_flow.company.metadata.get(
        "send_approval_step_email", False
    )
    if not needs_to_execute:
        return

    # Actions
    actions = instance.origin_transitions.all()
    if not actions.exists():
        return

    # Responsible send to
    send_to = []

    for user in instance.responsible_users.all():
        send_to.append(user)

    for firm in instance.responsible_firms.all():
        if firm.manager:
            send_to.append(firm.manager)
        for user in firm.users.all():
            send_to.append(user)

    if instance.responsible_supervisor:
        send_to.append(access_request.user.supervisor)

    send_to = list(set([user for user in send_to if user]))

    # Add disclaimer
    company = instance.approval_flow.company
    disclaimer_msg, mobile_app = get_disclaimer(company.company_group)

    disclaimer_approval_title = "Não compartilhe este e-mail."
    disclaimer_approval = "Este e-mail contém um link seguro para a plataforma. \
        Não compartilhe este e-mail, link ou código de acesso com outras pessoas."

    req_user = access_request.user
    creator_user = access_request.created_by

    # Build context

    # Get action name and color
    names_and_colors = [
        {
            "name": action.name,
            "color": action.button["color"] if "color" in action.button else "#3F51B5",
        }
        for action in actions
    ]

    expires = timedelta(weeks=2)

    context = {
        "title": "Kartado - Ação requerida em solicitação de acesso",
        "name": access_request.description,
        "transitions_names": names_and_colors,
        "mobile_app": mobile_app,
        "disclaimer": disclaimer_msg,
        "disclaimer_approval": disclaimer_approval,
        "disclaimer_approval_title": disclaimer_approval_title,
        "approvers": [
            "{} {} - {}".format(a.first_name, a.last_name, a.email) for a in send_to
        ],
        "creator_info": [
            a
            for a in [
                ["Nome", creator_user.first_name],
                ["Sobrenome", creator_user.last_name],
                ["E-mail", creator_user.email],
                [
                    "Supervisor",
                    creator_user.supervisor.first_name
                    + " "
                    + creator_user.supervisor.last_name
                    if creator_user.supervisor
                    else "",
                ],
                ["Group ID ENGIE", creator_user.saml_nameid],
            ]
            if a[1]
        ],
        "user_info": [
            a
            for a in [
                ["Status Atual", instance.name],
                ["Descrição e Justificativa", access_request.description],
                [
                    "Unidades",
                    ", ".join(access_request.companies.values_list("name", flat=True)),
                ],
                [
                    "Nível de Acesso",
                    access_request.permissions.name
                    if access_request.permissions
                    else "",
                ],
                ["Data de Expiração", access_request.expiration_date],
                ["Tipo", "Interno" if req_user.is_internal else "Terceiro"],
                ["Nome", req_user.first_name],
                ["Sobrenome", req_user.last_name],
                [
                    "Profissão",
                    req_user.metadata["occupation"]
                    if "occupation" in req_user.metadata
                    else "",
                ],
                [
                    "Função",
                    req_user.metadata["role"] if "role" in req_user.metadata else "",
                ],
                [
                    "N Registro Conselho",
                    req_user.metadata["board_registration"]
                    if "board_registration" in req_user.metadata
                    else "",
                ],
                ["E-mail", req_user.email],
                [
                    "Responsável Direto",
                    req_user.responsible.first_name
                    + " "
                    + req_user.responsible.last_name
                    if req_user.responsible
                    else "",
                ],
                [
                    "Supervisor",
                    req_user.supervisor.first_name + " " + req_user.supervisor.last_name
                    if req_user.supervisor
                    else "",
                ],
                ["Nome da Empresa", req_user.firm_name],
                ["Login", req_user.username],
                ["Group ID ENGIE", req_user.saml_nameid],
            ]
            if a[1]
        ],
    }

    template_path = "companies/email/step_email"

    # Create a email for each user
    for user in send_to:
        # Create url
        action_url = "{}/AccessRequestApproval/?access={}&tk={}".format(
            settings.BACKEND_URL,
            str(access_request.pk),
            get_user_token(user, expires, "approvalOnly"),
        )
        if UserInCompany.objects.filter(user=user, company=company).exists():
            url = "{}/#/SharedLink/AccessRequest/{}/show?company={}".format(
                settings.FRONTEND_URL, str(access_request.pk), str(company.pk)
            )
        else:
            url = ""

        context = {**context, "link_url": url, "url": action_url}

        create_single_notification(
            user,
            company,
            context,
            template_path,
            instance=instance,
            url=url,
            can_unsubscribe=False,
        )
