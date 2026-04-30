import os
from collections import OrderedDict
from datetime import datetime

import sentry_sdk
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import ResourceRelatedField

from apps.constructions.helpers import get_percentage_done as gp
from apps.files.models import File
from apps.reportings.models import Reporting, ReportingFile
from helpers.mixins import EagerLoadingMixin
from helpers.serializers import get_field_if_provided_or_present
from helpers.strings import get_obj_from_path

from .models import Construction, ConstructionProgress


class ConstructionSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = [
        "construction_progresses",
        "files",
        "company",
        "created_by",
    ]

    uuid = serializers.UUIDField(required=False)
    phases = serializers.JSONField(required=False)
    spend_schedule = serializers.JSONField(required=False)
    files = ResourceRelatedField(many=True, required=False, read_only=True)

    # Serializer method fields
    construction_rate = serializers.SerializerMethodField()
    executed_in_month = serializers.SerializerMethodField()
    current_total = serializers.SerializerMethodField()
    last_progress = serializers.SerializerMethodField()
    shared_with_agency = serializers.SerializerMethodField()

    class Meta:
        model = Construction
        fields = [
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
            "phases",
            "spend_schedule",
            "files",
            # Serializer method fields
            "construction_rate",
            "executed_in_month",
            "current_total",
            "last_progress",
            "origin",
            "shared_with_agency",
        ]
        read_only_fields = [
            "created_by",
            "files",
            "shared_with_agency",
        ]

    def get_shared_with_agency(self, obj):
        try:
            return obj in self.context["view"].queryset_to_verify
        except Exception:
            return False

    def validate(self, attrs):
        period_names = ["scheduling", "analysis", "execution", "spend_schedule"]
        error_template = "{} deve ser maior que {}"

        for name in period_names:
            start_key = name + "_start_date"
            end_key = name + "_end_date"

            start_date = (
                attrs[start_key]
                if start_key in attrs
                else getattr(self.instance, start_key)
            )
            end_date = (
                attrs[end_key] if end_key in attrs else getattr(self.instance, end_key)
            )

            if start_date > end_date:
                raise serializers.ValidationError(
                    error_template.format(end_key, start_key)
                )
        # expected_amount validation
        phases = get_field_if_provided_or_present("phases", attrs, self.instance)
        if phases:
            for phase in phases:
                if "subphases" in phase:
                    for subphase in phase["subphases"]:
                        if (
                            "expected_amount" in subphase
                            and (
                                subphase["expected_amount"] is None
                                or subphase["expected_amount"] <= 0
                            )
                        ) or ("expected_amount" not in subphase):
                            raise serializers.ValidationError(
                                "kartado.error.construction.subphase_has_invalid_expected_amount"
                            )
        return super().validate(attrs)

    def calculate_month_schedule(self, obj):
        spend_schedule = obj.spend_schedule
        construction_phases = obj.phases
        const_progs = obj.construction_progresses.all()
        if not spend_schedule or not construction_phases or not const_progs:
            return {}

        # Order schedule by month and year
        ordered_spend_schedule = OrderedDict()

        def schedule_sorter(item):
            return datetime.strptime(item, "%m/%Y")

        sorted_keys = sorted(spend_schedule, key=schedule_sorter)
        for sorted_key in sorted_keys:
            ordered_spend_schedule[sorted_key] = spend_schedule[sorted_key]

        # Determine key for this month
        now = timezone.now()
        now_date_key = now.strftime("%m/%Y")

        # Determine date key to be used
        # NOTE: uses last entry in schedule if current month is not in schedule
        ord_spend_schedule_keys = list(ordered_spend_schedule.keys())
        relevant_date_key = (
            now_date_key
            if now_date_key in spend_schedule
            else ord_spend_schedule_keys[-1]
        )

        # Handle schedule
        resp_schedule = OrderedDict()
        for date_key, expected_month in ordered_spend_schedule.items():
            date_key_datetime = datetime.strptime(date_key, "%m/%Y")

            # Get latest progress for that date
            month_progs = [
                prog
                for prog in const_progs
                if prog.executed_at.month == date_key_datetime.month
                and prog.executed_at.year == date_key_datetime.year
            ]
            date_key_prog = max(
                month_progs, default=None, key=lambda prog: prog.executed_at
            )

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

                    try:
                        phase = construction_phases[phase_i]
                        subphase = construction_phases[phase_i]["subphases"][subphase_i]
                    except IndexError:
                        sentry_sdk.capture_exception(
                            serializers.ValidationError(
                                "kartado.error.construction.detail_has_phase_or_subphase_index_out_of_range"
                            )
                        )
                        return {}

                    # Convert weights to decimal
                    phase_weight = phase["weight"] / 100
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

        return resp_schedule[relevant_date_key]

    def get_executed_in_month(self, obj):
        month_schedule = self.calculate_month_schedule(obj)
        if "executed_month" in month_schedule:
            return month_schedule["executed_month"]
        else:
            return None

    def get_current_total(self, obj):
        month_schedule = self.calculate_month_schedule(obj)
        if "executed" in month_schedule:
            return month_schedule["executed"]
        else:
            return None

    def get_construction_rate(self, obj):
        month_schedule = self.calculate_month_schedule(obj)
        construction_rate = None
        if "expected_month" in month_schedule and "executed_month" in month_schedule:
            month_expected = month_schedule["expected_month"]
            month_executed = month_schedule["executed_month"]

            if month_executed >= month_expected:
                construction_rate = "regular"
            elif month_executed == 0.0:
                construction_rate = "stuck"
            elif month_executed < month_expected:
                construction_rate = "slow"

        return construction_rate

    def get_last_progress(self, obj):
        if obj.construction_progresses.count() > 0:
            latest_progress = obj.construction_progresses.order_by("executed_at").last()
            return latest_progress.executed_at
        else:
            return None


class ConstructionProgressSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _SELECT_RELATED_FIELDS = ["construction", "created_by"]
    _PREFETCH_RELATED_FIELDS = ["reportings", "files"]

    uuid = serializers.UUIDField(required=False)
    progress_details = serializers.JSONField(required=False)
    reportings = ResourceRelatedField(
        queryset=Reporting.objects, required=False, many=True
    )
    files = ResourceRelatedField(many=True, required=False, read_only=True)

    class Meta:
        model = ConstructionProgress
        fields = [
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
        read_only_fields = ["created_at", "created_by", "files"]

    def handle_reporting_files(self, instance):
        reporting_files = self.initial_data.get("reporting_files", None)
        deferred_objs = []
        if reporting_files:
            try:
                construction_progress_type = ContentType.objects.get(
                    app_label="constructions", model="constructionprogress"
                )
                for reporting_file in reporting_files:
                    rep_file_uuid = reporting_file["id"]
                    rep_file_instance = ReportingFile.objects.get(pk=rep_file_uuid)

                    file_fields = [
                        "description",
                        "md5",
                        "upload",
                        "uploaded_at",
                        "datetime",
                        "created_by",
                        "kind",
                    ]
                    file_kwargs = {
                        field_name: getattr(rep_file_instance, field_name)
                        for field_name in file_fields
                    }

                    # Fields not present in the ReportingFile
                    file_kwargs["content_type"] = construction_progress_type
                    file_kwargs["object_id"] = instance.uuid

                    deferred_objs.append(File(**file_kwargs))
            except KeyError:
                raise serializers.ValidationError(
                    "kartado.error.construction_progress.malformed_reporting_file_relationship"
                )
            except ReportingFile.DoesNotExist:
                raise serializers.ValidationError(
                    "kartado.error.reporting_file.reporting_file_does_not_exist"
                )
            except Exception as e:
                sentry_sdk.capture_exception(e)
                raise serializers.ValidationError(
                    "kartado.error.construction_progress.error_while_creating_file_instances"
                )

            for obj in deferred_objs:
                obj.save()
                instance.files.add(obj)

    def create(self, validated_data):
        instance = super().create(validated_data)
        self.handle_reporting_files(instance)

        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self.handle_reporting_files(instance)

        return instance


class CustomConstructionProgressSerializer(
    serializers.ModelSerializer, EagerLoadingMixin
):
    _PREFETCH_RELATED_FIELDS = ["reportings", "files"]

    responsible = serializers.SerializerMethodField()
    percentage_done = serializers.SerializerMethodField()
    amount_photos = serializers.SerializerMethodField()
    amount_reportings = serializers.SerializerMethodField()
    amount_files = serializers.SerializerMethodField()
    files = ResourceRelatedField(many=True, required=False, read_only=True)

    class Meta:
        model = ConstructionProgress
        fields = [
            "uuid",
            "name",
            "executed_at",
            "files",
            "responsible",
            "amount_photos",
            "amount_reportings",
            "amount_files",
            "percentage_done",
        ]

    def get_responsible(self, obj):
        responsible = ""
        try:
            last_phase = obj.progress_details[-1]
        except Exception:
            return ""
        last_phase = last_phase.get("phase")
        if last_phase is None:
            return responsible

        try:
            return obj.construction.phases[last_phase]["responsible"]
        except Exception:
            return responsible

    def get_percentage_done(self, obj):
        return gp(obj)

    def get_amount_photos(self, obj):
        amount = 0
        VALID_EXTENSIONS = [
            ".jpg",
            ".jpeg",
            ".ico",
            ".gif",
            ".png",
            ".svg",
            ".psd",
            ".webp",
            ".raw",
            ".tiffbmp",
        ]
        for file in obj.files.all():
            try:
                _, file_extension = os.path.splitext(file.upload.name)
            except Exception:
                continue
            if file_extension in VALID_EXTENSIONS:
                amount += 1
        return amount

    def get_amount_files(self, obj):
        amount = 0
        VALID_EXTENSIONS = [
            ".jpg",
            ".jpeg",
            ".ico",
            ".gif",
            ".png",
            ".svg",
            ".psd",
            ".webp",
            ".raw",
            ".tiffbmp",
        ]
        for file in obj.files.all():
            try:
                _, file_extension = os.path.splitext(file.upload.name)
            except Exception:
                continue
            if file_extension not in VALID_EXTENSIONS:
                amount += 1
        return amount

    def get_amount_reportings(self, obj):
        return obj.reportings.count()
