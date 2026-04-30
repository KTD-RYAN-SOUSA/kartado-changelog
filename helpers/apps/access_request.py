from django.conf import settings
from rest_framework_json_api import serializers

from apps.approval_flows.models import ApprovalStep, ApprovalTransition
from apps.companies.models import AccessRequest, UserInCompany
from apps.to_dos.models import ToDoAction, ToDoActionStep
from apps.users.models import User
from helpers.apps.todo import generate_todo
from helpers.middlewares import get_current_user


def create_access_request(validated_data, company_id, companies=[]):
    validated_data["company_id"] = company_id
    try:
        approval_step = ApprovalStep.objects.filter(
            approval_flow__company_id=company_id,
            approval_flow__target_model="companies.AccessRequest",
            previous_steps__isnull=True,
        )[0]
        validated_data["approval_step"] = approval_step
    except Exception:
        raise (
            serializers.ValidationError(
                "Não foi possível criar a requisição de acesso. Contate nossa equipe."
            )
        )

    instance = AccessRequest.objects.create(**validated_data)

    instance.companies.set(companies)

    """
    if the ApprovalStep set has the auto_execute_transition
    flag set to True, execute its callback
    """
    if approval_step.auto_execute_transition:
        transitions = ApprovalTransition.objects.filter(origin=approval_step)
        for transition in transitions:
            instance.approval_step = transition.destination

            for key, callback in transition.callback.items():
                if key == "change_fields":
                    for field in callback:
                        try:
                            setattr(instance, field["name"], field["value"])
                        except Exception as e:
                            print("Exception setting model fields", e)

                elif key == "create_user_in_company" and callback:
                    if not instance.permissions:
                        raise serializers.ValidationError(
                            "Nenhum nível de permissão foi especificado"
                        )

                    # Libera acesso para TODAS as companies no AccessRequest
                    # (importante para is_clustered_access_request=True)
                    companies_to_grant_access = instance.companies.all()

                    for company in companies_to_grant_access:
                        if UserInCompany.objects.filter(
                            user=instance.user, company=company
                        ).exists():
                            uic = UserInCompany.objects.get(
                                user=instance.user, company=company
                            )
                            uic.permissions = instance.permissions
                            uic.expiration_date = (
                                instance.expiration_date if uic.is_active else None
                            )
                            uic.save()
                        else:
                            UserInCompany.objects.create(
                                user=instance.user,
                                company=company,
                                permissions=instance.permissions,
                                expiration_date=instance.expiration_date
                                if instance.expiration_date
                                else None,
                            )

            instance.save()

    try:
        if instance.approval_step:
            from apps.companies.notifications import send_approval_step_email

            send_approval_step_email(instance.approval_step, instance)
            description = {}
            request_user = instance.user
            description["access_request"] = request_user.get_full_name()
            description["permission"] = instance.permissions.name
            description["company"] = instance.company.name
            description["expiration_date"] = str(instance.expiration_date)
            description["approval_step_status"] = instance.approval_step.uuid

            url = "{}/#/SharedLink/AccessRequest/{}/show?company={}".format(
                settings.FRONTEND_URL,
                str(instance.pk),
                str(instance.company.pk),
            )
            # Look for ToDoActionStep with this approval step and company_group
            action_step = ToDoActionStep.objects.filter(
                approval_step=instance.approval_step,
                todo_action__company_group=instance.company.company_group,
            )
            # If there is any for this company group
            if len(action_step):
                # If there is, should be only one. So get the first one
                action_step = action_step.first()
                # Then get the respective ToDoAction
                action = ToDoAction.objects.filter(
                    action_steps=action_step,
                    company_group=instance.company.company_group,
                ).first()

                independent_todos = False
                send_to = []
                # Get responsibles for this step
                if action_step.destinatary == "responsible":
                    for user in instance.approval_step.responsible_users.all():
                        send_to.append(user)
                    for firm in instance.approval_step.responsible_firms.all():
                        send_to.append(firm.manager)
                        for user in firm.users.all():
                            send_to.append(user)
                    if instance.approval_step.responsible_created_by:
                        send_to.append(instance.created_by)
                    if instance.approval_step.responsible_supervisor:
                        supervisor = User.objects.get(uuid=request_user.uuid).supervisor
                        send_to.append(supervisor)
                if action_step.destinatary == "notified":
                    send_to.append(instance.created_by)
                    send_to.append(request_user)
                    independent_todos = True

                # If there is responsibles, generate todos
                send_to = set(send_to)
                if len(send_to):
                    generate_todo(
                        company=instance.company,
                        responsibles=send_to,
                        action=action,
                        due_at=None,
                        is_done=False,
                        description=description,
                        url=url,
                        created_by=get_current_user(),
                        independent_todos=independent_todos,
                        resource=instance,
                    )
    except Exception as e:
        print(e)
        pass
    return instance
