from datetime import datetime
from itertools import chain

import sentry_sdk
from django.utils import timezone

from helpers.strings import get_direction_name


def job_sort_comparator(job):
    try:
        if "especial" in job.title.lower():
            return 0
        elif "fase" in job.title.lower():
            return next(int(a) for a in job.title.lower().split("-")[0] if a.isdigit())
        elif "barreira" in job.title.lower() or "gabarito" in job.title.lower():
            return 50
        else:
            return 70
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return 100


class InventoryScheduleEndpoint:
    def __init__(self, inventory, company):
        self.inventory = inventory.prefetch_related(
            "occurrence_type",
            "active_inspection",
            "children",
            "children__occurrence_type",
            "children__status",
            "children__status__status_specs",
            "inventory_jobs",
            "inventory_jobs__reportings",
            "inventory_jobs__inspection",
            "inventory_jobs__reportings__occurrence_type",
            "inventory_jobs__reportings__status__status_specs",
        ).order_by("road__name", "km")

        self.company = company

        inspection_occurrence_kind = company.metadata.get("inspection_occurrence_kind")
        if isinstance(inspection_occurrence_kind, str):
            inspection_occurrence_kind = [inspection_occurrence_kind]

        self.executed_status_order = company.metadata.get("executed_status_order")
        last_schedule_reset = company.metadata.get(
            "last_schedule_reset",
            "default will be caught in the try/except below",
        )

        try:
            self.last_schedule_reset = timezone.make_aware(
                datetime.strptime(last_schedule_reset, "%Y/%m/%d %H:%M")
            )
        except Exception:
            self.last_schedule_reset = timezone.make_aware(
                datetime.now().replace(month=1, day=1)
            )

        self.inspections = {
            item.uuid: [
                a
                for a in item.children.all()
                if a.occurrence_type.occurrence_kind in inspection_occurrence_kind
                and a.status.status_specs.all()[0].order >= self.executed_status_order
            ]
            for item in self.inventory
        }

        self.jobs = {}
        for item in self.inventory:
            jobs = item.inventory_jobs.all()
            for job in jobs:
                job.active = (
                    True
                    if (
                        item.active_inspection
                        and job.inspection
                        and job.inspection.uuid == item.active_inspection.uuid
                    )
                    else False
                )
            self.jobs[item.uuid] = sorted(jobs, key=job_sort_comparator)

        self.routine_inspection_years = self.get_routine_inspection_years()

    def find_and_format_inspection(self, inspections, year, item):
        try:
            inspection = next(
                a
                for a in inspections
                if a.executed_at
                and a.executed_at.year == year
                and "rotineira" in a.occurrence_type.name.lower()
            )
            return {
                "uuid": str(inspection.uuid),
                "date": inspection.executed_at,
                "structural_classification": inspection.form_data.get(
                    "structural_classification"
                ),
                "functional_classification": inspection.form_data.get(
                    "functional_classification"
                ),
                "wear_classification": inspection.form_data.get("wear_classification"),
                "type": inspection.occurrence_type.name,
                "is_active": item.active_inspection.uuid == inspection.uuid
                if item.active_inspection
                else False,
            }
        except Exception:
            return {"type": "rotineira"}

    def get_inspections(self, item):
        inspections = self.inspections[item.uuid]
        return [
            {
                "uuid": str(inspection.uuid),
                "date": inspection.executed_at,
                "structural_classification": inspection.form_data.get(
                    "structural_classification"
                ),
                "functional_classification": inspection.form_data.get(
                    "functional_classification"
                ),
                "wear_classification": inspection.form_data.get("wear_classification"),
                "type": inspection.occurrence_type.name,
                "is_active": item.active_inspection.uuid == inspection.uuid
                if item.active_inspection
                else False,
            }
            for inspection in inspections
            if "inicial" in inspection.occurrence_type.name.lower()
            or "especial" in inspection.occurrence_type.name.lower()
        ] + [
            self.find_and_format_inspection(inspections, year, item)
            for year in self.routine_inspection_years
        ]

    def get_jobs(self, item):

        jobs = self.jobs[item.uuid]

        return_jobs = []

        for job in jobs:

            execution_dates = (
                sorted([a.executed_at for a in job.reportings.all() if a.executed_at])
                if len(job.reportings.all())
                else []
            )
            execution_start_date = execution_dates[0] if len(execution_dates) else None
            is_done = len(execution_dates) and len(execution_dates) == len(
                job.reportings.all()
            )
            execution_end_date = execution_dates[-1] if is_done else None

            return_jobs.append(
                {
                    "uuid": str(job.uuid),
                    "title": job.title,
                    "color": job.description,
                    "start_date": job.start_date,
                    "end_date": job.end_date,
                    "execution_start_date": execution_start_date,
                    "execution_end_date": execution_end_date,
                    "is_done": is_done,
                    "inspection": str(job.inspection_id),
                    "all_services": sorted(
                        [
                            {
                                "uuid": str(reporting.uuid),
                                "occurrence_type_name": reporting.occurrence_type.name,
                                "description": reporting.form_data.get("description"),
                                "date": reporting.executed_at,
                                "is_executed": reporting.status.status_specs.all()[
                                    0
                                ].order
                                >= self.executed_status_order,
                            }
                            for reporting in job.reportings.all()
                        ],
                        key=lambda x: (x["date"] is None, x["date"]),
                    ),
                    "pending": [
                        {
                            "uuid": str(reporting.uuid),
                            "occurrence_type_name": reporting.occurrence_type.name,
                            "description": reporting.form_data.get("description"),
                        }
                        for reporting in [
                            a
                            for a in job.reportings.all()
                            if a.status.status_specs.all()[0].order
                            < self.executed_status_order
                        ]
                    ],
                    "executed": sorted(
                        [
                            {
                                "uuid": str(reporting.uuid),
                                "occurrence_type_name": reporting.occurrence_type.name,
                                "description": reporting.form_data.get("description"),
                                "date": reporting.executed_at,
                            }
                            for reporting in [
                                a
                                for a in job.reportings.all()
                                if a.status.status_specs.all()[0].order
                                >= self.executed_status_order
                            ]
                        ],
                        key=lambda x: x["date"],
                    ),
                    "is_active": job.active,
                }
            )

        return return_jobs

    def get_is_scheduled(self, jobs):
        starting_day_of_current_year = timezone.make_aware(
            datetime.now().replace(month=1, day=1)
        )
        ending_day_of_current_year = timezone.make_aware(
            datetime.now().replace(month=12, day=31)
        )

        def is_between_dates(job):
            return (
                job["start_date"]
                and job["start_date"] > starting_day_of_current_year
                and job["start_date"] < ending_day_of_current_year
            ) or (
                job["end_date"]
                and job["end_date"] > starting_day_of_current_year
                and job["end_date"] < ending_day_of_current_year
            )

        return any([is_between_dates(a) for a in jobs])

    def get_is_updated(self, jobs):
        def is_between_dates(job):
            return (
                job["execution_end_date"]
                and job["execution_end_date"] > self.last_schedule_reset
                and job["execution_end_date"] < timezone.now()
            )

        return any([is_between_dates(a) for a in jobs])

    def get_inspection_types(self, item):
        return {
            "inicial": len(
                [a for a in item if "inicial" in a.occurrence_type.name.lower()]
            ),
            "rotineira": len(
                [a for a in item if "rotineira" in a.occurrence_type.name.lower()]
            ),
            "especial": len(
                [a for a in item if "especial" in a.occurrence_type.name.lower()]
            ),
        }

    def get_routine_inspection_years(self):
        # Flatten all the inspections to a single list
        all_inspections = []
        for inventory_item in self.inventory:
            all_inspections += inventory_item.children.all()

        # Get all the years
        all_inspections_years = [
            a.executed_at.year
            for a in all_inspections
            if a.executed_at and "rotineira" in a.occurrence_type.name.lower()
        ]
        # Return unique list of years for which we had inspections
        return sorted(list(set(all_inspections_years)))

    def get_initial_inspection_date(self, inspections):
        try:
            return next(a for a in inspections if "inicial" in a["type"].lower())[
                "date"
            ]
        except Exception:
            return ""

    def get_data(self):
        # self.company = self.inventory[0].company
        all_jobs = set(chain(*self.jobs.values()))

        try:
            start_date = min([a.start_date for a in all_jobs if a.start_date])
            start_date = datetime(start_date.year, 1, 1, 12, tzinfo=start_date.tzinfo)
            end_date = max([a.end_date for a in all_jobs if a.end_date])
            end_date = datetime(end_date.year, 12, 31, 12, tzinfo=end_date.tzinfo)
        except Exception:
            start_date = None
            end_date = None

        all_inspections = [
            self.get_inspection_types(a) for a in self.inspections.values()
        ]
        try:
            initial_inspection_columns = max(
                *[a["inicial"] for a in all_inspections], 1
            )
            routine_inspection_columns = max(
                *[a["rotineira"] for a in all_inspections], 1
            )
            special_inspection_columns = max(
                *[a["especial"] for a in all_inspections], 1
            )
        except Exception:
            initial_inspection_columns = 1
            routine_inspection_columns = 1
            special_inspection_columns = 1

        inventory_updated_at = [a.updated_at for a in self.inventory]
        inspections_updated_at = sorted(
            {x.updated_at for v in self.inspections.values() for x in v}
        )
        jobs_services = {x.reportings.all() for v in self.jobs.values() for x in v}
        services_updated_at = {x.updated_at for v in jobs_services for x in v}

        try:
            last_updated_at = max(
                [
                    *inventory_updated_at,
                    *inspections_updated_at,
                    *services_updated_at,
                ]
            )
        except Exception:
            last_updated_at = None

        # Get data from reportings
        inventory_data = [
            {
                "uuid": str(item.pk),
                "km": "{:07.3f}".format(item.km).replace(".", "+"),
                "end_km": "{:07.3f}".format(item.end_km).replace(".", "+"),
                "number": item.number,
                "direction": get_direction_name(self.company, item.direction),
                "occurrence_type_name": str(item.occurrence_type.name),
                "inspections": self.get_inspections(item),
                "jobs": self.get_jobs(item),
            }
            for item in self.inventory
        ]

        inventory_data = [
            {
                **a,
                "initial_inspection_date": self.get_initial_inspection_date(
                    a["inspections"]
                ),
                "is_updated": self.get_is_updated(a["jobs"]),
                "is_scheduled": self.get_is_scheduled(a["jobs"]),
            }
            for a in inventory_data
        ]

        return {
            "inventory": inventory_data,
            "start_date": start_date,
            "end_date": end_date,
            "initial_inspection_columns": initial_inspection_columns,
            "routine_inspection_columns": routine_inspection_columns,
            "special_inspection_columns": special_inspection_columns,
            "routine_inspection_years": self.routine_inspection_years,
            "last_updated_at": last_updated_at,
        }
