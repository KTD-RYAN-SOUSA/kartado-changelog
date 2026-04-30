from apps.companies.models import Company


def get_offender(occurrence_record) -> str:
    for involved in occurrence_record.involved_parts:
        if involved["involved_parts"] == "1":
            OFFENDER = involved["name"]
            return OFFENDER


def get_recipients(company: Company) -> list:
    recipients = []
    for user in company.get_judiciary_users():
        if user.email not in [x["email"] for x in recipients]:
            recipients.append({"name": user.full_name, "email": user.email})

    return recipients


def get_obra_sequencial_identificador(main_property: dict) -> tuple:
    """
        Pega os valores do main_property
    Args:
        main_property (dict): originalmente validado entre
        occurrence_record e shape_file_property

    Returns:
        tuple: (OBRA, SEQUENCIAL, IDENTIFICADOR)
    """
    OBRA = main_property["attributes"]["OBRA"]
    SEQUENCIAL = main_property["attributes"]["SEQUENCIAL"]
    IDENTIFICADOR = main_property["attributes"]["IDENTIFICADOR"]
    return (OBRA, SEQUENCIAL, IDENTIFICADOR)


def build_data_context(
    os_description: str,
    os_number: str,
    offender: str,
    identificador: str,
    sequencial: str,
    obra: str,
    process: str,
    service_order_action: str,
    recipients: list,
    sender: str = "",
    task_deadline: str = "",
    task_to_do: str = "",
) -> dict:
    data = dict(
        to_do=task_to_do,  # Descrição/nome da tarefa
        deadline=task_deadline,  # Prazo da tarefa que ta sendo criada
        recipients=recipients,
        service_order_action=service_order_action,  # Título da Entrega
        process=process,  # Processo
        construction=obra,  # Obra
        sequential=sequencial,  # Sequencial
        identifier=identificador,  # Identificador
        offender=offender,  # Infrator
        sender=sender,  # Emitente
        os_number=os_number,  # Número do Serviço
        os_description=os_description,  # Descrição da ordem de serviço
    )

    return data
