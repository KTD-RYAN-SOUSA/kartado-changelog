from collections import Counter
from datetime import timedelta

import pytz
from dateutil import parser
from django.db.models import Case, IntegerField, When
from django.db.models.functions import Cast, Least
from django.utils import timezone
from fnc.mappings import get

from apps.companies.models import Company
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import Reporting
from helpers.apps.dashboard_reporting import ReportingCountRoad
from helpers.apps.json_logic import apply_json_logic
from helpers.dates import get_first_and_last_day_of_month, utc_to_local
from helpers.error_messages import error_message
from helpers.filters import Floor, KeyFilter
from helpers.strings import get_obj_from_path


def get_csp_class(csp_number):
    if csp_number == "3.1":
        return Csp31Endpoint
    return CspEndpoint


def get_csp_graph_class(csp_number):
    if csp_number == "3.1":
        return Csp31GraphEndpoint
    return CspGraphEndpoint


class CspBase:
    def __init__(self, params):
        self.inspected_fixed = False
        self.year = int(params.get("csp_year", timezone.now().year))
        self.company_id = params.get("company", "")
        self.csp_number = params.get("csp_number", "")
        self.csp_type = params.get("csp_type", "")
        self.system = params.get("csp_system", "")
        created_by_param = params.get("created_by", "")
        self.created_by = (
            created_by_param.split(",") if created_by_param else created_by_param
        )
        lots_param = params.get("lot", "")
        self.lots = lots_param.split(",") if lots_param else lots_param
        self.csp_total_dict = {}
        self.translate_quarter = {
            1: [1, 2, 3],
            2: [4, 5, 6],
            3: [7, 8, 9],
            4: [10, 11, 12],
        }

    def get_count_inventory(self, value):
        return get(value, self.inventory, default=0)

    def get_inspected(self, infos, value):
        if self.inspected_fixed:
            inspected = self.get_count_inventory(value)
        else:
            inspected = sum([item["segments"] for item in infos])
        return inspected

    def get_not_conforming(self, objs):
        not_conforming = sum([item["not_conforming"] for item in objs])
        return not_conforming

    def get_perc(self, not_conforming, inspected):
        # Usar o numero de nao conformidades para calcular o numero de conformidades
        # e dividir pelo numero de segmentos fiscalizados e multiplicar isso tudo por cem
        conforming = inspected - not_conforming
        value_perc = (conforming / inspected if inspected else 0) * 100
        value_frac = "{}/{}".format(conforming, inspected)
        return value_perc, value_frac

    def get_not_conform_calc(self, reportings, indicator):
        # Numero de nao conformidades por segmento (km)
        kms = dict(Counter([item["initial_km"] for item in reportings]))

        # Usar o scoring logic para calcular o numero real de nao conformidades
        nb_not_conf = 0
        scoring = indicator["scoring"]
        for km, nb_reportings in kms.items():
            nb_not_conf += apply_json_logic(scoring, {"conf": nb_reportings})
        return nb_not_conf

    def get_summary(self, indicators_period, grades):
        lots_final = []
        lots_dict = {}

        for topic, value in indicators_period.items():
            if isinstance(value, list):
                for lot in value:
                    lot_name = lot["name"]
                    if lot_name not in lots_dict:
                        lots_dict[lot_name] = {
                            "id": lot["id"],
                            "topics": {topic: lot["final_part"]},
                            "roads": {},
                        }
                    else:
                        lots_dict[lot_name]["topics"][topic] = lot["final_part"]

                    for road in lot["roads"]:
                        road_name = road["name"]
                        roads = lots_dict[lot_name]["roads"]
                        if road_name not in roads:
                            roads[road_name] = {"topics": {topic: road["final_part"]}}
                        else:
                            roads[road_name]["topics"][topic] = road["final_part"]

        for lot_name, lot_data in lots_dict.items():
            roads_temp = []
            for road_name, road_data in lot_data["roads"].items():
                remaining_road_topics = {
                    key: value
                    for key, value in grades.items()
                    if key not in road_data["topics"]
                }
                road_grades = {**road_data["topics"], **remaining_road_topics}
                csp_road_total = round(sum(road_grades.values()) * 100, 2)
                roads_temp.append({"name": road_name, "csp_total": csp_road_total})

            remaining_lot_topics = {
                key: value
                for key, value in grades.items()
                if key not in lot_data["topics"]
            }
            lot_grades = {**lot_data["topics"], **remaining_lot_topics}
            csp_lot_total = round(sum(lot_grades.values()) * 100, 2)

            lots_final.append(
                {
                    "name": lot_name,
                    "id": lot_data["id"],
                    "csp_total": csp_lot_total,
                    "roads": roads_temp,
                }
            )

        return lots_final

    def get_result_by_period(self, all_information, period):
        if period == "month":
            informations = {
                "{}/{}".format(str(i), self.year): list(
                    filter(lambda x: x["month"] == i, all_information)
                )
                for i in range(1, 13, 1)
            }
        elif period == "quarter":
            # This is not being used
            informations = {
                "{}/{}".format(str(i), self.year): list(
                    filter(
                        lambda x: x["month"] in self.translate_quarter[i],
                        all_information,
                    )
                )
                for i in range(1, 5, 1)
            }
        else:
            return {}

        result = {}
        all_topics = list(self.rules.keys())
        for period_name, values in informations.items():
            indicators = []
            indicators_period = {}
            grades = {}
            for topic in all_topics:
                lots = []
                lots_period = []
                indicator_dict = self.rules[topic]
                weight = indicator_dict["weight"]
                original_name = indicator_dict["name"]
                info_by_topic = list(
                    filter(lambda x: x["inspection_topic"] == topic, values)
                )
                all_lots = list(set([item["lot"] for item in info_by_topic]))
                for lot in all_lots:
                    roads = []
                    roads_period = []
                    lot_name = self.lots_translation.get(lot, "Sem Lote")
                    info_by_lot = list(filter(lambda x: x["lot"] == lot, info_by_topic))
                    all_roads = list(set([item["road_name"] for item in info_by_lot]))
                    for road in all_roads:
                        info_by_road = list(
                            filter(lambda x: x["road_name"] == road, info_by_lot)
                        )
                        reportings_by_road = [
                            a for item in info_by_road for a in item["reportings"]
                        ]
                        not_conforming_road = self.get_not_conform_calc(
                            reportings_by_road, indicator_dict
                        )
                        inspected_road = self.get_inspected(
                            info_by_road, "{}:{}".format(lot_name, road)
                        )
                        value_perc_road, value_frac_road = self.get_perc(
                            not_conforming_road, inspected_road
                        )
                        road_summary = {
                            "name": road,
                            "inspected": inspected_road,
                            "not_conforming": not_conforming_road,
                        }
                        roads.append(
                            {
                                **road_summary,
                                "value_perc": value_perc_road,
                                "value_frac": value_frac_road,
                            }
                        )
                        grade_road = (
                            self.get_csp_calc(value_perc_road, indicator_dict)
                            if info_by_road
                            else 1
                        )
                        roads_period.append(
                            {**road_summary, "final_part": grade_road * weight}
                        )

                    not_conforming_lot = self.get_not_conforming(roads)
                    inspected_lot = self.get_inspected(info_by_lot, lot_name)
                    value_perc_lot, value_frac_lot = self.get_perc(
                        not_conforming_lot, inspected_lot
                    )

                    lot_summary = {
                        "name": lot_name,
                        "id": lot,
                        "inspected": inspected_lot,
                        "not_conforming": not_conforming_lot,
                    }

                    lots.append(
                        {
                            **lot_summary,
                            "value_perc": value_perc_lot,
                            "value_frac": value_frac_lot,
                            "roads": roads,
                        }
                    )
                    grade_lot = (
                        self.get_csp_calc(value_perc_lot, indicator_dict)
                        if info_by_lot
                        else 1
                    )
                    lots_period.append(
                        {
                            **lot_summary,
                            "final_part": grade_lot * weight,
                            "roads": roads_period,
                        }
                    )

                not_conforming_topic = self.get_not_conforming(lots)

                inspected_topic = self.get_inspected(info_by_topic, "total")
                value_perc_topic, value_frac_topic = self.get_perc(
                    not_conforming_topic, inspected_topic
                )
                grade = (
                    self.get_csp_calc(value_perc_topic, indicator_dict)
                    if info_by_topic
                    else 1
                )

                indicators.append(
                    {
                        "name": topic,
                        "original_name": original_name,
                        "inspected": inspected_topic,
                        "not_conforming": not_conforming_topic,
                        "value_perc": value_perc_topic,
                        "value_frac": value_frac_topic,
                        "grade": grade,
                        "weight": weight,
                        "final_part": grade * weight,
                        "lots": lots,
                    }
                )
                indicators_period[topic] = lots_period
                grades[topic] = weight

            period_int = int(period_name.split("/")[0])

            if period == "month":
                csp_total = round(
                    sum([item["final_part"] for item in indicators]) * 100, 2
                )
                self.csp_total_dict[period_int] = csp_total
            elif period == "quarter":
                months = self.translate_quarter[period_int]
                sum_csp_total = sum(
                    [
                        value
                        for key, value in self.csp_total_dict.items()
                        if key in months
                    ]
                )
                csp_total = round(sum_csp_total / 3, 2)
            else:
                csp_total = 100

            result[period_name] = {
                "csp_total": csp_total,
                "indicators": indicators,
                "lots": self.get_summary(indicators_period, grades),
            }

        return result

    def get_result_by_quarter(self):
        result = {}

        for i in range(1, 5, 1):
            period_name = "{}/{}".format(str(i), self.year)
            months = self.translate_quarter[i]
            sum_csp_total = sum(
                [value for key, value in self.csp_total_dict.items() if key in months]
            )
            csp_total = round(sum_csp_total / 3, 2)

            result[period_name] = {
                "csp_total": csp_total,
                "indicators": [],
                "lots": [],
            }

        return result

    def get_result_by_year(self):
        csp_total = sum(list(self.csp_total_dict.values()))
        return {str(self.year): {"csp_total": round(csp_total / 12, 2)}}

    def has_csp_data_in_company(self):
        # Verify if company metadata has everything for the calculation
        fields = ["name", "weight", "performance", "scoring", "types"]

        try:
            csp_data = self.company.metadata["csp"]["topics"][self.csp_number]
            self.rules = csp_data["rules"]
            self.csp_name = csp_data["name"]
            self.type_ids = csp_data.get("type_ids", [])
        except Exception:
            return False

        # Get all_types to filter reportings
        all_types = []
        for value in self.rules.values():
            if set(fields).issubset(value):
                all_types += value["types"]
            else:
                return False

        self.all_types = all_types
        return True

    def get_filters_reportings(self):
        filters = {}
        exclude = {}

        filters["company"] = self.company
        filters["found_at__year"] = self.year
        if self.all_types:
            filters["occurrence_type_id__in"] = self.all_types
        if self.all_roads:
            filters["road_name__in"] = self.all_roads
        if self.all_created_by:
            filters["created_by_id__in"] = self.all_created_by
        if self.lots:
            filters["lot__in"] = self.lots
        if self.csp_type == "2":
            filters["form_data__artesp_code__isnull"] = False
            exclude["form_data__artesp_code__exact"] = ""

        return filters, exclude

    def get_filters_inspection_reportings(self):
        filters = {}

        inspect_types = get_obj_from_path(self.company.metadata, "csp__inspect_types")

        filters["company"] = self.company
        filters["found_at__year"] = self.year
        filters["occurrence_type_id__in"] = inspect_types
        filters["form_data__executed_by"] = self.csp_type
        if self.created_by:
            filters["created_by_id__in"] = self.created_by
        if self.lots:
            filters["form_data__lots__has_any_keys"] = self.lots
        if self.system:
            filters["form_data__road_system"] = self.system

        return filters

    def get_csp_calc(self, value_perc, indicator):
        # Usar a performance para calcular a nota final de cada indicador
        performance = indicator["performance"]
        grade = apply_json_logic(performance, {"perf": value_perc})
        return grade

    def get_basic_data(self):
        if not self.company_id or not self.csp_number or not self.csp_type:
            return False

        # Get company and its data related to CSP
        try:
            self.company = Company.objects.get(pk=self.company_id)
        except Exception:
            return False
        possible_path_lots = "reporting__fields__lot__selectoptions__options"
        lots = get_obj_from_path(self.company.custom_options, possible_path_lots)
        self.lots_translation = {item["value"]: item["name"] for item in lots}
        can_calculate = self.has_csp_data_in_company()
        return can_calculate

    def get_inspection_reportings_qs(self, filters):
        self.inspection_reportings_qs = Reporting.objects.filter(**filters).only(
            "form_data", "found_at", "road_name", "created_by_id"
        )
        return

    def get_inspection_reportings(self):
        self.inspection_reportings = [
            {
                "form_data": item.form_data,
                "road_name": item.road_name or "Sem Rodovia",
                "found_at": utc_to_local(item.found_at),
                "created_by": str(item.created_by_id),
            }
            for item in self.inspection_reportings_qs
        ]

        if self.csp_number != "8.1":
            self.all_roads = list(
                set(
                    [
                        item["road_name"]
                        for item in self.inspection_reportings
                        if item["road_name"]
                    ]
                )
            )

        self.all_created_by = list(
            set(
                [
                    item["created_by"]
                    for item in self.inspection_reportings
                    if item["created_by"]
                ]
            )
        )
        return

    def get_reportings_qs(self, filters, exclude={}):
        self.reportings_qs = (
            Reporting.objects.filter(**filters)
            .exclude(**exclude)
            .only(
                "uuid",
                "lot",
                "km",
                "road_name",
                "occurrence_type_id",
                "found_at",
                "created_by_id",
            )
        )
        return

    def get_reportings(self):
        self.reportings = [
            {
                "uuid": str(item.uuid),
                "lot": item.lot,
                "initial_km": int(item.km),
                "road_name": item.road_name or "Sem Rodovia",
                "occurrence_type": str(item.occurrence_type_id),
                "created_by": str(item.created_by_id),
                "found_at": utc_to_local(item.found_at),
            }
            for item in self.reportings_qs
        ]
        return

    def get_filters_inventory(self):
        filters = {}
        filters["company"] = self.company
        # filters["found_at__year"] = self.year
        filters["occurrence_type__occurrence_kind"] = "2"
        filters["occurrence_type_id__in"] = self.type_ids
        # if self.all_roads:
        #     filters["road_name__in"] = self.all_roads
        if self.lots:
            filters["lot__in"] = self.lots
        return filters

    def get_inventory_qs(self, filters):
        self.inventory_qs = Reporting.objects.filter(**filters).only(
            "uuid", "lot", "road_name"
        )
        return

    def get_inventory(self):
        total = 0
        self.inventory = {}
        inventories = [
            {
                "uuid": str(item.uuid),
                "lot": item.lot,
                "road_name": item.road_name or "Sem Rodovia",
            }
            for item in self.inventory_qs
        ]

        if self.csp_number == "8.1":
            self.all_roads = list(
                set([item["road_name"] for item in inventories if item["road_name"]])
            )

        all_lots = list(set([item["lot"] for item in inventories]))
        self.all_lots = all_lots

        for lot in all_lots:
            lot_name = self.lots_translation.get(lot, "Sem Lote")
            inventory_by_lot = list(filter(lambda x: x["lot"] == lot, inventories))
            all_roads = list(set([item["road_name"] for item in inventory_by_lot]))
            for road_name in all_roads:
                road_count = len(
                    list(
                        filter(
                            lambda x: x["road_name"] == road_name,
                            inventory_by_lot,
                        )
                    )
                )
                lot_and_road = "{}:{}".format(lot_name, road_name)
                self.inventory[lot_and_road] = road_count

            lot_count = len(inventory_by_lot)
            total += lot_count
            self.inventory[lot_name] = lot_count
        self.inventory["total"] = total

        return


