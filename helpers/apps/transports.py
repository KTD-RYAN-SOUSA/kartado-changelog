import re

from rest_framework.response import Response

from apps.reportings.models import Reporting
from apps.services.models import Service
from helpers.apps.json_logic import apply_reporting_json_logic


def snake_case(name):
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def none_sum(*args):
    args = [a for a in args if a is not None]
    return sum(args) if args else None


class TransportsEndpoint:
    def __init__(self, measurement, pk):
        self.measurement = measurement
        self.pk = pk

        self.reportings = (
            Reporting.objects.filter(
                reporting_usage__in=measurement.measurement_usage.all()
            )
            .distinct()
            .select_related(
                "occurrence_type",
                "created_by",
                "status",
                "firm",
                "job",
                "parent",
                "road",
                "parent",
                "company",
            )
            .prefetch_related(
                "reporting_files",
                "children",
                "services",
                "reporting_usage__measurement__measurement_services",
                "reporting_usage__service",
            )
        )

        self.transport_services = Service.objects.filter(
            company=measurement.company,
            metadata__transportServices__isnull=False,
        )

        self.services = Service.objects.filter(company=measurement.company)

        self.transports = self.get_transports()

    def get_transports(self):
        transports = []
        for transport in self.transport_services:
            transports.insert(
                transport.metadata["order"],
                {"name": transport.name, "tasks": self.get_tasks(transport)},
            )

        return transports

    def get_tasks(self, transport):
        tasks = []
        for service_id, description in transport.metadata["transportServices"].items():
            service = self.get_service(service_id)
            if not service:
                continue
            materials = description["materials"]
            materials_dict = self.get_materials(materials, service)
            insert_flag = True
            for task in tasks:
                if task["code"] == service.code:
                    insert_flag &= False
                    for material in task["materials"]:
                        for item in material:
                            for obj_dict in materials_dict:
                                for obj in obj_dict:
                                    if item["name"] == obj["name"]:
                                        variables = [
                                            "amount",
                                            "moment",
                                            "density",
                                            "dmt",
                                        ]
                                        for var in variables:
                                            item[var] = none_sum(item[var], obj[var])

            if insert_flag:
                tasks.insert(
                    description["order"],
                    {
                        "code": service.code,
                        "name": service.name,
                        "materials": materials_dict,
                    },
                )
        return tasks

    def get_materials(self, materials, service):
        reportings = [
            a
            for a in self.reportings
            if service in [b.service for b in a.reporting_usage.all()]
        ]
        ret_materials = []
        for material in materials:
            amount = self.get_form_values(reportings, material["amount"])
            moment = self.get_form_values(reportings, material["moment"])
            density = self.get_form_values(
                reportings, material["density"], accumulate=False
            )
            dmt = self.get_form_values(reportings, material["dmt"], accumulate=False)
            try:
                dmt = moment / amount if dmt == "Var" else dmt
            except ZeroDivisionError:
                dmt = 0

            ret_materials.insert(
                material["order"],
                {
                    "name": material.get("name", ""),
                    "auxCode": material.get("aux_code", ""),
                    "unit": service.unit,
                    "amount": amount,
                    "moment": moment,
                    "density": density,
                    "dmt": dmt,
                },
            )
        return ret_materials

    def get_form_values(self, reportings, source, accumulate=True):
        result = 0 if accumulate else None
        for reporting in reportings:
            amount = 0
            if isinstance(source, str):
                field_name = source
            elif isinstance(source, list):
                if (
                    snake_case(source[0]) in reporting.form_data.keys()
                    and reporting.form_data[snake_case(source[0])]
                ):
                    field_name = source[2]
                else:
                    field_name = source[1]

            try:
                field = next(
                    a
                    for a in reporting.occurrence_type.form_fields["fields"]
                    if a["apiName"] == field_name
                )
            except StopIteration:
                continue
            if field["dataType"] == "jsonLogic":
                amount = apply_reporting_json_logic(reporting, field["logic"])
            elif field["dataType"] == "number" or field["dataType"] == "float":
                amount = reporting.form_data.get(snake_case(field["apiName"]), 0)

            if accumulate:
                result += amount
            else:
                if result is None or result == amount:
                    result = amount
                else:
                    result = "Var"

        if isinstance(result, float):
            result = round(result, 3)

        return result

    def get_usages(self, service_id):
        all_usages = self.measurement.measurement_usage.all()
        return [a for a in all_usages if a.pk == service_id]

    def get_service(self, service_id):
        try:
            return next(a for a in self.services if str(a.pk) == service_id)
        except (Exception, StopIteration):
            return None

    def get_response(self):
        return Response(
            {
                "type": "Transports",
                "id": self.pk,
                "attributes": {"transports": self.transports},
            }
        )
