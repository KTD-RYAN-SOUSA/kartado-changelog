import datetime
import uuid
from collections import OrderedDict
from datetime import date

from django.contrib.admin.utils import flatten
from django.db.models import Q

from apps.approval_flows.models import ApprovalStep
from apps.companies.models import Firm
from apps.daily_reports.models import (
    DailyReportEquipment,
    DailyReportOccurrence,
    DailyReportRelation,
    DailyReportResource,
    DailyReportSignaling,
    DailyReportVehicle,
    DailyReportWorker,
)
from apps.reportings.models import Reporting
from apps.resources.models import Contract
from apps.users.models import User
from helpers.apps.daily_reports import (
    translate_condition,
    translate_kind,
    translate_weather,
)
from helpers.strings import to_camel_case, translate_custom_options


def get_reporting_date_lookup(date_field: str, date: date) -> Q:
    date_lookups = {
        "found_at": Q(found_at__date=date),
        "executed_at": Q(executed_at__date=date),
        "created_at": Q(created_at__date=date),
        "updated_at": Q(updated_at__date=date),
    }
    return date_lookups[date_field]


def get_board_item_name(obj, model_name, field_name):
    if obj.company and getattr(obj, field_name):
        return translate_custom_options(
            obj.company.custom_options,
            model_name,
            field_name,
            getattr(obj, field_name),
        )
    elif hasattr(obj, "contract_item_administration_id"):
        try:
            return obj.contract_item_administration.resource.resource.name
        except Exception:
            pass

    return ""


def return_impact_duration(value):
    if value in [None, ""]:
        return ""
    impact_duration = value.split(":")
    if len(impact_duration) == 2:
        return value
    if len(impact_duration) == 3:
        return ":".join(impact_duration[:2])
    return value