class CspEndpoint(CspBase):
    def get_inspected_information(self, inspection, inspection_lots):
        all_information = []
        if self.lots:
            inspection_lots = {
                key: value for key, value in inspection_lots.items() if key in self.lots
            }
        if not inspection_lots:
            return all_information

        for lot, values in inspection_lots.items():
            lot_topics = values.get("topics", {})
            kms = values.get("kms", [])
            for topic, count in lot_topics.items():
                if topic not in self.rules:
                    continue
                occ_types = self.rules[topic]["types"]

                reportings_filtered = [
                    reporting
                    for reporting in self.reportings
                    if (reporting["occurrence_type"] in occ_types)
                    and (reporting["found_at"].month == inspection["found_at"].month)
                    and (reporting["found_at"].year == inspection["found_at"].year)
                    and (reporting["found_at"].day == inspection["found_at"].day)
                    and (reporting["created_by"] == inspection["created_by"])
                    and (reporting["road_name"] == inspection["road_name"])
                    and (reporting["lot"] == lot)
                    and (reporting["initial_km"] in kms)
                ]

                new_count = count if not self.inspected_fixed else 0

                all_information.append(
                    {
                        "inspection_topic": topic,
                        "lot": lot,
                        "road_name": inspection["road_name"],
                        "segments": new_count,
                        "month": inspection["found_at"].month,
                        "reportings": reportings_filtered,
                    }
                )
        return all_information

    def get_inventory_information(self):
        all_information = []
        inventory_code = next(iter(self.rules.keys()))

        for reporting in self.reportings:

            all_information.append(
                {
                    "inspection_topic": inventory_code,
                    "lot": reporting["lot"],
                    "road_name": reporting["road_name"],
                    "segments": 0,
                    "month": reporting["found_at"].month,
                    "reportings": [reporting],
                }
            )
        return all_information

    def get_data(self):
        can_calculate = self.get_basic_data()
        if not can_calculate:
            return {}

        # Get inspection reportings
        inspection_filters = self.get_filters_inspection_reportings()
        self.get_inspection_reportings_qs(inspection_filters)
        self.get_inspection_reportings()
        if not self.inspection_reportings:
            return {}

        # Get inventory count for 8.1
        if self.csp_number == "8.1":
            self.inspected_fixed = True
            inventory_filters = self.get_filters_inventory()
            self.get_inventory_qs(inventory_filters)
            self.get_inventory()
            if not self.inventory:
                return {}

        # Get reportings
        filters, exclude = self.get_filters_reportings()
        self.get_reportings_qs(filters, exclude)
        self.get_reportings()
        if not self.reportings:
            return {}

        # Iterate on each inspection reporting
        all_information = []

        if self.csp_number != "8.1":
            for inspection in self.inspection_reportings:
                inspection_lots = inspection["form_data"].get("lots", {})
                all_information += self.get_inspected_information(
                    inspection, inspection_lots
                )
        else:
            all_information = self.get_inventory_information()

        result_by_month = self.get_result_by_period(all_information, period="month")
        result_by_quarter = self.get_result_by_quarter()
        result_by_year = self.get_result_by_year()

        return {
            "indicator": self.csp_number,
            "name": self.csp_name,
            "year": result_by_year,
            "quarter": result_by_quarter,
            "month": result_by_month,
        }


