import uuid
from collections import OrderedDict
from datetime import datetime
from functools import reduce

from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework_json_api import serializers
from rest_framework_json_api.utils import format_field_names

from helpers.permissions import PermissionManager, join_queryset
from helpers.strings import get_obj_from_path

from .filters import ConstructionFilter, ConstructionProgressFilter
from .models import Construction, ConstructionProgress
from .permissions import ConstructionPermissions, ConstructionProgressPermissions
from .serializers import (
    ConstructionProgressSerializer,
    ConstructionSerializer,
    CustomConstructionProgressSerializer,
)


class ConstructionViewSet(ModelViewSet):
    serializer_class = ConstructionSerializer
    filterset_class = ConstructionFilter
    permissions = None
    permission_classes = [IsAuthenticated, ConstructionPermissions]
    queryset_to_verify = None

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "company",
        "name",
        "description",
        "location",
        "km",
        "end_km",
        "construction_item",
        "intervention_type",
        "created_by",
        "created_at",
        "scheduling_start_date",
        "scheduling_end_date",
        "analysis_start_date",
        "analysis_end_date",
        "execution_start_date",
        "execution_end_date",
        "spend_schedule_start_date",
        "spend_schedule_end_date",
        "origin",
    ]

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list" or "retrieve"
        if self.action in ["list", "retrieve"]:
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return Construction.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="Construction",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()

            supervisor_agency_queryset = Construction.objects.filter(
                company_id=user_company, origin="AGENCY"
            )
            self.queryset_to_verify = supervisor_agency_queryset

            if self.action == "list":
                if "none" in allowed_queryset:
                    queryset = join_queryset(queryset, Construction.objects.none())
                if "supervisor_agency" in allowed_queryset:
                    queryset = join_queryset(
                        queryset,
                        supervisor_agency_queryset,
                    )
                if "all" in allowed_queryset:
                    queryset = join_queryset(
                        queryset,
                        Construction.objects.filter(company_id=user_company),
                    )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = Construction.objects.filter(company__in=user_companies)

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def format(self, obj, format_type="camelize"):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, dict):
                    obj[key] = format_field_names(self.format(value), format_type)
                elif isinstance(value, list):
                    temp_list = value.copy()
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            temp_list[i] = format_field_names(
                                self.format(item), format_type
                            )
                        else:
                            temp_list[i] = item
                    obj[key] = temp_list
            return format_field_names(obj, format_type)
        elif isinstance(obj, list):
            return [self.format(item, format_type) for item in obj]

    @action(methods=["GET"], url_path="FollowUp", detail=True)
    def get_follow_up(self, request, pk=None):
        try:
            construction = Construction.objects.get(pk=pk)
        except Construction.DoesNotExist:
            raise serializers.ValidationError(
                "kartado.error.construction.construction_not_found"
            )

        construction_phases = construction.phases

        # Handle step filter
        step = request.query_params["step"] if "step" in request.query_params else None
        if step is not None:
            try:
                step = float(step)
            except ValueError:
                raise serializers.ValidationError(
                    "kartado.error.construction.step_is_not_a_float"
                )

        # If both progress and date filters are being used, throw an error
        uses_progress_filter = "construction_progress" in request.query_params
        uses_date_filter = "date" in request.query_params
        if uses_progress_filter and uses_date_filter:
            raise serializers.ValidationError(
                "kartado.error.construction.progress_and_date_filters_cant_be_used_together"
            )

        # If specific progress is provided, use that progress
        if uses_progress_filter:
            try:
                construction_progress_id = uuid.UUID(
                    request.query_params["construction_progress"]
                )
                construction_progress = construction.construction_progresses.get(
                    pk=construction_progress_id
                )
            except ValueError:
                raise serializers.ValidationError(
                    "kartado.error.construction_progress.invalid_uuid"
                )
            except ConstructionProgress.DoesNotExist:
                raise serializers.ValidationError(
                    "kartado.error.construction_progress.construction_progress_not_found"
                )
        # If a date is provided get latest progress for that date
        elif uses_date_filter:
            date = request.query_params["date"]
            is_full_date = len(date.split("-")) == 3

            if is_full_date:
                try:
                    date = datetime.strptime(date, "%Y-%m-%d")
                except ValueError:
                    raise serializers.ValidationError(
                        "kartado.error.construction.invalid_date_format"
                    )

                progresses_til_date = construction.construction_progresses.filter(
                    executed_at__date__lte=date
                )
            else:
                try:
                    date = datetime.strptime(date, "%Y-%m")
                except ValueError:
                    raise serializers.ValidationError(
                        "kartado.error.construction.invalid_date_format"
                    )

                progresses_til_date = construction.construction_progresses.filter(
                    executed_at__date__month__lte=date.month,
                    executed_at__date__year__lte=date.year,
                )

            construction_progress = progresses_til_date.order_by("executed_at").last()
        # Defaults to latest progress for that construction
        else:
            construction_progress = construction.construction_progresses.order_by(
                "executed_at"
            ).last()

        # Statuses
        STATUS_FINISHED = "finished"
        STATUS_IN_PROGRESS = "in_progress"
        STATUS_NOT_STARTED = "not_started"

        # Status colors
        STATUS_COLOR_METADATA = get_obj_from_path(
            construction.company.metadata, "straight_line_diagram_colors"
        )
        # If it's not configured, use defaults
        if not STATUS_COLOR_METADATA:
            STATUS_COLOR_METADATA = {
                "finished": "#00ff00",
                "in_progress": "#ffff00",
                "not_started": "#ffffff",
            }
        STATUS_FINISHED_COLOR = STATUS_COLOR_METADATA[STATUS_FINISHED]
        STATUS_IN_PROGRESS_COLOR = STATUS_COLOR_METADATA[STATUS_IN_PROGRESS]
        STATUS_NOT_STARTED_COLOR = STATUS_COLOR_METADATA[STATUS_NOT_STARTED]

        # Extract km limits
        km = construction.km
        end_km = construction.end_km

        # Handle general progress details
        if construction_progress:
            progress_details = construction_progress.progress_details
        else:
            progress_details = []

        for phase_index, phase in enumerate(construction_phases):
            for subphase_index, subphase in enumerate(
                get_obj_from_path(phase, "subphases")
            ):
                # Extract details related to subphase
                related_progress_details = [
                    detail
                    for detail in progress_details
                    if int(detail["phase"]) == phase_index
                    and int(detail["subphase"]) == subphase_index
                ]

                # If there are details for that subphase
                if len(related_progress_details) > 0:
                    # Inject executed amount into subphase
                    executed_amount = sum(
                        [
                            get_obj_from_path(detail, "executedAmount")
                            for detail in related_progress_details
                        ]
                    )
                    subphase["executedAmount"] = executed_amount

                    subphase_expected_amount = get_obj_from_path(
                        subphase, "expectedAmount"
                    )
                    if (
                        subphase_expected_amount in [None, []]
                        or subphase_expected_amount <= 0
                    ):
                        raise serializers.ValidationError(
                            "kartado.error.construction.subphase_has_invalid_expected_amount"
                        )

                    # Inject percentage done into subphase
                    subphase["percentageDone"] = round(
                        executed_amount / subphase_expected_amount, 2
                    )

                    # Straight line diagram setup
                    subphase["straightLineDiagram"] = []
                    straight_line_diagram = subphase["straightLineDiagram"]

                    # Handle step filter
                    if step is not None:
                        # Add km steps
                        current_km = km
                        while current_km < end_km:
                            entry = {"km": current_km}

                            straight_line_diagram.append(entry)
                            current_km = round(current_km + step, 3)
                        straight_line_diagram.append({"km": end_km})

                        # Add status and color
                        stretches_list = [
                            detail["stretches"] for detail in related_progress_details
                        ]
                        stretches_list = reduce(
                            lambda a, b: a + b, stretches_list
                        )  # Join all lists

                        for entry_index, entry in enumerate(straight_line_diagram):
                            related_stretches = [
                                stretch
                                for stretch in stretches_list
                                if entry["km"] >= get_obj_from_path(stretch, "km")
                                and get_obj_from_path(stretch, "end_km") > entry["km"]
                            ]

                            # Scenarios
                            if len(related_stretches) > 0:
                                all_finished = all(
                                    [
                                        stretch["status"] == STATUS_FINISHED
                                        for stretch in related_stretches
                                    ]
                                )
                                any_in_progress = any(
                                    [
                                        stretch["status"] == STATUS_FINISHED
                                        or stretch["status"] == STATUS_IN_PROGRESS
                                        for stretch in related_stretches
                                    ]
                                )
                            else:
                                all_finished = False
                                any_in_progress = False

                            # Set status and color
                            if all_finished:
                                entry["status"] = STATUS_FINISHED
                                entry["color"] = STATUS_FINISHED_COLOR
                            elif any_in_progress:
                                entry["status"] = STATUS_IN_PROGRESS
                                entry["color"] = STATUS_IN_PROGRESS_COLOR
                            else:
                                entry["status"] = STATUS_NOT_STARTED
                                entry["color"] = STATUS_NOT_STARTED_COLOR

                # If there are not details use defaults
                else:
                    subphase["executedAmount"] = 0.0
                    subphase["percentageDone"] = 0.0

                    # If using step filter
                    if step is not None:
                        # Setup
                        subphase["straightLineDiagram"] = []
                        straight_line_diagram = subphase["straightLineDiagram"]

                        # Add km steps with status and color
                        current_km = km
                        while current_km < end_km:
                            entry = {
                                "km": current_km,
                                "status": STATUS_NOT_STARTED,
                                "color": STATUS_NOT_STARTED_COLOR,
                            }

                            straight_line_diagram.append(entry)
                            current_km = round(current_km + step, 3)
                        straight_line_diagram.append(
                            {
                                "km": current_km,
                                "status": STATUS_NOT_STARTED,
                                "color": STATUS_NOT_STARTED_COLOR,
                            }
                        )

        return Response(self.format(construction_phases))

    @action(methods=["GET"], url_path="Evolution", detail=True)
    def get_evolution(self, request, pk=None):
        try:
            construction = Construction.objects.get(pk=pk)
        except Construction.DoesNotExist:
            raise serializers.ValidationError(
                "kartado.error.construction.construction_not_found"
            )

        # Handle date filters
        if "starts_at" in request.query_params and "ends_at" in request.query_params:
            try:
                starts_at = datetime.strptime(
                    request.query_params["starts_at"], "%Y-%m-%d"
                )
                ends_at = datetime.strptime(request.query_params["ends_at"], "%Y-%m-%d")
            except ValueError:
                raise serializers.ValidationError(
                    "kartado.error.construction.invalid_date_format"
                )
        else:
            raise serializers.ValidationError(
                "kartado.error.construction.starts_at_and_ends_at_filters_are_required"
            )

        # Prepare construction progresses
        const_progs = construction.construction_progresses.order_by("executed_at")
        prev_const_prog = const_progs.exclude(executed_at__date__gt=starts_at).last()
        period_const_prog = const_progs.filter(
            executed_at__date__gte=starts_at, executed_at__date__lte=ends_at
        ).last()

        # Prepare response variables
        prev_total_perc = 0.0
        period_total_perc = 0.0
        total_percs_sum = 0.0
        resp_phases = []

        # Go through phases extracting the progress
        construction_phases = construction.phases
        for phase_index, phase in enumerate(construction_phases):
            # Prepare (or reset) totals for phase percentages
            prev_perc_for_phase = 0.0
            period_perc_for_phase = 0.0

            # Extract phase info
            phase_description = get_obj_from_path(phase, "phaseDescription")
            phase_weight = get_obj_from_path(phase, "weight")
            phase_actual_weight = phase_weight / 100 if phase_weight else 0.0

            for subphase_index, subphase in enumerate(
                get_obj_from_path(phase, "subphases")
            ):
                # Progress details previous to the date
                prev_progress_details = (
                    [
                        detail
                        for detail in prev_const_prog.progress_details
                        if detail["phase"] == phase_index
                        and detail["subphase"] == subphase_index
                    ]
                    if prev_const_prog
                    else []
                )

                # Progress details of that period
                period_progress_details = (
                    [
                        detail
                        for detail in period_const_prog.progress_details
                        if detail["phase"] == phase_index
                        and detail["subphase"] == subphase_index
                    ]
                    if period_const_prog
                    else []
                )

                # Get executed amount for both scenarios
                prev_executed_amount = sum(
                    [
                        get_obj_from_path(detail, "executedAmount")
                        for detail in prev_progress_details
                    ]
                )
                period_executed_amount = sum(
                    [
                        get_obj_from_path(detail, "executedAmount")
                        for detail in period_progress_details
                    ]
                )

                subphase_weight = get_obj_from_path(subphase, "weight") / 100
                expected_for_subphase = get_obj_from_path(subphase, "expectedAmount")
                if expected_for_subphase <= 0:
                    raise serializers.ValidationError(
                        "kartado.error.construction.subphase_has_zero_or_negative_expected_amount"
                    )

                # Calculate percentages
                prev_perc_for_subphase = (
                    prev_executed_amount / expected_for_subphase
                ) * subphase_weight
                prev_perc_for_subphase = prev_perc_for_subphase

                # NOTE: Since progress is cumulative, the only scenario where the subtraction
                # has negative results is when the period has no progress (which is the condition here)
                if period_executed_amount > 0.0:
                    period_perc_for_subphase = (
                        (period_executed_amount - prev_executed_amount)
                        / expected_for_subphase
                    ) * subphase_weight
                else:
                    period_perc_for_subphase = 0.0

                # Add to phase percentage totals
                prev_perc_for_phase += prev_perc_for_subphase
                period_perc_for_phase += period_perc_for_subphase

            # Apply the phase's weight
            prev_service_perc = prev_perc_for_phase * phase_actual_weight
            period_service_perc = period_perc_for_phase * phase_actual_weight

            current_service_perc = prev_service_perc + period_service_perc

            # Append to response phases list
            resp_phases.append(
                {
                    "phaseDescription": phase_description,
                    "previousServicePercentage": prev_service_perc,
                    "inPeriodServicePercentage": period_service_perc,
                    "currentServicePercentage": current_service_perc,
                    "weight": phase_weight,
                }
            )

            # Add phase's final percentages to grand total
            prev_total_perc += prev_service_perc
            period_total_perc += period_service_perc
            total_percs_sum += current_service_perc

        # Prepare schedule
        spend_schedule = construction.spend_schedule
        ordered_spend_schedule = OrderedDict()

        def schedule_sorter(item):
            return datetime.strptime(item, "%m/%Y")

        # Sort spend_schedule and for manipulation
        sorted_keys = sorted(spend_schedule, key=schedule_sorter)
        for sorted_key in sorted_keys:
            ordered_spend_schedule[sorted_key] = spend_schedule[sorted_key]

        # Handle schedule
        resp_schedule = OrderedDict()
        for date_key, expected_month in ordered_spend_schedule.items():
            date_key_datetime = datetime.strptime(date_key, "%m/%Y")

            # Get latest progress for that date
            date_key_prog = const_progs.filter(
                executed_at__date__month=date_key_datetime.month,
                executed_at__date__year=date_key_datetime.year,
            ).last()

            # Get last resp_schedule entry if exists
            if len(resp_schedule) > 0:
                prev_resp_schedule_key = list(resp_schedule.keys())[-1]
                prev_resp_schedule = resp_schedule[prev_resp_schedule_key]
            else:
                prev_resp_schedule = None

            executed = 0.0  # default
            # Is there any progress for this month?
            if date_key_prog:
                for detail in date_key_prog.progress_details:
                    phase_i = int(detail["phase"])
                    subphase_i = int(detail["subphase"])

                    subphase = construction_phases[phase_i]["subphases"][subphase_i]

                    # Convert weights to decimal
                    phase_weight = construction_phases[phase_i]["weight"] / 100
                    subphase_weight = subphase["weight"] / 100

                    subphase_expected_amount = get_obj_from_path(
                        subphase, "expectedAmount"
                    )
                    if subphase_expected_amount <= 0:
                        raise serializers.ValidationError(
                            "kartado.error.construction.subphase_has_zero_or_negative_expected_amount"
                        )

                    executed_amount = get_obj_from_path(detail, "executedAmount")

                    # Calculate naive percentage
                    detail_total = executed_amount / subphase_expected_amount

                    # Apply weights to naive percentage
                    detail_total = detail_total * subphase_weight * phase_weight

                    executed += detail_total
            # Is there at least a previous entry to copy?
            elif prev_resp_schedule:
                executed = prev_resp_schedule["executed"]

            # Convert expected_perc from str to float
            try:
                expected_month = float(expected_month)
            except Exception:
                expected_month = 0.0

            # Calculate cumulative expected
            expected = (
                sum([float(item["expected_month"]) for item in resp_schedule.values()])
                + expected_month
            )

            # Calculate executed_month
            if prev_resp_schedule:
                executed_month = executed - prev_resp_schedule["executed"]
            else:
                executed_month = executed

            resp_schedule[date_key] = {
                "expected_month": expected_month,
                "executed_month": executed_month,
                "expected": expected,
                "executed": executed,
            }

        # Add construction rate info
        construction_rate = None
        if resp_schedule:
            ends_at_date_key = ends_at.strftime("%m/%Y")

            # If provided ends_at is within schedule use ends_at_date_key
            # otherwise use last entry within schedule
            rate_date_key = (
                ends_at_date_key
                if ends_at_date_key in resp_schedule
                else list(resp_schedule.keys())[-1]
            )

            month_percs = resp_schedule[rate_date_key]
            month_executed = get_obj_from_path(month_percs, "executedMonth")
            month_expected = get_obj_from_path(month_percs, "expectedMonth")

            if month_executed >= month_expected:
                construction_rate = "regular"
            elif month_executed == 0.0:
                construction_rate = "stuck"
            elif month_executed < month_expected:
                construction_rate = "slow"

        # Build response dict
        response_data = {
            "previousTotal": prev_total_perc,
            "executedInPeriod": period_total_perc,
            "currentTotal": total_percs_sum,
            "constructionRate": construction_rate,
            "phases": resp_phases,
            "schedule": resp_schedule,
        }

        return Response(response_data)


