import json

from rest_framework.response import Response
from rest_framework_json_api.utils import format_field_names

from apps.companies.models import Firm

# Serializers
from apps.companies.serializers import CompanySerializer, FirmSerializer

# Models
from apps.occurrence_records.models import OccurrenceRecord
from apps.occurrence_records.serializers import (
    OccurrenceRecordObjectSerializer,
    OccurrenceRecordSerializer,
    OccurrenceTypeSerializer,
)
from apps.resources.models import Contract
from apps.resources.serializers import ContractSerializer
from apps.service_orders.models import (
    MeasurementBulletin,
    ProcedureResource,
    ServiceOrder,
    ServiceOrderAction,
    ServiceOrderResource,
)
from apps.service_orders.serializers import (
    AdministrativeInformationSerializer,
    MeasurementBulletinSerializer,
    ProcedureResourceSerializer,
    ServiceOrderActionSerializer,
    ServiceOrderResourceSerializer,
    ServiceOrderSerializer,
)
from apps.users.serializers import UserSerializer
from helpers.json_parser import JSONRenderer
from helpers.strings import get_xyz_from_point


class BaseObject(object):
    def __init__(self, initial_data):
        for key in initial_data:
            setattr(self, key, initial_data[key])


class PDFEndpoint:
    def __init__(self, obj, pk, request, model):
        self.obj = obj
        self.pk = pk
        self.request = request
        self.history = obj.history.all().order_by("-history_date")
        self.type = model

    def get_history(self, histories, discard_changes=[]):
        histories_list = []
        discard_changes_in = [
            "history",
            "history_id",
            "history_date",
            "updated_at",
            "history_change_reason",
            "history_type",
            "history_user",
            "firm",
            "created_by",
            "responsible",
        ] + discard_changes

        for i in range(len(histories) - 1):
            history = histories[i + 1]
            field_names = list(set(list(histories[0].keys())) - set(discard_changes_in))
            if history["history_type"] != "+":
                data = []
                for field in field_names:
                    old_value = histories[i][field]
                    new_value = history[field]
                    if old_value != new_value:
                        data.append(
                            {
                                "field_name": field,
                                "old_value": old_value,
                                "new_value": new_value,
                            }
                        )

                histories_list.insert(
                    i,
                    {
                        "id": history["history_id"],
                        "created_at": history["history_date"],
                        "created_by": history["history_user_id"],
                        "to_do": history["history_change_reason"],
                        "record_type": self.type,
                        "form_data": {"data": data, "type": "HistoryChange"},
                    },
                )
            else:
                histories_list.insert(
                    i,
                    {
                        "id": history["history_id"],
                        "created_at": history["history_date"],
                        "created_by": history["history_user_id"],
                        "to_do": history["history_change_reason"],
                        "record_type": self.type,
                        "form_data": {"type": self.type + "Created"},
                    },
                )

        return histories_list

    def get_point(self):
        if self.obj.point:
            point = get_xyz_from_point(self.obj.point)
        else:
            point = {"x": 0, "y": 0, "zone": None}
        return point

    def format(self, obj, format_type="camelize"):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, dict):
                    obj[key] = format_field_names(self.format(value), format_type)
                elif isinstance(value, list):
                    list_temp = value.copy()
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            list_temp[i] = format_field_names(
                                self.format(item), format_type
                            )
                        else:
                            list_temp[i] = item
                    obj[key] = list_temp

        return obj

    def format_to_front(self, obj):
        """
        remove the attributes key, flattening everything inside
        remove id and types keys in m2m relationships
        """
        if "attributes" in obj["data"]:
            attributes = obj["data"].pop("attributes")
            for key, value in attributes.items():
                obj["data"][key] = value

        if "relationships" in obj["data"]:
            for key, value in obj["data"]["relationships"].items():
                if "data" in value and isinstance(value["data"], list):
                    data = value.pop("data")
                    value["data"] = [item["id"] for item in data]
                    value["type"] = data[0]["type"] if data else ""

        return obj

    def format_to_json(self, obj_serialized, view):
        return self.format_to_front(
            json.loads(
                JSONRenderer().render(
                    obj_serialized,
                    renderer_context={"view": view, "request": self.request},
                )
            )
        )

    def get_response(self):
        """
        Need to import views from here because of recursion
        """
        from apps.companies.views import CompanyView, FirmView
        from apps.occurrence_records.views import (
            OccurrenceRecordView,
            OccurrenceTypeView,
        )
        from apps.resources.views import ContractView
        from apps.service_orders.views import (
            AdministrativeInformationView,
            MeasurementBulletinView,
            ProcedureResourceView,
            ServiceOrderActionView,
            ServiceOrderResourceView,
            ServiceOrderView,
        )
        from apps.users.views import UserViewSet

        record = None

        if type(self.obj) not in [
            ServiceOrderAction,
            Contract,
            MeasurementBulletin,
        ]:
            company_obj = self.obj.company

        creator_view = UserViewSet(serializer_class=UserSerializer)
        creator = self.format_to_json(
            UserSerializer(self.obj.created_by).data, creator_view
        )

        if isinstance(self.obj, OccurrenceRecord):
            record_view = OccurrenceRecordView(
                serializer_class=OccurrenceRecordObjectSerializer
            )
            record = self.format_to_json(
                OccurrenceRecordObjectSerializer(self.obj).data, record_view
            )
            point_utm = self.get_point()
            record["data"]["pointUTM"] = point_utm
            type_view = OccurrenceTypeView(serializer_class=OccurrenceTypeSerializer)
            record["data"]["occurrenceType"] = self.format_to_json(
                OccurrenceTypeSerializer(self.obj.occurrence_type).data,
                type_view,
            )["data"]

        administrative_informations = []
        if isinstance(self.obj, ServiceOrder):
            record_view = ServiceOrderView(serializer_class=ServiceOrderSerializer)
            record = self.format_to_json(
                ServiceOrderSerializer(self.obj).data, record_view
            )

            adm_objs = self.obj.administrative_informations.all()
            adm_view = AdministrativeInformationView(
                serializer_class=AdministrativeInformationSerializer
            )
            administrative_informations = self.format_to_json(
                AdministrativeInformationSerializer(adm_objs, many=True).data,
                adm_view,
            )

        procedure_resources = []
        if isinstance(self.obj, ServiceOrderAction):
            company_obj = self.obj.service_order.company

            record_view = ServiceOrderActionView(
                serializer_class=ServiceOrderActionSerializer
            )
            record = self.format_to_json(
                ServiceOrderActionSerializer(self.obj).data, record_view
            )

            procedures = self.obj.procedures.all()
            procedure_resource_objs = ProcedureResource.objects.filter(
                procedure__in=procedures
            )
            proc_resource_view = ProcedureResourceView(
                serializer_class=ProcedureResourceSerializer
            )
            procedure_resources = self.format_to_json(
                ProcedureResourceSerializer(procedure_resource_objs, many=True).data,
                proc_resource_view,
            )

        elif type(self.obj) == Contract:
            company_obj = self.obj.firm.company

            record_view = ContractView(serializer_class=ContractSerializer)
            record = self.format_to_json(ContractSerializer(self.obj).data, record_view)

            so_resources = self.obj.resources.all()
            procedure_resource_objs = ProcedureResource.objects.filter(
                service_order_resource__in=so_resources
            ).distinct()
            proc_resource_view = ProcedureResourceView(
                serializer_class=ProcedureResourceSerializer
            )
            procedure_resources = self.format_to_json(
                ProcedureResourceSerializer(procedure_resource_objs, many=True).data,
                proc_resource_view,
            )

        service_order_record = {}
        if type(self.obj) == ServiceOrder:
            occ_record = self.obj.so_records.first()
            occ_type = None
            occ_kind = "Não definido"
            if occ_record:
                occ_type = occ_record.occurrence_type.name
                occ_kind = occ_record.occurrence_type.occurrence_kind

            occ_record_view = OccurrenceRecordView(
                serializer_class=OccurrenceRecordSerializer
            )
            occ_record_json = self.format_to_json(
                OccurrenceRecordSerializer(occ_record).data, occ_record_view
            )

            service_order_record = {
                "occurrence_record": occ_record_json,
                "occurrence_type": occ_type,
                "occurrence_kind": occ_kind,
            }

        finisher = ""
        if type(self.obj) == ServiceOrder:
            closed_by = self.obj.closed_by
            if closed_by:
                finisher = closed_by.get_full_name()

        contracts = []
        if administrative_informations:
            contracts = [item.contract.pk for item in adm_objs if item.contract]

        service_order_resources = []
        if type(self.obj) == ServiceOrder:
            so_resources = ServiceOrderResource.objects.filter(
                contract_id__in=contracts
            ).distinct()

            so_resource_view = ServiceOrderResourceView(
                serializer_class=ServiceOrderResourceSerializer
            )
            service_order_resources = self.format_to_json(
                ServiceOrderResourceSerializer(so_resources, many=True).data,
                so_resource_view,
            )

        elif type(self.obj) == Contract:
            procedure_resources = []
            procedure_resources_filtered = procedure_resource_objs.filter(
                approval_status="DENIED_APPROVAL"
            )
            for item in procedure_resources_filtered:
                procedure_resources.append(
                    {
                        "amount": item.amount,
                        "unit": item.resource.unit if item.resource else "",
                        "resource": item.resource.name if item.resource else "",
                        "created_by": item.created_by.get_full_name(),
                        "created_at": item.creation_date.strftime("%d/%m/%Y"),
                        "total_price": item.total_price,
                        "unit_price": item.unit_price,
                    }
                )

        firm = {}
        firm_obj = None
        if type(self.obj) == MeasurementBulletin:
            company_obj = self.obj.contract.firm.company

            record_view = MeasurementBulletinView(
                serializer_class=MeasurementBulletinSerializer
            )
            record = self.format_to_json(
                MeasurementBulletinSerializer(self.obj).data, record_view
            )

            if self.obj.contract:
                firm_obj = self.obj.contract.firm
        elif type(self.obj) == Contract:
            firm_obj = self.obj.firm
        else:
            firms_id = self.obj.created_by.user_firms.values_list("pk", flat=True)
            firm_obj = Firm.objects.filter(pk__in=firms_id, company=company_obj).first()

        if firm_obj:
            firm_view = FirmView(serializer_class=FirmSerializer)
            firm = self.format_to_json(FirmSerializer(firm_obj).data, firm_view)

        measurement_bulletins = []
        if type(self.obj) == Contract:
            bulletins = self.obj.bulletins.all()
            for item in bulletins:
                accounting = ""
                if "accounting_classification" in item.extra_info.keys():
                    accounting = item.extra_info["accounting_classification"]
                measurement_bulletins.append(
                    {
                        "number": item.number,
                        "created_by": item.created_by.get_full_name(),
                        "measurement_date": item.measurement_date.strftime("%d/%m/%Y"),
                        "total_price": item.total_price,
                        "accounting_classification": accounting,
                    }
                )

        history = []
        if "history" in record.keys():
            history = self.get_history(histories=record["history"])

        company_view = CompanyView(serializer_class=CompanySerializer)
        company = self.format_to_json(CompanySerializer(company_obj).data, company_view)

        pdf_data = {
            "record": record["data"] if record else record,
            "creator": creator["data"] if creator else creator,
            "finisher": finisher["data"] if finisher else finisher,
            "company": company["data"] if company else company,
            "firm": firm["data"] if firm else firm,
            "history": history["data"] if history else history,
            "administrativeInformations": administrative_informations["data"]
            if administrative_informations
            else administrative_informations,
            "serviceOrderRecord": service_order_record["data"]
            if service_order_record
            else service_order_record,
            "serviceOrderResources": service_order_resources["data"]
            if service_order_resources
            else service_order_resources,
            "procedureResources": procedure_resources["data"]
            if procedure_resources
            else procedure_resources,
            "measurementBulletins": measurement_bulletins["data"]
            if measurement_bulletins
            else measurement_bulletins,
        }

        return Response(self.format(pdf_data))