class Csp31Endpoint(CspBase):
    def get_perc(self, not_conforming, inspected):
        value_perc = (not_conforming / inspected if inspected else 0) * 100
        value_frac = "{}/{}".format(not_conforming, inspected)
        return value_perc, value_frac

    def get_denominator(self, reportings, first_day, last_day):
        date_str = "artesp_date" if self.is_artesp else "executed_at"
        denominator = 0
        last_day_last_month = first_day - timedelta(seconds=1)
        first_day_last_month = (first_day - timedelta(days=1)).replace(day=1)
        for reporting in reportings:
            # Special case for cobertura vegetal
            # Se foi executado e data do formulário está preenchida, em meses
            # após a data de aprovação artesp, para de contabilizar aquele apontamento
            if (
                reporting["occurrence_type_id"] in self.special_type
                and reporting["executed_at"]
                and reporting["artesp_date"]
                and first_day >= reporting["artesp_date"]
            ):
                continue
            if (
                (
                    # Prazo esteja nesse mês
                    reporting["due_at"]
                    and reporting["due_at"] >= first_day
                    and reporting["due_at"] <= last_day
                )
                or (
                    # Vencidos em meses anteriores e ainda não executados
                    reporting["due_at"]
                    and reporting["due_at"] <= first_day
                    and not reporting[date_str]
                )
                or (
                    # Foram executados com atraso no mês anterior
                    reporting["due_at"]
                    and reporting["due_at"] >= first_day_last_month
                    and reporting["due_at"] <= last_day_last_month
                    and reporting[date_str] >= reporting["due_at"]
                )
                or (
                    # Special case for cobertura vegetal
                    # Se foi executado, e a data do formulário ainda está vazia, em meses
                    # a partir do mês da execução, contabilizar no numerador e denominador
                    reporting["occurrence_type_id"] in self.special_type
                    and reporting["executed_at"]
                    and not reporting["artesp_date"]
                    and last_day >= reporting["executed_at"]
                )
            ):
                denominator += 1
        return denominator

    def get_numerator(self, reportings, first_day, last_day):
        date_str = "artesp_date" if self.is_artesp else "executed_at"
        reportings_list = []
        numerator = 0
        for reporting in reportings:
            # Special case for cobertura vegetal
            # Se foi executado e data do formulário está preenchida, em meses
            # após a data de aprovação artesp, para de contabilizar aquele apontamento
            if (
                reporting["occurrence_type_id"] in self.special_type
                and reporting["executed_at"]
                and reporting["artesp_date"]
                and first_day >= reporting["artesp_date"]
            ):
                continue
            if (
                (
                    # Prazo esteja nesse mês e foi executado antes do fim do mês
                    reporting["due_at"]
                    and reporting[date_str]
                    and reporting[date_str] <= last_day
                    and reporting["due_at"] >= first_day
                    and reporting["due_at"] <= last_day
                )
                or (
                    # Prazo esteja em meses anteriores e foi executado nesse mês
                    reporting["due_at"]
                    and reporting[date_str]
                    and reporting[date_str] >= first_day
                    and reporting[date_str] <= last_day
                    and reporting["due_at"] <= first_day
                )
                or (
                    # Special case for cobertura vegetal
                    # Se foi executado, e a data do formulário ainda está vazia, em meses
                    # a partir do mês da execução, contabilizar no numerador e denominador
                    reporting["occurrence_type_id"] in self.special_type
                    and reporting["executed_at"]
                    and not reporting["artesp_date"]
                    and last_day >= reporting["executed_at"]
                )
            ):
                numerator += 1
                reportings_list.append(reporting["uuid"])
        return numerator, reportings_list

    def get_result_by_month(self):
        all_lots = list(set([item["lot"] for item in self.reportings]))
        all_topics = list(self.rules.keys())
        result = {}
        for i in range(1, 13, 1):
            first_day, last_day = get_first_and_last_day_of_month(i, self.year)
            indicators = []
            indicators_period = {}
            grades = {}
            for topic in all_topics:
                lots = []
                lots_period = []
                indicator_dict = self.rules[topic]
                weight = indicator_dict["weight"]
                original_name = indicator_dict["name"]
                for lot in all_lots:
                    roads = []
                    roads_period = []
                    reportings_by_lot = list(
                        filter(lambda x: x["lot"] == lot, self.reportings)
                    )
                    numerator_lot, reportings_list_lot = self.get_numerator(
                        reportings_by_lot, first_day, last_day
                    )
                    denominator_lot = self.get_denominator(
                        reportings_by_lot, first_day, last_day
                    )
                    if denominator_lot:
                        all_roads = list(
                            set([item["road_name"] for item in reportings_by_lot])
                        )
                        for road in all_roads:
                            reportings_by_road = list(
                                filter(
                                    lambda x: x["road_name"] == road,
                                    reportings_by_lot,
                                )
                            )
                            (numerator_road, reportings_list,) = self.get_numerator(
                                reportings_by_road, first_day, last_day
                            )
                            denominator_road = self.get_denominator(
                                reportings_by_road, first_day, last_day
                            )
                            if denominator_road:
                                (
                                    value_perc_road,
                                    value_frac_road,
                                ) = self.get_perc(numerator_road, denominator_road)
                                road_summary = {
                                    "name": road,
                                    "inspected": denominator_road,
                                    "not_conforming": numerator_road,
                                    "reportings": reportings_list,
                                }
                                roads.append(
                                    {
                                        **road_summary,
                                        "value_perc": value_perc_road,
                                        "value_frac": value_frac_road,
                                    }
                                )
                                grade_road = (
                                    self.get_csp_calc(value_perc_road, indicator_dict)
                                    if reportings_by_road
                                    else 1
                                )
                                roads_period.append(
                                    {
                                        **road_summary,
                                        "final_part": grade_road * weight,
                                    }
                                )

                        value_perc_lot, value_frac_lot = self.get_perc(
                            numerator_lot, denominator_lot
                        )

                        lot_summary = {
                            "name": self.lots_translation.get(lot, "Sem Lote"),
                            "id": lot,
                            "inspected": denominator_lot,
                            "not_conforming": numerator_lot,
                        }

                        lots.append(
                            {
                                **lot_summary,
                                "value_perc": value_perc_lot,
                                "value_frac": value_frac_lot,
                                "roads": roads,
                            }
                        )
                        grade_lot = (
                            self.get_csp_calc(value_perc_lot, indicator_dict)
                            if reportings_by_lot
                            else 1
                        )
                        lots_period.append(
                            {
                                **lot_summary,
                                "final_part": grade_lot * weight,
                                "roads": roads_period,
                            }
                        )

                numerator_topic, _ = self.get_numerator(
                    self.reportings, first_day, last_day
                )
                denominator_topic = self.get_denominator(
                    self.reportings, first_day, last_day
                )
                value_perc_topic, value_frac_topic = self.get_perc(
                    numerator_topic, denominator_topic
                )
                grade = (
                    self.get_csp_calc(value_perc_topic, indicator_dict)
                    if self.reportings
                    else 1
                )

                indicators.append(
                    {
                        "name": topic,
                        "original_name": original_name,
                        "inspected": denominator_topic,
                        "not_conforming": numerator_topic,
                        "value_perc": value_perc_topic,
                        "value_frac": value_frac_topic,
                        "grade": grade,
                        "weight": weight,
                        "final_part": grade * weight,
                        "lots": lots,
                    }
                )
                indicators_period[topic] = lots_period
                grades[topic] = weight

            period_name = "{}/{}".format(str(i), self.year)

            period_int = int(period_name.split("/")[0])

            csp_total = round(sum([item["final_part"] for item in indicators]) * 100, 2)
            self.csp_total_dict[period_int] = csp_total

            result[period_name] = {
                "csp_total": csp_total,
                "indicators": indicators,
                "lots": self.get_summary(indicators_period, grades),
            }

        return result

    def get_filters_reportings(self):
        filters = {}
        exclude = {}
        filters["company"] = self.company
        if self.all_types:
            filters["occurrence_type_id__in"] = self.all_types
        if self.created_by:
            filters["created_by_id__in"] = self.created_by
        if self.lots:
            filters["lot__in"] = self.lots

        try:
            inspect_types = get_obj_from_path(
                self.company.metadata, "csp__inspect_types"
            )
            fields = OccurrenceType.objects.filter(pk__in=inspect_types)[0].form_fields[
                "fields"
            ]
            executed_by = list(filter(lambda x: x["apiName"] == "executedBy", fields))[
                0
            ]
            options = get_obj_from_path(executed_by, "select_options__options")
            options_values = {item["value"]: item["name"] for item in options}
            self.is_artesp = options_values[self.csp_type].lower() == "artesp"
        except Exception:
            self.is_artesp = False

        if self.is_artesp:
            filters["form_data__artesp_code__isnull"] = False
            exclude["form_data__artesp_code__exact"] = ""
        else:
            filters["form_data__artesp_code__isnull"] = True

        return filters, exclude

    def get_reportings_qs(self, filters, exclude={}):
        self.reportings_qs = (
            Reporting.objects.filter(**filters)
            .exclude(**exclude)
            .filter(due_at__isnull=False)
            .only(
                "uuid",
                "lot",
                "road_name",
                "due_at",
                "executed_at",
                "created_by_id",
                "occurrence_type_id",
                "form_data",
            )
        )
        return

    def safe_date_parse(self, date):
        try:
            return utc_to_local(parser.parse(date) if isinstance(date, str) else date)
        except Exception:
            return None

    def get_reportings(self):
        self.reportings = [
            {
                "uuid": str(item.uuid),
                "lot": item.lot,
                "road_name": item.road_name or "Sem Rodovia",
                "created_by": str(item.created_by_id),
                "occurrence_type_id": str(item.occurrence_type_id),
                "due_at": utc_to_local(item.due_at) if item.due_at else None,
                "executed_at": utc_to_local(item.executed_at)
                if item.executed_at
                else None,
                "artesp_date": self.safe_date_parse(item.form_data.get("artesp_date"))
                if item.form_data.get("artesp_date", False)
                else None,
            }
            for item in self.reportings_qs
        ]
        return

    def get_data(self):
        can_calculate = self.get_basic_data()
        if not can_calculate:
            return {}

        # Get reportings
        filters, exclude = self.get_filters_reportings()
        self.get_reportings_qs(filters, exclude)
        self.get_reportings()
        if not self.reportings:
            return {}

        # Get special type for Cobertura Vegetal
        self.special_type = [
            str(item)
            for item in OccurrenceType.objects.filter(
                name__icontains="cobertura vegetal", company=self.company
            )
            .filter(name__contains="OB")
            .values_list("uuid", flat=True)
        ]

        # Get results
        result_by_month = self.get_result_by_month()
        result_by_quarter = self.get_result_by_quarter()
        result_by_year = self.get_result_by_year()

        return {
            "indicator": self.csp_number,
            "name": self.csp_name,
            "year": result_by_year,
            "quarter": result_by_quarter,
            "month": result_by_month,
        }


