import datetime
import logging

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import prefetch_related_objects
from zappa.asynchronous import task

from apps.service_orders.models import ProcedureResource, ServiceOrderResource
from apps.to_dos.models import ToDo, ToDoAction
from apps.to_dos.serializers import ToDoSerializer
from helpers.middlewares import get_current_user


@task
def handle_todos_procedure_resource(instance_uuid, created):
    try:
        instance = ProcedureResource.objects.get(uuid=instance_uuid)
        prefetch_related_objects(
            [instance], "service_order_resource", "service_order_resource__contract"
        )
        contract = instance.service_order_resource.contract
        prefetch_related_objects(
            [contract],
            "firm",
            "subcompany",
            "firm__company",
            "subcompany__company",
            "responsibles_hirer",
        )
        send_to = []
        description = {}
        if contract.firm:
            company = contract.firm.company
        elif contract.subcompany:
            company = contract.subcompany.company
        if created:
            todo_action = ToDoAction.objects.filter(
                default_options="resource", company_group=company.company_group
            ).first()
            if todo_action:
                if contract.responsibles_hirer.exists():
                    for user in contract.responsibles_hirer.all():
                        send_to.append(user)

        else:
            todo_action = ToDoAction.objects.filter(
                default_options="see", company_group=company.company_group
            ).first()
            if todo_action:
                if contract.responsibles_hired.exists():
                    for user in contract.responsibles_hired.all():
                        send_to.append(user)
                if instance.approval_status == "APPROVED_APPROVAL":
                    description["resource_status"] = "APPROVED_APPROVAL"
                elif instance.approval_status == "DENIED_APPROVAL":
                    description["resource_status"] = "DENIED_APPROVAL"
                else:
                    return
        send_to = set(send_to)
        if len(send_to):
            description["description"] = contract.name
            if contract.extra_info["r_c_number"]:
                description["contract"] = contract.extra_info["r_c_number"]
            description["resource"] = instance.resource.name
            description["amount"] = str(instance.amount) + " " + instance.resource.unit

            url = (
                "{}/#/SharedLink/Contract/{}/show/procedureResources?company={}".format(
                    settings.FRONTEND_URL, str(contract.uuid), str(company.uuid)
                )
            )
            generate_todo(
                company=company,
                responsibles=send_to,
                action=todo_action,
                due_at=None,
                is_done=False,
                description=description,
                url=url,
                created_by=get_current_user(),
                independent_todos=False,
                resource=instance,
            )
    except Exception as e:
        print(e)
        pass


@task
def handle_todos_service_order_resource(instance_uuid):
    try:
        instance = ServiceOrderResource.objects.get(uuid=instance_uuid)

        send_to = []
        description = {}

        contract = instance.contract
        company = (
            contract.firm.company if contract.firm else contract.subcompany.company
        )
        todo_action = ToDoAction.objects.filter(
            default_options="see", company_group=company.company_group
        ).first()
        if todo_action:
            if contract.responsibles_hirer.exists():
                for user in contract.responsibles_hirer.all():
                    send_to.append(user)
            if contract.responsibles_hired.exists():
                for user in contract.responsibles_hired.all():
                    send_to.append(user)
            description["description"] = contract.name
            if contract.extra_info["r_c_number"]:
                description["contract"] = contract.extra_info["r_c_number"]
            description["activity"] = "CONTRACT_EDITED_MESSAGE"

            url = "{}/#/SharedLink/Contract/{}/show?company={}".format(
                settings.FRONTEND_URL, str(contract.uuid), str(company.uuid)
            )
            send_to = set(send_to)
            if len(send_to):
                generate_todo(
                    company=company,
                    responsibles=send_to,
                    action=todo_action,
                    due_at=None,
                    is_done=False,
                    description=description,
                    url=url,
                    created_by=get_current_user(),
                    independent_todos=True,
                    resource=contract,
                )
    except Exception as e:
        print(e)
        pass


