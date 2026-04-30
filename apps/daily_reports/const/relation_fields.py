"""
Constants related to the DailyReportRelation model
"""

from typing import Dict, List

from django.db.models import Model

from apps.daily_reports.models import (
    DailyReportEquipment,
    DailyReportExternalTeam,
    DailyReportOccurrence,
    DailyReportResource,
    DailyReportSignaling,
    DailyReportVehicle,
    DailyReportWorker,
    ProductionGoal,
)

FIELD_TO_MODEL_CLASS: Dict[str, Model] = {
    "worker": DailyReportWorker,
    "external_team": DailyReportExternalTeam,
    "equipment": DailyReportEquipment,
    "vehicle": DailyReportVehicle,
    "signaling": DailyReportSignaling,
    "occurrence": DailyReportOccurrence,
    "resource": DailyReportResource,
    "production_goal": ProductionGoal,
}

RELATION_FIELDS: List[str] = list(FIELD_TO_MODEL_CLASS.keys())