class CspGraphEndpoint(CspBase):
    def __init__(self, params):
        self.params = params
        self.road_name = params.get("road_name", "")
        self.csp_topic = params.get("csp_topic", "").upper()
        self.csp_lot = params.get("csp_lot", "")
        self.start_date = params.get("start_date", "")
        self.end_date = params.get("end_date", "")
        self.km_step = params.get("km_step", "")
        super(CspGraphEndpoint, self).__init__(params)

    def get_filters_inspection_reportings(self):
        filters = {}

        inspect_types = get_obj_from_path(self.company.metadata, "csp__inspect_types")

        filters["company"] = self.company
        filters["found_at__gte"] = self.start_date
        filters["found_at__lt"] = self.end_date
        filters["occurrence_type_id__in"] = inspect_types
        filters["form_data__executed_by"] = self.csp_type
        filters["form_data__lots__has_any_keys"] = self.csp_lot
        filters["road_name"] = self.road_name
        if self.created_by:
            filters["created_by_id__in"] = self.created_by
        if self.system:
            filters["form_data__road_system"] = self.system

        return filters

    def get_filters_reportings(self):
        filters = {}
        exclude = {}
        filters["company"] = self.company
        filters["found_at__gte"] = self.start_date
        filters["found_at__lt"] = self.end_date
        filters["occurrence_type_id__in"] = self.occ_types
        filters["lot"] = self.csp_lot
        filters["road_name"] = self.road_name
        if self.created_by:
            filters["created_by_id__in"] = self.created_by
        if self.csp_type == "2":
            filters["form_data__artesp_code__isnull"] = False
            exclude["form_data__artesp_code__exact"] = ""

        return filters, exclude

    def get_response(self):
        can_calculate = self.get_basic_data()

        fields = [
            "start_date",
            "end_date",
            "road_name",
            "csp_topic",
            "km_step",
            "csp_lot",
        ]

        if not set(fields).issubset(self.params.keys()) or not can_calculate:
            return error_message(400, "Falta algum parâmetro")

        try:
            self.start_date = parser.parse(self.start_date).replace(tzinfo=pytz.UTC)
            self.end_date = parser.parse(self.end_date).replace(tzinfo=pytz.UTC)
        except Exception:
            return error_message(400, "start_date ou end_date inválido")

        if not self.km_step.isdigit():
            return error_message(400, "km_step inválido.")

        # Get occurrence_type ids
        if self.csp_topic.lower() == "all":
            self.occ_types = self.all_types
        else:
            topic = self.rules.get(self.csp_topic, {})
            self.occ_types = topic.get("types", [])

        # Get inspection reportings
        inspection_filters = self.get_filters_inspection_reportings()
        inspection_reportings_qs = Reporting.objects.filter(**inspection_filters).only(
            "form_data", "found_at", "created_by_id"
        )

        inspection_reportings = [
            {
                "form_data": item.form_data,
                "found_at": item.found_at,
                "created_by": str(item.created_by_id),
            }
            for item in inspection_reportings_qs
        ]

        if (not inspection_reportings) and (self.csp_number != "8.1"):
            return error_message(400, "Apontamentos de fiscalização não encontrados")

        # Get reportings
        filters, exclude = self.get_filters_reportings()
        reportings_qs = (
            Reporting.objects.filter(**filters)
            .exclude(**exclude)
            .annotate(
                km_int_temp=Case(
                    When(end_km__gt=0, then=Floor(Least("km", "end_km"))),
                    default=Floor("km"),
                )
            )
            .annotate(km_int=Cast("km_int_temp", IntegerField()))
        )

        # Iterate on each inspection reporting
        if self.csp_number != "8.1":

            reporting_uuids = []
            for inspection in inspection_reportings:
                inspection_lots = inspection["form_data"].get("lots", {})
                lot_data = inspection_lots.get(self.csp_lot, {})
                lot_topics = lot_data.get("topics", {})
                kms = lot_data.get("kms", [])
                if not inspection_lots or not lot_data:
                    continue
                if (self.csp_topic.lower() == "all") or (
                    self.csp_topic in lot_topics.keys()
                ):
                    reporting_uuids += reportings_qs.filter(
                        km_int__in=kms,
                        found_at__day=inspection["found_at"].day,
                        found_at__month=inspection["found_at"].month,
                        found_at__year=inspection["found_at"].year,
                        created_by_id=inspection["created_by"],
                    ).values_list("uuid", flat=True)

            # Filter reportings_qs
            reportings = reportings_qs.filter(uuid__in=reporting_uuids)

        else:
            reportings = reportings_qs

        occ_types = OccurrenceType.objects.filter(
            reporting_occurrence__in=reportings
        ).distinct()

        # form_data filter
        if "form_data" in self.params.keys():
            key_filter = KeyFilter(field_name="form_data", distinct=True)
            reportings = key_filter.filter(reportings, self.params["form_data"])

        if "lane" in self.params.keys() and self.params["lane"]:
            lanes = self.params["lane"].split(",")
            reportings = reportings.filter(lane__in=lanes)

        if "direction" in self.params.keys() and self.params["direction"]:
            directions = self.params["direction"].split(",")
            reportings = reportings.filter(direction__in=directions)

        # artesp filter
        if "has_artesp_code" in self.params.keys():
            if self.params["has_artesp_code"].lower() == "true":
                reportings = reportings.filter(
                    form_data__artesp_code__isnull=False
                ).exclude(form_data__artesp_code__exact="")

            if self.params["has_artesp_code"].lower() == "false":
                reportings = reportings.filter(form_data__artesp_code__isnull=True)
        if reportings.count() == 0:
            return error_message(400, "Apontamentos não encontrados.")

        reportings_count = ReportingCountRoad(
            int(self.km_step),
            self.road_name,
            reportings,
            occ_types,
            self.company_id,
        )

        return reportings_count.get_response()