def get_board_history(mdr):
    data = {}
    data["history"] = []
    worker_list = []
    equipment_list = []
    vehicle_list = []
    signaling_list = []
    occurrence_list = []
    resource_list = []
    excluded_uuids = []

    company = mdr.company

    daily_report_relations = (
        DailyReportRelation.history.model.objects.filter(
            multiple_daily_report_id=str(mdr.uuid)
        )
        .exclude(history_type="-")
        .order_by("history_date")
        .values_list(
            "worker_id",
            "equipment_id",
            "vehicle_id",
            "signaling_id",
            "occurrence_id",
            "resource_id",
            "active",
        )
    )
    for (
        worker_id,
        equipment_id,
        vehicle_id,
        signaling_id,
        occurrence_id,
        resource_id,
        active,
    ) in daily_report_relations:
        if worker_id:
            worker = (
                DailyReportWorker.history.model.objects.filter(uuid=worker_id)
                .exclude(history_id__in=excluded_uuids)
                .order_by("history_date")
                .first()
            )
            if worker is not None:
                excluded_uuids.append(str(worker.history_id))
                worker_list.append((worker, active))
                worker = (
                    DailyReportWorker.history.model.objects.filter(
                        uuid=worker_id, history_type="-"
                    )
                    .exclude(history_id__in=excluded_uuids)
                    .first()
                )
                if worker is not None:
                    excluded_uuids.append(str(worker.history_id))
                    worker_list.append((worker, ""))
        if equipment_id:
            equipment = (
                DailyReportEquipment.history.model.objects.filter(uuid=equipment_id)
                .exclude(history_id__in=excluded_uuids)
                .order_by("history_date")
                .first()
            )
            excluded_uuids.append(str(equipment.history_id))
            equipment_list.append((equipment, active))
            if (
                DailyReportEquipment.history.model.objects.filter(
                    uuid=equipment_id, history_type="-"
                )
                .exclude(history_id__in=excluded_uuids)
                .exists()
            ):
                equipment = (
                    DailyReportEquipment.history.model.objects.filter(
                        uuid=equipment_id, history_type="-"
                    )
                    .exclude(history_id__in=excluded_uuids)
                    .first()
                )
                excluded_uuids.append(str(equipment.history_id))
                equipment_list.append((equipment, ""))
        if vehicle_id:
            vehicle = (
                DailyReportVehicle.history.model.objects.filter(uuid=vehicle_id)
                .exclude(history_id__in=excluded_uuids)
                .order_by("history_date")
                .first()
            )
            excluded_uuids.append(str(vehicle.history_id))
            vehicle_list.append((vehicle, active))
            if (
                DailyReportVehicle.history.model.objects.filter(
                    uuid=vehicle_id, history_type="-"
                )
                .exclude(history_id__in=excluded_uuids)
                .exists()
            ):
                vehicle = (
                    DailyReportVehicle.history.model.objects.filter(
                        uuid=vehicle_id, history_type="-"
                    )
                    .exclude(history_id__in=excluded_uuids)
                    .first()
                )
                excluded_uuids.append(str(vehicle.history_id))
                vehicle_list.append((vehicle, ""))
        if signaling_id:
            signaling = (
                DailyReportSignaling.history.model.objects.filter(uuid=signaling_id)
                .exclude(history_id__in=excluded_uuids)
                .order_by("history_date")
                .first()
            )
            excluded_uuids.append(str(signaling.history_id))
            signaling_list.append((signaling, active))
            if (
                DailyReportSignaling.history.model.objects.filter(
                    uuid=signaling_id, history_type="-"
                )
                .exclude(history_id__in=excluded_uuids)
                .exists()
            ):
                signaling = (
                    DailyReportSignaling.history.model.objects.filter(
                        uuid=signaling_id, history_type="-"
                    )
                    .exclude(history_id__in=excluded_uuids)
                    .first()
                )
                excluded_uuids.append(str(signaling.history_id))
                signaling_list.append((signaling, ""))
        if occurrence_id:
            occurrence = (
                DailyReportOccurrence.history.model.objects.filter(uuid=occurrence_id)
                .exclude(history_id__in=excluded_uuids)
                .order_by("history_date")
                .first()
            )
            excluded_uuids.append(str(occurrence.history_id))
            occurrence_list.append((occurrence, active))
            if (
                DailyReportOccurrence.history.model.objects.filter(
                    uuid=occurrence_id, history_type="-"
                )
                .exclude(history_id__in=excluded_uuids)
                .exists()
            ):
                occurrence = (
                    DailyReportOccurrence.history.model.objects.filter(
                        uuid=occurrence_id, history_type="-"
                    )
                    .exclude(history_id__in=excluded_uuids)
                    .first()
                )
                excluded_uuids.append(str(occurrence.history_id))
                occurrence_list.append((occurrence, ""))
        if resource_id:
            resource = (
                DailyReportResource.history.model.objects.filter(uuid=resource_id)
                .exclude(history_id__in=excluded_uuids)
                .order_by("history_date")
                .first()
            )
            excluded_uuids.append(str(resource.history_id))
            resource_list.append((resource, active))
            if (
                DailyReportResource.history.model.objects.filter(
                    uuid=resource_id, history_type="-"
                )
                .exclude(history_id__in=excluded_uuids)
                .exists()
            ):
                resource = (
                    DailyReportResource.history.model.objects.filter(
                        uuid=resource_id, history_type="-"
                    )
                    .exclude(history_id__in=excluded_uuids)
                    .first()
                )
                excluded_uuids.append(str(resource.history_id))
                resource_list.append((resource, ""))

    if worker_list:
        for item, active in worker_list:
            if item.history_type == "+":
                history_changes = [
                    {
                        "group": "dailyReportWorker",
                        "action": "created",
                        "fields": [
                            {
                                "field": "role",
                                "oldValue": "",
                                "newValue": get_board_item_name(
                                    item, "DailyReportWorker", "role"
                                ),
                            },
                            {
                                "field": "amount",
                                "oldValue": "",
                                "newValue": item.amount,
                            },
                            {
                                "field": "active",
                                "oldValue": "",
                                "newValue": "Sim" if active else "Não",
                            },
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
                previous_active = active
            elif item.history_type == "~":
                previous_history = item.prev_record
                field_changes = [
                    {
                        "field": "role",
                        "oldValue": get_board_item_name(
                            previous_history, "DailyReportWorker", "role"
                        ),
                        "newValue": get_board_item_name(
                            item, "DailyReportWorker", "role"
                        ),
                    },
                    {
                        "field": "amount",
                        "oldValue": previous_history.amount,
                        "newValue": item.amount,
                    },
                    {
                        "field": "active",
                        "oldValue": "Sim" if previous_active else "Não",
                        "newValue": "Sim" if active else "Não",
                    },
                ]
                previous_active = active
                history_changes = [
                    {
                        "group": "dailyReportWorker",
                        "action": "updated",
                        "fields": field_changes,
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
            elif item.history_type == "-":
                previous_history = item.prev_record
                history_changes = [
                    {
                        "group": "dailyReportWorker",
                        "action": "removed",
                        "fields": [
                            {
                                "field": "role",
                                "oldValue": get_board_item_name(
                                    previous_history, "DailyReportWorker", "role"
                                ),
                                "newValue": "",
                            },
                            {
                                "field": "amount",
                                "oldValue": previous_history.amount,
                                "newValue": "",
                            },
                            {
                                "field": "active",
                                "oldValue": "Sim" if previous_active else "Não",
                                "newValue": "",
                            },
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
            else:
                pass

    if equipment_list:
        for item, active in equipment_list:
            if item.history_type == "+":
                history_changes = [
                    {
                        "group": "dailyReportEquipment",
                        "action": "created",
                        "fields": [
                            {
                                "field": "description",
                                "oldValue": "",
                                "newValue": get_board_item_name(
                                    item, "DailyReportEquipment", "description"
                                ),
                            },
                            {
                                "field": "kind",
                                "oldValue": "",
                                "newValue": translate_kind(item.kind, company),
                            },
                            {
                                "field": "amount",
                                "oldValue": "",
                                "newValue": item.amount,
                            },
                            {
                                "field": "active",
                                "oldValue": "",
                                "newValue": "Sim" if active else "Não",
                            },
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
                previous_active = active
            elif item.history_type == "~":
                previous_history = item.prev_record
                field_changes = [
                    {
                        "field": "description",
                        "oldValue": get_board_item_name(
                            previous_history,
                            "DailyReportEquipment",
                            "description",
                        ),
                        "newValue": get_board_item_name(
                            item, "DailyReportEquipment", "description"
                        ),
                    },
                    {
                        "field": "kind",
                        "oldValue": translate_kind(previous_history.kind, company),
                        "newValue": translate_kind(item.kind, company),
                    },
                    {
                        "field": "amount",
                        "oldValue": previous_history.amount,
                        "newValue": item.amount,
                    },
                    {
                        "field": "active",
                        "oldValue": "Sim" if previous_active else "Não",
                        "newValue": "Sim" if active else "Não",
                    },
                ]
                previous_active = active
                history_changes = [
                    {
                        "group": "dailyReportEquipment",
                        "action": "updated",
                        "fields": field_changes,
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
            elif item.history_type == "-":
                previous_history = item.prev_record
                history_changes = [
                    {
                        "group": "dailyReportEquipment",
                        "action": "removed",
                        "fields": [
                            {
                                "field": "description",
                                "oldValue": get_board_item_name(
                                    previous_history,
                                    "DailyReportEquipment",
                                    "description",
                                ),
                                "newValue": "",
                            },
                            {
                                "field": "kind",
                                "oldValue": translate_kind(
                                    previous_history.kind, company
                                ),
                                "newValue": "",
                            },
                            {
                                "field": "amount",
                                "oldValue": previous_history.amount,
                                "newValue": "",
                            },
                            {
                                "field": "active",
                                "oldValue": "Sim" if previous_active else "Não",
                                "newValue": "",
                            },
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
            else:
                pass

    if vehicle_list:
        for item, active in vehicle_list:
            if item.history_type == "+":
                history_changes = [
                    {
                        "group": "dailyReportVehicle",
                        "action": "created",
                        "fields": [
                            {
                                "field": "description",
                                "oldValue": "",
                                "newValue": get_board_item_name(
                                    item, "DailyReportVehicle", "description"
                                ),
                            },
                            {
                                "field": "kind",
                                "oldValue": "",
                                "newValue": translate_kind(item.kind, company),
                            },
                            {
                                "field": "amount",
                                "oldValue": "",
                                "newValue": item.amount,
                            },
                            {
                                "field": "active",
                                "oldValue": "",
                                "newValue": "Sim" if active else "Não",
                            },
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
                previous_active = active
            elif item.history_type == "~":
                previous_history = item.prev_record
                field_changes = [
                    {
                        "field": "description",
                        "oldValue": get_board_item_name(
                            previous_history,
                            "DailyReportVehicle",
                            "description",
                        ),
                        "newValue": get_board_item_name(
                            item, "DailyReportVehicle", "description"
                        ),
                    },
                    {
                        "field": "kind",
                        "oldValue": translate_kind(previous_history.kind, company),
                        "newValue": translate_kind(item.kind, company),
                    },
                    {
                        "field": "amount",
                        "oldValue": previous_history.amount,
                        "newValue": item.amount,
                    },
                    {
                        "field": "active",
                        "oldValue": "Sim" if previous_active else "Não",
                        "newValue": "Sim" if active else "Não",
                    },
                ]
                previous_active = active
                history_changes = [
                    {
                        "group": "dailyReportVehicle",
                        "action": "updated",
                        "fields": field_changes,
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
            elif item.history_type == "-":
                previous_history = item.prev_record
                history_changes = [
                    {
                        "group": "dailyReportVehicle",
                        "action": "removed",
                        "fields": [
                            {
                                "field": "description",
                                "oldValue": get_board_item_name(
                                    previous_history,
                                    "DailyReportVehicle",
                                    "description",
                                ),
                                "newValue": "",
                            },
                            {
                                "field": "kind",
                                "oldValue": translate_kind(
                                    previous_history.kind, company
                                ),
                                "newValue": "",
                            },
                            {
                                "field": "amount",
                                "oldValue": previous_history.amount,
                                "newValue": "",
                            },
                            {
                                "field": "active",
                                "oldValue": "Sim" if previous_active else "Não",
                                "newValue": "",
                            },
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
            else:
                pass

    if signaling_list:
        for item, active in signaling_list:
            if item.history_type == "+":
                history_changes = [
                    {
                        "group": "dailyReportSignaling",
                        "action": "created",
                        "fields": [
                            {
                                "field": "kind",
                                "oldValue": "",
                                "newValue": get_board_item_name(
                                    item, "DailyReportSignaling", "kind"
                                ),
                            },
                            {
                                "field": "active",
                                "oldValue": "",
                                "newValue": "Sim" if active else "Não",
                            },
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
                previous_active = active

            elif item.history_type == "~":
                previous_history = item.prev_record
                field_changes = [
                    {
                        "field": "kind",
                        "oldValue": get_board_item_name(
                            previous_history, "DailyReportSignaling", "kind"
                        ),
                        "newValue": get_board_item_name(
                            item, "DailyReportSignaling", "kind"
                        ),
                    },
                    {
                        "field": "active",
                        "oldValue": "Sim" if previous_active else "Não",
                        "newValue": "Sim" if active else "Não",
                    },
                ]
                previous_active = active
                history_changes = [
                    {
                        "group": "dailyReportSignaling",
                        "action": "updated",
                        "fields": field_changes,
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
            elif item.history_type == "-":
                previous_history = item.prev_record
                history_changes = [
                    {
                        "group": "dailyReportSignaling",
                        "action": "removed",
                        "fields": [
                            {
                                "field": "kind",
                                "oldValue": get_board_item_name(
                                    previous_history, "DailyReportSignaling", "kind"
                                ),
                                "newValue": "",
                            },
                            {
                                "field": "active",
                                "oldValue": "Sim" if previous_active else "Não",
                                "newValue": "",
                            },
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
            else:
                pass

    if occurrence_list:
        for item, active in occurrence_list:
            if item.history_type == "+":
                history_changes = [
                    {
                        "group": "dailyReportOccurrence",
                        "action": "created",
                        "fields": [
                            {
                                "field": "origin",
                                "oldValue": "",
                                "newValue": translate_custom_options(
                                    company.custom_options,
                                    "DailyReportOccurrence",
                                    "origin",
                                    getattr(item, "origin"),
                                ),
                            },
                            {
                                "field": "description",
                                "oldValue": "",
                                "newValue": translate_custom_options(
                                    company.custom_options,
                                    "DailyReportOccurrence",
                                    "origin",
                                    getattr(item, "description"),
                                ),
                            },
                            {
                                "field": "startsAt",
                                "oldValue": "",
                                "newValue": getattr(item, "starts_at").strftime("%H:%M")
                                if getattr(item, "starts_at")
                                else "",
                            },
                            {
                                "field": "endsAt",
                                "oldValue": "",
                                "newValue": getattr(item, "ends_at").strftime("%H:%M")
                                if getattr(item, "ends_at")
                                else "",
                            },
                            {
                                "field": "impactDuration",
                                "oldValue": "",
                                "newValue": return_impact_duration(
                                    getattr(item, "impact_duration")
                                ),
                            },
                            {
                                "field": "extraInfo",
                                "oldValue": "",
                                "newValue": item.extra_info or "",
                            },
                            {
                                "field": "active",
                                "oldValue": "",
                                "newValue": "Sim" if active else "Não",
                            },
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
                previous_active = active

            elif item.history_type == "~":
                previous_history = item.prev_record
                field_changes = [
                    {
                        "field": "origin",
                        "oldValue": translate_custom_options(
                            company.custom_options,
                            "DailyReportOccurrence",
                            "origin",
                            getattr(previous_history, "origin"),
                        ),
                        "newValue": translate_custom_options(
                            company.custom_options,
                            "DailyReportOccurrence",
                            "origin",
                            getattr(item, "origin"),
                        ),
                    },
                    {
                        "field": "description",
                        "oldValue": translate_custom_options(
                            company.custom_options,
                            "DailyReportOccurrence",
                            "origin",
                            getattr(previous_history, "description"),
                        ),
                        "newValue": translate_custom_options(
                            company.custom_options,
                            "DailyReportOccurrence",
                            "origin",
                            getattr(item, "description"),
                        ),
                    },
                    {
                        "field": "startsAt",
                        "oldValue": getattr(previous_history, "starts_at").strftime(
                            "%H:%M"
                        )
                        if getattr(previous_history, "starts_at")
                        else "",
                        "newValue": getattr(item, "starts_at").strftime("%H:%M")
                        if getattr(item, "starts_at")
                        else "",
                    },
                    {
                        "field": "endsAt",
                        "oldValue": getattr(previous_history, "ends_at").strftime(
                            "%H:%M"
                        )
                        if getattr(previous_history, "ends_at")
                        else "",
                        "newValue": getattr(item, "ends_at").strftime("%H:%M")
                        if getattr(item, "ends_at")
                        else "",
                    },
                    {
                        "field": "impactDuration",
                        "oldValue": return_impact_duration(
                            getattr(previous_history, "impact_duration")
                        ),
                        "newValue": return_impact_duration(
                            getattr(item, "impact_duration")
                        ),
                    },
                    {
                        "field": "extraInfo",
                        "oldValue": previous_history.extra_info or "",
                        "newValue": item.extra_info or "",
                    },
                    {
                        "field": "active",
                        "oldValue": "Sim" if previous_active else "Não",
                        "newValue": "Sim" if active else "Não",
                    },
                ]
                previous_active = active
                history_changes = [
                    {
                        "group": "dailyReportOccurrence",
                        "action": "updated",
                        "fields": field_changes,
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
            elif item.history_type == "-":
                previous_history = item.prev_record
                history_changes = [
                    {
                        "group": "dailyReportOccurrence",
                        "action": "removed",
                        "fields": [
                            {
                                "field": "origin",
                                "oldValue": translate_custom_options(
                                    company.custom_options,
                                    "DailyReportOccurrence",
                                    "origin",
                                    getattr(previous_history, "origin"),
                                ),
                                "newValue": "",
                            },
                            {
                                "field": "description",
                                "oldValue": translate_custom_options(
                                    company.custom_options,
                                    "DailyReportOccurrence",
                                    "origin",
                                    getattr(previous_history, "description"),
                                ),
                                "newValue": "",
                            },
                            {
                                "field": "startsAt",
                                "oldValue": getattr(
                                    previous_history, "starts_at"
                                ).strftime("%H:%M")
                                if getattr(previous_history, "starts_at")
                                else "",
                                "newValue": "",
                            },
                            {
                                "field": "endsAt",
                                "oldValue": getattr(
                                    previous_history, "ends_at"
                                ).strftime("%H:%M")
                                if getattr(previous_history, "ends_at")
                                else "",
                                "newValue": "",
                            },
                            {
                                "field": "impactDuration",
                                "oldValue": return_impact_duration(
                                    getattr(previous_history, "impact_duration")
                                ),
                                "newValue": "",
                            },
                            {
                                "field": "extraInfo",
                                "oldValue": previous_history.extra_info or "",
                                "newValue": "",
                            },
                            {
                                "field": "active",
                                "oldValue": "Sim" if previous_active else "Não",
                                "newValue": "",
                            },
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
            else:
                pass

    if resource_list:
        for item, active in resource_list:
            if item.history_type == "+":
                history_changes = [
                    {
                        "group": "dailyReportResource",
                        "action": "created",
                        "fields": [
                            {
                                "field": "kind",
                                "oldValue": "",
                                "newValue": translate_kind(item.kind, company),
                            },
                            {
                                "field": "description",
                                "oldValue": "",
                                "newValue": item.resource.name,
                            },
                            {
                                "field": "amount",
                                "oldValue": "",
                                "newValue": item.amount,
                            },
                            {
                                "field": "active",
                                "oldValue": "",
                                "newValue": "Sim" if active else "Não",
                            },
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
                previous_active = active

            elif item.history_type == "~":
                previous_history = item.prev_record
                field_changes = [
                    {
                        "field": "kind",
                        "oldValue": translate_kind(previous_history.kind, company),
                        "newValue": translate_kind(item.kind, company),
                    },
                    {
                        "field": "description",
                        "oldValue": previous_history.resource.name,
                        "newValue": item.resource.name,
                    },
                    {
                        "field": "amount",
                        "oldValue": previous_history.amount,
                        "newValue": item.amount,
                    },
                    {
                        "field": "active",
                        "oldValue": "Sim" if previous_active else "Não",
                        "newValue": "Sim" if active else "Não",
                    },
                ]
                previous_active = active
                history_changes = [
                    {
                        "group": "dailyReportResource",
                        "action": "updated",
                        "fields": field_changes,
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
            elif item.history_type == "-":
                previous_history = item.prev_record
                history_changes = [
                    {
                        "group": "dailyReportResource",
                        "action": "removed",
                        "fields": [
                            {
                                "field": "kind",
                                "oldValue": translate_kind(
                                    previous_history.kind, company
                                ),
                                "newValue": "",
                            },
                            {
                                "field": "description",
                                "oldValue": previous_history.resource.name,
                                "newValue": "",
                            },
                            {
                                "field": "amount",
                                "oldValue": previous_history.amount,
                                "newValue": "",
                            },
                            {
                                "field": "active",
                                "oldValue": "Sim" if previous_active else "Não",
                                "newValue": "",
                            },
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": item.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(item.history_user.uuid)
                        if item.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )
            else:
                pass

    data["history"].sort(key=lambda x: x["historyDate"])
    new_data = {}

    temp_dict = OrderedDict()

    for item in data["history"]:
        temp_dict.setdefault((item["historyDate"], item["historyUser"]), []).append(
            item["historyChanges"]
        )

    new_history = [
        {
            "historyDate": k[0],
            "historyUser": k[1],
            "historyChanges": flatten(v.pop() if len(v) == 1 else v),
        }
        for k, v in temp_dict.items()
    ]
    new_data["history"] = new_history
    return new_data


def get_history(mdr):
    WEATHER_LIST = [
        "morning_weather",
        "afternoon_weather",
        "night_weather",
    ]
    CONDITIONS_LIST = ["morning_conditions", "afternoon_conditions", "night_conditions"]
    WORK_DURATION_LIST = [
        "morning_start",
        "morning_end",
        "afternoon_start",
        "afternoon_end",
        "night_start",
        "night_end",
    ]

    # Translate some fields and values
    def translate_value(value, field=None):
        if isinstance(value, datetime.date):
            return value.strftime("%d/%m/%Y")
        elif isinstance(value, bool):
            if field == "editable":
                return "Desbloqueada" if value else "Bloqueada"
            else:
                return "Sim" if value else "Não"
        elif isinstance(value, uuid.UUID):
            if field == "approval_step":
                return ApprovalStep.objects.get(uuid=value).name
            elif field in ["created_by", "responsible", "inspector"]:
                return User.objects.get(uuid=value).get_full_name()
            elif field == "firm":
                # Returning whole object to account for SubCompany changes
                return Firm.objects.get(uuid=value)
            elif field == "contract":
                return Contract.objects.get(uuid=value).extra_info.get("r_c_number", "")
        return value if value is not None else ""

    def get_weather_conditions_history(history_item, previous_record=None):
        if not previous_record:
            weather_list = [
                {
                    "field": to_camel_case(item),
                    "oldValue": "",
                    "newValue": translate_weather(getattr(history_item, item, ""))
                    or "",
                }
                for item in WEATHER_LIST
            ]
            conditions_list = [
                {
                    "field": to_camel_case(item),
                    "oldValue": "",
                    "newValue": translate_condition(getattr(history_item, item, ""))
                    or "",
                }
                for item in CONDITIONS_LIST
            ]
            weather_conditions_list = weather_list + conditions_list
            is_weather_conditions_not_empty = any(
                item["newValue"] for item in weather_conditions_list
            )
            if is_weather_conditions_not_empty:
                weather_conditions_group = {
                    "group": "weatherConditions",
                    "action": "created",
                    "fields": weather_conditions_list,
                }

                return weather_conditions_group
            else:
                return None
        else:
            weather_list = [
                {
                    "field": to_camel_case(item),
                    "oldValue": translate_weather(getattr(previous_record, item, ""))
                    or "",
                    "newValue": translate_weather(getattr(history_item, item, ""))
                    or "",
                }
                for item in WEATHER_LIST
            ]
            conditions_list = [
                {
                    "field": to_camel_case(item),
                    "oldValue": translate_condition(getattr(previous_record, item, ""))
                    or "",
                    "newValue": translate_condition(getattr(history_item, item, ""))
                    or "",
                }
                for item in CONDITIONS_LIST
            ]
            final_list = weather_list + conditions_list
            is_updated = any(a["newValue"] for a in final_list)
            weather_conditions_group = {
                "group": "weatherConditions",
                "action": "updated" if is_updated else "removed",
                "fields": final_list,
            }

            return weather_conditions_group

    def get_work_day_history(history_item, previous_record=None):
        if not previous_record:
            work_day_list = [
                {
                    "field": to_camel_case(item),
                    "oldValue": "",
                    "newValue": getattr(history_item, item).strftime("%H:%M")
                    if getattr(history_item, item)
                    else "",
                }
                for item in WORK_DURATION_LIST
            ]
            is_work_day_not_empty = any(item["newValue"] for item in work_day_list)
            if is_work_day_not_empty:
                work_day_group = {
                    "group": "workDay",
                    "action": "created",
                    "fields": work_day_list,
                }

                return work_day_group
            else:
                return None
        else:
            work_day_list = [
                {
                    "field": to_camel_case(item),
                    "oldValue": getattr(previous_record, item).strftime("%H:%M")
                    if getattr(previous_record, item)
                    else "",
                    "newValue": getattr(history_item, item).strftime("%H:%M")
                    if getattr(history_item, item)
                    else "",
                }
                for item in WORK_DURATION_LIST
            ]
            is_updated = any(a["newValue"] for a in work_day_list)
            work_day_group = {
                "group": "workDay",
                "action": "updated" if is_updated else "removed",
                "fields": work_day_list,
            }

            return work_day_group

    data = {}
    data["history"] = []

    # History for created type - basic fields
    first_history = mdr.history.filter(history_type="+").first()
    first_values = [
        {"field": "number", "newValue": first_history.number},
        {"field": "date", "newValue": translate_value(first_history.date)},
        {
            "field": "dayWithoutWork",
            "newValue": translate_value(first_history.day_without_work),
        },
        {"field": "createdBy", "newValue": first_history.created_by.get_full_name()},
        {"field": "subcompany", "newValue": first_history.firm.subcompany.name},
        {"field": "firm", "newValue": first_history.firm.name},
        {"field": "responsible", "newValue": first_history.responsible.get_full_name()},
        {
            "field": "editable",
            "newValue": translate_value(first_history.editable, "editable"),
        },
        {
            "field": "useReportingResources",
            "newValue": translate_value(first_history.use_reporting_resources),
        },
    ]
    if first_history.history_change_reason:
        first_values.append(
            {
                "field": "historyChangeReason",
                "newValue": first_history.history_change_reason,
            }
        )
    if first_history.notes:
        first_values.append({"field": "notes", "newValue": first_history.notes})
    if first_history.approval_step:
        first_values.append(
            {"field": "approvalStep", "newValue": first_history.approval_step.name}
        )
    if first_history.contract:
        first_values.append(
            {
                "field": "contract",
                "newValue": first_history.contract.extra_info.get("r_c_number", ""),
            }
        )
    if first_history.inspector:
        first_values.append(
            {"field": "inspector", "newValue": first_history.inspector.get_full_name()}
        )

    # Merging all values
    first_values = [
        {
            "field": item["field"],
            "action": "created",
            "oldValue": "",
            "newValue": item["newValue"],
        }
        for item in first_values
    ]
    # History for created type - weather, conditions and duration

    weather_conditions_first_history = get_weather_conditions_history(first_history)
    if weather_conditions_first_history:
        first_values.append(weather_conditions_first_history)
    work_day_first_history = get_work_day_history(first_history)
    if work_day_first_history is not None:
        first_values.append(work_day_first_history)

    data["history"].append(
        {
            "historyDate": first_history.history_date.replace(second=0, microsecond=0),
            "historyUser": str(first_history.history_user.uuid)
            if first_history.history_user
            else "",
            "historyChanges": first_values,
        }
    )

    # History for updated and removed types
    remaining_histories = mdr.history.exclude(history_type="+").order_by("history_date")

    for history in remaining_histories:
        WEATHER_CONDITIONS_FLAG = True
        WORK_DAY_FLAG = True
        previous_history = history.prev_record
        delta = history.diff_against(
            previous_history,
            excluded_fields=[
                "uuid",
                "created_at",
                "header_info",
                "company",
                "reportings",
            ],
        )
        new_history = {
            "historyDate": history.history_date.replace(second=0, microsecond=0),
            "historyUser": str(history.history_user.uuid)
            if history.history_user
            else "",
            "historyChanges": [],
        }
        for change in delta.changes:
            if change.field == "approval_step":
                approval_step_changes = [
                    {
                        "field": to_camel_case(change.field),
                        "action": "updated",
                        "oldValue": translate_value(change.old, change.field),
                        "newValue": translate_value(change.new, change.field),
                    }
                ]
                if previous_history.editable != history.editable:
                    approval_step_changes.append(
                        {
                            "field": "editable",
                            "action": "updated",
                            "oldValue": translate_value(
                                previous_history.editable, "editable"
                            ),
                            "newValue": translate_value(history.editable, "editable"),
                        }
                    )
                data["history"].append(
                    {
                        "historyDate": history.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(history.history_user.uuid)
                        if history.history_user
                        else "",
                        "historyChanges": approval_step_changes,
                    }
                )
            elif change.field in [
                "number",
                "date",
                "day_without_work",
                "notes",
                "use_reporting_resources",
            ]:
                new_history["historyChanges"].append(
                    {
                        "field": to_camel_case(change.field),
                        "action": "updated"
                        if change.new not in ["", None]
                        else "removed",
                        "oldValue": translate_value(change.old),
                        "newValue": translate_value(change.new),
                    }
                )
            elif change.field in [
                "created_by",
                "responsible",
                "inspector",
                "contract",
            ]:
                new_history["historyChanges"].append(
                    {
                        "field": to_camel_case(change.field),
                        "action": "updated" if change.new else "removed",
                        "oldValue": translate_value(change.old, change.field),
                        "newValue": translate_value(change.new, change.field),
                    }
                )
            elif change.field == "firm":
                old_value = translate_value(change.old, change.field)
                new_value = translate_value(change.new, change.field)
                if new_value.subcompany != old_value.subcompany:
                    new_history["historyChanges"].append(
                        {
                            "field": "subcompany",
                            "action": "updated" if new_value else "removed",
                            "oldValue": old_value.subcompany.name,
                            "newValue": new_value.subcompany.name,
                        }
                    )
                new_history["historyChanges"].append(
                    {
                        "field": to_camel_case(change.field),
                        "action": "updated" if new_value else "removed",
                        "oldValue": old_value.name,
                        "newValue": new_value.name,
                    }
                )
            elif change.field in WEATHER_LIST:
                if WEATHER_CONDITIONS_FLAG:
                    new_history["historyChanges"].append(
                        get_weather_conditions_history(history, previous_history)
                    )
                    WEATHER_CONDITIONS_FLAG = False
            elif change.field in WORK_DURATION_LIST:
                if WORK_DAY_FLAG:
                    new_history["historyChanges"].append(
                        get_work_day_history(history, previous_history)
                    )
                    WORK_DAY_FLAG = False
            else:
                pass

        old_change_reason = getattr(previous_history, "history_change_reason")
        new_change_reason = getattr(history, "history_change_reason")
        if old_change_reason != new_change_reason:
            new_history["historyChanges"].append(
                {
                    "field": "historyChangeReason",
                    "action": "updated" if new_change_reason else "removed",
                    "oldValue": "" if old_change_reason is None else old_change_reason,
                    "newValue": "" if new_change_reason is None else new_change_reason,
                }
            )
        if new_history.get("historyChanges", []) != []:
            data["history"].append(new_history)

    board_history = get_board_history(mdr)

    data["history"].extend(board_history["history"])

    data["history"].sort(
        key=lambda x: x["historyChanges"][0].get("field", ""), reverse=True
    )
    data["history"].sort(key=lambda x: x["historyDate"])

    return data


def get_reportings_history(mdr):
    """
    Get history of reportings M2M field changes for a MultipleDailyReport.
    Tracks when reportings are linked or unlinked from the RDO.
    """
    data = {}
    data["history"] = []

    histories = mdr.history.all().order_by("history_date")
    if not histories.exists():
        return data

    all_reporting_uuids = set()
    histories_reportings_cache = {}

    for history in histories:
        reporting_uuids = set(history.reportings.values_list("reporting_id", flat=True))
        histories_reportings_cache[history.history_id] = reporting_uuids
        all_reporting_uuids.update(reporting_uuids)

    reportings_dict = {
        r.uuid: r for r in Reporting.objects.filter(uuid__in=all_reporting_uuids)
    }

    deleted_uuids = all_reporting_uuids - set(reportings_dict.keys())

    reporting_deletion_times = {}
    if deleted_uuids:
        deleted_reporting_histories = Reporting.history.filter(
            uuid__in=deleted_uuids, history_type="-"
        ).values("uuid", "history_date")
        reporting_deletion_times = {
            str(h["uuid"]): h["history_date"] for h in deleted_reporting_histories
        }

    previous_reportings = set()
    for history in histories:
        current_reportings = histories_reportings_cache[history.history_id]

        added_reportings = current_reportings - previous_reportings
        removed_reportings = previous_reportings - current_reportings

        if added_reportings:
            numbers = [
                "deleted" if uuid in deleted_uuids else reportings_dict[uuid].number
                for uuid in added_reportings
                if uuid in deleted_uuids
                or (uuid in reportings_dict and reportings_dict[uuid].number)
            ]
            if numbers:
                history_changes = [
                    {
                        "group": "reportings",
                        "action": "linked",
                        "fields": [
                            {
                                "field": "number",
                                "oldValue": [],
                                "newValue": numbers,
                            }
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": history.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(history.history_user.uuid)
                        if history.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )

        if removed_reportings:
            reportings_to_show = []
            for reporting_uuid in removed_reportings:
                uuid_str = str(reporting_uuid)

                if reporting_uuid not in deleted_uuids:
                    reportings_to_show.append(reporting_uuid)
                elif uuid_str in reporting_deletion_times:
                    deletion_time = reporting_deletion_times[uuid_str]
                    history_time = history.history_date
                    if deletion_time > history_time:
                        reportings_to_show.append(reporting_uuid)

            numbers = [
                "deleted"
                if reporting_uuid in deleted_uuids
                else reportings_dict[reporting_uuid].number
                for reporting_uuid in reportings_to_show
                if reporting_uuid in deleted_uuids
                or (
                    reporting_uuid in reportings_dict
                    and reportings_dict[reporting_uuid].number
                )
            ]
            if numbers:
                history_changes = [
                    {
                        "group": "reportings",
                        "action": "unlinked",
                        "fields": [
                            {
                                "field": "number",
                                "oldValue": numbers,
                                "newValue": [],
                            }
                        ],
                    }
                ]
                data["history"].append(
                    {
                        "historyDate": history.history_date.replace(
                            second=0, microsecond=0
                        ),
                        "historyUser": str(history.history_user.uuid)
                        if history.history_user
                        else "",
                        "historyChanges": history_changes,
                    }
                )

        previous_reportings = current_reportings

    data["history"].sort(key=lambda x: x["historyDate"])
    new_data = {}

    temp_dict = OrderedDict()
    for item in data["history"]:
        temp_dict.setdefault((item["historyDate"], item["historyUser"]), []).append(
            item["historyChanges"]
        )

    new_history = [
        {
            "historyDate": k[0],
            "historyUser": k[1],
            "historyChanges": flatten(v.pop() if len(v) == 1 else v),
        }
        for k, v in temp_dict.items()
    ]
    new_data["history"] = new_history
    return new_data
