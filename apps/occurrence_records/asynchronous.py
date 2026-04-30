import logging
from collections import defaultdict

from django.conf import settings
from django.utils import timezone

from apps.occurrence_records.models import OccurrenceRecord
from apps.users.models import UserNotification
from helpers.apps.users import add_unique_debounce_data
from helpers.strings import get_obj_from_path


def notify_overdue_validations():
    """
    Inject overdue validation notification for users with the proper
    UserNotification configuration.

    Does not group results of multiple Company instances.

    This function is called on a 1 minute rate by AWS SQS
    """

    NOTIFICATION_AREA = "auscultacao.leituras_ultrapassaram_prazo_de_validacao"

    user_notifs = UserNotification.objects.filter(
        notification=NOTIFICATION_AREA,
    )

    if user_notifs:
        user_notifs_companies = user_notifs.values_list("companies", flat=True)
        occ_records = OccurrenceRecord.objects.filter(
            validation_deadline__isnull=False,
            validated_at__isnull=True,
            validation_deadline__lte=timezone.now(),
            company__in=user_notifs_companies,
        )

        if occ_records:
            company_to_data = defaultdict(list)
            for occ_record in occ_records:
                form_data = occ_record.form_data

                instrument_id = form_data.get("instrument", None)
                instrument = (
                    OccurrenceRecord.objects.get(uuid=instrument_id)
                    if instrument_id
                    else None
                )

                reading_url = (
                    settings.FRONTEND_URL
                    + "/#/SharedLink/OccurrenceRecord/{}/show".format(occ_record.uuid)
                )

                company_name = instrument.company.name if instrument.company else None
                company_uuid = str(instrument.company.uuid)
                operational_position_value = instrument.form_data.get(
                    "operational_position", None
                )
                operational_position_field = next(
                    (
                        field
                        for field in get_obj_from_path(
                            instrument.occurrence_type.form_fields, "fields"
                        )
                        if field.get("apiName", None) == "operationalPosition"
                    ),
                    None,
                )
                operational_position = next(
                    option["name"]
                    for option in get_obj_from_path(
                        operational_position_field, "selectoptions__options"
                    )
                    if option["value"] == operational_position_value
                )
                occ_type_name = (
                    instrument.occurrence_type.name
                    if instrument.occurrence_type
                    else None
                )
                code = instrument.form_data.get("code", None)

                validation_deadline = (
                    occ_record.validation_deadline.strftime("%d/%m/%Y")
                    if occ_record.validation_deadline
                    else None
                )

                data_item = {
                    "occurrence_record_uuid": str(occ_record.uuid),
                    "company_name": company_name,
                    "operational_position": operational_position,
                    "instrument_type": occ_type_name,
                    "instrument_code": code,
                    "reading_url": reading_url,
                    "validation_deadline": validation_deadline,
                    "company_id": company_uuid,
                }

                company_to_data[company_uuid].append(data_item)

            add_unique_debounce_data(
                user_notifs,
                company_to_seri_item=company_to_data,
                dedup_key="occurrence_record_uuid",
            )
        else:
            logging.info(
                "No OccurrenceRecord has overdue validations for the current UserNotification instances"
            )
    else:
        logging.info("No UserNotification configured to receive overdue validations")
