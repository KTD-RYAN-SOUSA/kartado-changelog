from apps.service_orders.helpers.email_judiciary.context_check_email_judiciary import (
    build_data_context,
    get_obra_sequencial_identificador,
    get_offender,
    get_recipients,
)
from apps.service_orders.models import ServiceOrderAction
from helpers.strings import keys_to_snake_case


def build_data_check_email_judiciary(
    service_order_action: ServiceOrderAction, request
) -> dict:
    service_order = service_order_action.service_order
    company = service_order.company

    PROCESS = service_order.get_process_type_display()
    os_number = service_order.number
    os_description = service_order.description
    service_order_action = service_order_action.name

    sender = request.user.full_name

    occurrence_record = service_order.get_main_occurrence_record()

    if not occurrence_record:
        return {"error": "kartado.error.occurrence_record.not_found"}

    recipients = get_recipients(company)

    main_property = service_order.get_main_property()

    OFFENDER = get_offender(occurrence_record)

    if not main_property:
        OBRA = SEQUENCIAL = IDENTIFICADOR = None
    else:
        OBRA, SEQUENCIAL, IDENTIFICADOR = get_obra_sequencial_identificador(
            main_property
        )

    task_to_do = ""
    task_deadline = ""
    try:
        GET = keys_to_snake_case(request.GET)
        task_to_do = GET.get("task_to_do", "")
        task_deadline = GET.get("task_deadline", "")
    except AttributeError:
        pass

    context = build_data_context(
        task_to_do=task_to_do,
        task_deadline=task_deadline,
        process=PROCESS,
        os_number=os_number,
        os_description=os_description,
        service_order_action=service_order_action,
        sender=sender,
        recipients=recipients,
        obra=OBRA,
        sequencial=SEQUENCIAL,
        identificador=IDENTIFICADOR,
        offender=OFFENDER,
    )

    return context