class Csp31GraphEndpoint(CspBase):
    def __init__(self, params):
        self.params = params
        self.road_name = params.get("road_name", "")
        self.csp_topic = params.get("csp_topic", "").upper()
        self.csp_lot = params.get("csp_lot", "")
        self.start_date = params.get("start_date", "")
        self.end_date = params.get("end_date", "")
        self.km_step = params.get("km_step", "")
        super(Csp31GraphEndpoint, self).__init__(params)

    def get_response(self):
        can_calculate = self.get_basic_data()

        fields = [
            "start_date",
            "end_date",
            "road_name",
            "csp_topic",
            "km_step",
            "csp_lot",
        ]

        if not set(fields).issubset(self.params.keys()) or not can_calculate:
            return error_message(400, "Falta algum parâmetro")

        try:
            self.start_date = parser.parse(self.start_date).replace(tzinfo=pytz.UTC)
            self.end_date = parser.parse(self.end_date).replace(tzinfo=pytz.UTC)
        except Exception:
            return error_message(400, "start_date ou end_date inválido")

        if not self.km_step.isdigit():
            return error_message(400, "km_step inválido.")

        # Get occurrence_type ids
        if self.csp_topic.lower() == "all":
            self.occ_types = self.all_types
        else:
            topic = self.rules.get(self.csp_topic, {})
            self.occ_types = topic.get("types", [])

        # Get reportings
        results = Csp31Endpoint(self.params).get_data()
        period_name = "{}/{}".format(self.start_date.month, self.year)

        try:
            lots = results["month"][period_name]["indicators"][0]["lots"]
            roads = list(filter(lambda x: x["id"] == self.csp_lot, lots))[0]["roads"]
            reporting_uuids = list(
                filter(lambda x: x["name"] == self.road_name, roads)
            )[0]["reportings"]
        except Exception:
            reporting_uuids = []

        reportings = Reporting.objects.filter(uuid__in=reporting_uuids)

        occ_types = OccurrenceType.objects.filter(
            reporting_occurrence__in=reportings
        ).distinct()

        # form_data filter
        if "form_data" in self.params.keys():
            key_filter = KeyFilter(field_name="form_data", distinct=True)
            reportings = key_filter.filter(reportings, self.params["form_data"])

        if "lane" in self.params.keys() and self.params["lane"]:
            lanes = self.params["lane"].split(",")
            reportings = reportings.filter(lane__in=lanes)

        if "direction" in self.params.keys() and self.params["direction"]:
            directions = self.params["direction"].split(",")
            reportings = reportings.filter(direction__in=directions)

        # artesp filter
        if "has_artesp_code" in self.params.keys():
            if self.params["has_artesp_code"].lower() == "true":
                reportings = reportings.filter(
                    form_data__artesp_code__isnull=False
                ).exclude(form_data__artesp_code__exact="")

            if self.params["has_artesp_code"].lower() == "false":
                reportings = reportings.filter(form_data__artesp_code__isnull=True)

        reportings_count = ReportingCountRoad(
            int(self.km_step),
            self.road_name,
            reportings,
            occ_types,
            self.company_id,
        )

        return reportings_count.get_response()
