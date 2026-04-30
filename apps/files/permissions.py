import uuid

from apps.constructions.models import Construction, ConstructionProgress
from apps.monitorings.models import MonitoringRecord, OperationalControl
from apps.occurrence_records.models import OccurrenceRecord
from helpers.permissions import BaseModelAccessPermissions


class FilePermissions(BaseModelAccessPermissions):
    model_name = "File"

    def get_company_id(self, action, request, obj=None):

        if action == "create":
            try:
                monitoring_record = MonitoringRecord.objects.get(
                    pk=uuid.UUID(request.data["content_object"]["id"])
                )
            except Exception:
                monitoring_record = False
                pass

            try:
                occurrence_record = OccurrenceRecord.objects.get(
                    pk=uuid.UUID(request.data["content_object"]["id"])
                )
            except Exception:
                occurrence_record = False
                pass

            try:
                op_control = OperationalControl.objects.get(
                    pk=uuid.UUID(request.data["content_object"]["id"])
                )
            except Exception:
                op_control = False

            try:
                construction = Construction.objects.get(
                    pk=uuid.UUID(request.data["content_object"]["id"])
                )
            except Exception:
                construction = False

            try:
                construction_progress = ConstructionProgress.objects.get(
                    pk=uuid.UUID(request.data["content_object"]["id"])
                )
            except Exception:
                construction_progress = False
                pass

            if monitoring_record:
                return monitoring_record.company_id
            elif occurrence_record:
                if not occurrence_record.editable:
                    return False
                return occurrence_record.company_id
            elif op_control:
                return op_control.firm.company_id
            elif construction:
                return construction.company_id
            elif construction_progress:
                return construction_progress.construction.company_id
            else:
                return False

        elif action in ["update", "partial_update", "destroy"]:
            model = obj.content_type.model_class()

            if model == OccurrenceRecord:
                if not obj.content_object.editable:
                    return False
                return obj.content_object.company_id
            elif model == OperationalControl:
                return obj.content_object.firm.company_id
            elif model == MonitoringRecord:
                return obj.content_object.company_id
            elif model == Construction:
                return obj.content_object.company_id
            elif model == ConstructionProgress:
                return obj.content_object.construction.company_id
            else:
                return False

        else:
            return super(FilePermissions, self).get_company_id(action, request, obj)

    def has_object_permission(self, request, view, obj):
        if view.action == "check":
            view.action = "retrieve"

        return super(FilePermissions, self).has_object_permission(request, view, obj)


class OccurrenceRecordFilePermissions(FilePermissions):
    model_name = "OccurrenceRecordFile"

    def has_object_permission(self, request, view, obj):
        if view.action == "check":
            view.action = "retrieve"

        return super(OccurrenceRecordFilePermissions, self).has_object_permission(
            request, view, obj
        )