def generate_todo(
    company,
    responsibles,
    action,
    is_done=False,
    description={},
    url="",
    destination="",
    due_at=None,
    created_by=None,
    resource=None,
    destination_resource=None,
    independent_todos=True,
):
    """
    Generates a new ToDo instance according to the provided data.
    The extra argument `independent_todos` tells the function to create an
    instance for every responsible or not.

    This helper should reflect any changes made to the ToDo model.
    """

    # Remove creator from responsibles if "see" type ToDo
    filtered_responsibles = responsibles  # Default value
    if action.default_options == "see" and created_by:
        filtered_responsibles = [
            responsible
            for responsible in responsibles
            if responsible.pk != created_by.pk
        ]

    # Don't create ToDo instances if there are no responsibles
    if len(filtered_responsibles) > 0:
        # Basic data
        todo_data = {
            "due_at": due_at,
            "description": description,
            "is_done": is_done,
            "url": url,
            "destination": destination,
        }

        # Required relationships
        todo_data["company"] = {"type": "Company", "id": str(company.pk)}
        todo_data["action"] = {"type": "ToDoAction", "id": str(action.pk)}

        # Optional normal & generic relationships
        if created_by:
            todo_data["created_by"] = {"type": "User", "id": str(created_by.pk)}

        if resource:
            # Get class name in lowercase
            resource_model_name = resource.__class__.__name__.lower()
            content_type = ContentType.objects.filter(model=resource_model_name).first()

            if content_type:
                todo_data.update(
                    {
                        "resource_type": {
                            "type": "ContentType",
                            "id": str(content_type.pk),
                        },
                        "resource_obj_id": str(resource.pk),
                    }
                )
                # Implement debounce when resource exists

                # If any todo already exists for this case, interrupt creation
                if action.default_options == "see":
                    now = datetime.datetime.now()
                    debounce_time = now - datetime.timedelta(hours=12)
                    # We need to pay attention here!!!
                    # It will only works when the todo has only one responsible
                    todos = ToDo.objects.filter(
                        created_at__gte=debounce_time,
                        responsibles__in=filtered_responsibles,
                        resource_obj_id=resource.pk,
                        resource_type__pk=content_type.pk,
                    )
                    if todos.count() > 0:
                        return

                # If any todo exists for this case and is not done, just update it
                if action.default_options == "resource":
                    procedure_resources = ProcedureResource.objects.filter(
                        service_order_resource=resource.service_order_resource
                    )
                    procedure_resources = [a.pk for a in procedure_resources.all()]
                    todos = ToDo.objects.filter(
                        is_done=False,
                        resource_obj_id__in=procedure_resources,
                        resource_type__pk=content_type.pk,
                    )
                    if todos.count() > 0:
                        old_todo = todos.first()
                        amount = description["amount"].split(" ")[0]
                        old_amount = old_todo.description["amount"].split(" ")[0]
                        new_amount = float(amount) + float(old_amount)
                        description["amount"] = (
                            str(new_amount) + " " + description["amount"].split(" ")[1]
                        )
                        old_todo.description = description
                        # Might be good update responsibles for this todo in the future
                        old_todo.save()
                        return

        if destination_resource:
            # Get class name in lowercase
            destination_resource_model_name = (
                destination_resource.__class__.__name__.lower()
            )

            content_type = ContentType.objects.filter(
                model=destination_resource_model_name
            ).first()

            if content_type:
                todo_data.update(
                    {
                        "destination_resource_type": {
                            "type": "ContentType",
                            "id": str(content_type.pk),
                        },
                        "destination_resource_obj_id": str(destination_resource.pk),
                    }
                )

        # Handle responsibles & save
        if independent_todos:
            for responsible in filtered_responsibles:
                todo_data["responsibles"] = [
                    {"type": "User", "id": str(responsible.pk)}
                ]

                serializer = ToDoSerializer(data=todo_data)
                if serializer.is_valid(raise_exception=True):
                    serializer.save()
        else:
            todo_data["responsibles"] = []
            for responsible in filtered_responsibles:
                todo_data["responsibles"].append(
                    {"type": "User", "id": str(responsible.pk)}
                )

            serializer = ToDoSerializer(data=todo_data)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
    else:
        logging.warning(
            "generate_todo: Attempted to create ToDo instances but didn't provide responsibles (creator doesn't count)"
        )


def field_has_changed(changed_fields, field_name):
    old_value, new_value = next(
        (
            (old, new)
            for field, (old, new) in changed_fields.items()
            if field == field_name
        ),
        (None, None),
    )
    return old_value and new_value and old_value != new_value


def mark_to_dos_as_read(instance):
    content_type = ContentType.objects.get_for_model(instance._meta.model)
    to_do_objs = ToDo.objects.filter(
        resource_obj_id=str(instance.pk),
        resource_type__pk=str(content_type.pk),
        is_done=False,
    )
    to_do_objs.update(is_done=True)