class ConstructionProgressViewSet(ModelViewSet):
    serializer_class = ConstructionProgressSerializer
    filterset_class = ConstructionProgressFilter
    permissions = None
    permission_classes = [IsAuthenticated, ConstructionProgressPermissions]

    ordering = "uuid"
    ordering_fields = [
        "uuid",
        "name",
        "created_at",
        "executed_at",
        "created_by",
        "construction",
        "progress_details",
        "reportings",
        "files",
    ]

    def get_serializer_class(self):
        necessary_query_params = ["only_last_progress", "exclude_last_progress"]
        if self.request.method == "GET" and self.has_necessary_query_params(
            necessary_query_params
        ):
            return CustomConstructionProgressSerializer
        else:
            return self.serializer_class

    def get_queryset(self):
        queryset = None

        # Limit the queryset if the action is "list"
        if self.action == "list":
            # If there's no "company" in the request, return nothing
            if "company" not in self.request.query_params:
                return ConstructionProgress.objects.none()

            user_company = uuid.UUID(self.request.query_params["company"])

            if not self.permissions:
                self.permissions = PermissionManager(
                    user=self.request.user,
                    company_ids=user_company,
                    model="ConstructionProgress",
                )

            allowed_queryset = self.permissions.get_allowed_queryset()
            if "none" in allowed_queryset:
                queryset = join_queryset(queryset, ConstructionProgress.objects.none())
            if "all" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ConstructionProgress.objects.filter(
                        construction__company_id=user_company
                    ),
                )
            if "supervisor_agency" in allowed_queryset:
                queryset = join_queryset(
                    queryset,
                    ConstructionProgress.objects.filter(
                        construction__company_id=user_company,
                        construction__origin="AGENCY",
                    ),
                )

        # If queryset isn't set by any means above
        if queryset is None:
            user_companies = self.request.user.companies.all()
            queryset = ConstructionProgress.objects.filter(
                construction__company__in=user_companies
            )

        return self.get_serializer_class().setup_eager_loading(queryset.distinct())

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def has_necessary_query_params(self, query_params: list):
        # check necessary params
        return any(
            [
                self.request.query_params.get(query_param) is not None
                for query_param in query_params
            ]
        )
