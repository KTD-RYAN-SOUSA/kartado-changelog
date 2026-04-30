import sentry_sdk
from django.db.models.signals import pre_save
from django.dispatch import receiver

from apps.constructions.models import Construction, ConstructionProgress
from apps.files.models import File
from apps.monitorings.models import MonitoringRecord, OperationalControl
from apps.occurrence_records.models import OccurrenceRecord


@receiver(pre_save, sender=File)
def auto_add_company_to_file_if_empty(sender, instance, **kwargs):
    if instance.company_id is None and instance.object_id:
        try:
            name_to_model = {
                "monitoringrecord": MonitoringRecord,
                "operationalcontrol": OperationalControl,  # firm.company_id
                "occurrencerecord": OccurrenceRecord,
                "construction": Construction,
                "constructionprogress": ConstructionProgress,  # construction.company_id
            }

            model_name = instance.content_type.model
            model = name_to_model.get(model_name, None)
            object_id = instance.object_id

            if model is not None:
                if model == OperationalControl:
                    company_field = "firm__company"
                elif model == ConstructionProgress:
                    company_field = "construction__company"
                else:
                    company_field = "company"

                company_id = (
                    model.objects.filter(uuid=object_id)
                    .values_list(company_field, flat=True)
                    .first()
                )

                instance.company_id = company_id
        except Exception as e:
            sentry_sdk.capture_exception(e)
