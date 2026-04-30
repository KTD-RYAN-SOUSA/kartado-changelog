from django.db.models import IntegerField, Prefetch, Q, Value, prefetch_related_objects
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce
from rest_framework_json_api import serializers
from rest_framework_json_api.relations import (
    ResourceRelatedField,
    SerializerMethodResourceRelatedField,
)

from apps.companies.models import Company, Firm, SubCompany
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import RecordMenu, Reporting
from apps.service_orders.models import ServiceOrderActionStatusSpecs
from apps.users.models import User
from helpers.apps.daily_reports import get_uuids_jobs_user_firms
from helpers.apps.inventory import (
    create_recuperation_from_inspections,
    create_recuperation_items,
    has_sheet_occurrence_type,
    reportings_from_inventory,
    separate_reportings_by_therapy,
)
from helpers.apps.job import (
    calculate_fields,
    get_approved_steps_for_progress,
    update_reportings_fields,
)
from helpers.apps.reportings import reportings_from_inspection
from helpers.fields import ReportingRelatedField
from helpers.mixins import EagerLoadingMixin
from helpers.permissions import PermissionManager
from helpers.serializers import get_field_if_provided_or_present
from helpers.strings import get_obj_from_path

from .models import Job, NoticeViewManager, UserNoticeView
from .notifications import create_job_email, update_job_email


class JobSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    # Only use prefetch (no selects) in order to improve performance under load
    # and make queries lighter on the db
    _PREFETCH_RELATED_FIELDS = [
        # Prefetch only if quantity is within max
        # NOTE: This means that hitting the target WILL OMIT THE INSTANCES for the serializer methods. Remember to refresh the instance for individual operations.
        # NOTE: Not refreshing the instance can cause bugs that are really hard to identify
        Prefetch(
            "reportings",
            queryset=Reporting.objects.exclude(
                Q(job__isnull=True)
                | Q(
                    job__reporting_count__gt=Coalesce(
                        Cast(
                            KeyTextTransform(
                                "max_reportings_by_job", "company__metadata"
                            ),
                            IntegerField(),
                        ),
                        Value(250),
                    )
                ),
            ).only("uuid", "km", "end_km", "job"),
        ),
        "watcher_firms",
        "watcher_users",
        "worker",
        "created_by",
        "company",
        "firm",
        "firm__subcompany",
        "inspection",
        "watcher_subcompanies",
        "job_async_batches",
        "rep_in_rep_async_batches",
    ]

    uuid = serializers.UUIDField(required=False)
    reportings = ResourceRelatedField(
        queryset=Reporting.objects,
        many=True,  # necessary for M2M fields & reverse FK fields,
        required=False,
    )
    inventory = ReportingRelatedField(
        queryset=Reporting.objects,
        many=True,  # necessary for M2M fields & reverse FK fields,
        required=False,
        extra_allowed_types=["Inventory"],
        write_only=True,
    )
    occurrence_type = ResourceRelatedField(
        queryset=OccurrenceType.objects.all(),
        many=True,  # necessary for M2M fields & reverse FK fields,
        required=False,
        write_only=True,
    )
    watcher_firms = ResourceRelatedField(
        queryset=Firm.objects, read_only=False, many=True, required=False
    )
    watcher_users = ResourceRelatedField(
        queryset=User.objects, read_only=False, many=True, required=False
    )
    reason = serializers.CharField(required=False, write_only=True)
    inspection = ResourceRelatedField(
        queryset=Reporting.objects,
        read_only=False,
        many=False,
        required=False,
        write_only=True,
    )
    parent_inventory = ReportingRelatedField(
        many=False,
        read_only=False,
        required=False,
        queryset=Reporting.objects,
        extra_allowed_types=["Inventory"],
        type_lookup_path="occurrence_type.occurrence_kind",
        type_lookup_map={"1": "Reporting", "2": "Inventory"},
        allow_null=True,
    )

    subcompany = SerializerMethodResourceRelatedField(
        model=SubCompany, method_name="get_subcompany", read_only=True, many=False
    )
    watcher_subcompanies = ResourceRelatedField(
        queryset=SubCompany.objects, read_only=False, many=True, required=False
    )
    recuperation_occurrence_types = ResourceRelatedField(
        queryset=OccurrenceType.objects,
        required=False,
        many=True,
        write_only=True,
    )
    menu = ResourceRelatedField(
        queryset=RecordMenu.objects,
        required=False,
        many=False,
        write_only=True,
    )

    processing_async_creation = serializers.SerializerMethodField(read_only=True)
    can_be_synced = serializers.SerializerMethodField(read_only=True)

    add_reportings = ResourceRelatedField(
        queryset=Reporting.objects,
        required=False,
        many=True,
        write_only=True,
    )
    remove_reportings = ResourceRelatedField(
        queryset=Reporting.objects,
        required=False,
        many=True,
        write_only=True,
    )

    class Meta:
        model = Job
        fields = [
            "uuid",
            "company",
            "worker",
            "number",
            "title",
            "description",
            "start_date",
            "end_date",
            "firm",
            "metadata",
            "created_by",
            "reportings",
            "reason",
            "inventory",
            "occurrence_type",
            "progress",
            "watcher_firms",
            "watcher_users",
            "executed_reportings",
            "reporting_count",
            "archived",
            "is_automatic",
            "has_auto_allocated_reportings",
            "inspection",
            "parent_inventory",
            "subcompany",
            "watcher_subcompanies",
            "processing_async_creation",
            "can_be_synced",
            "add_reportings",
            "remove_reportings",
            "recuperation_occurrence_types",
            "menu",
        ]
        read_only_fields = [
            "created_by",
            "progress",
            "executed_reportings",
            "reporting_count",
            "reportings",
            "is_automatic",
            "has_auto_allocated_reportings",
        ]
        extra_kwargs = {
            "inventory": {"write_only": True},
            "occurrence_type": {"write_only": True},
        }

    def get_subcompany(self, obj):
        if obj.firm:
            return obj.firm.subcompany
        return None

    def get_processing_async_creation(self, job: Job):
        """
        We'll consider the async creation as processing both
        when creating batches and when there are still batches to
        be processed
        """
        return (
            job.creating_batches
            or job.job_async_batches.exists()
            or job.rep_in_rep_async_batches.exists()
        )

    def get_can_be_synced(self, job: Job):
        """
        Should the Job be used in mobile syncs?
        Done because syncing huge amounts of Reporting instances can take hours
        and syncing a Job that's processing can be a problem.
        """

        processing_async_creation = self.get_processing_async_creation(job)

        max_reportings_by_job = int(
            job.company.metadata.get("max_reportings_by_job", 250)
        )

        return (
            job.reporting_count <= max_reportings_by_job
            and not processing_async_creation
        )

    def validate(self, data):
        user = self.context["request"].user
        company: Company = get_field_if_provided_or_present(
            "company", data, self.instance
        )
        job_permissions = PermissionManager(
            user=user, company_ids=company.pk, model="Job"
        )

        """
        Validate the filters input by checking the provided occurrence_type
        """
        filters = self.initial_data.get("filters", None)
        if filters is not None and "occurrence_type" not in filters:
            raise serializers.ValidationError(
                "kartado.error.job.if_using_filters_field_provide_occurrence_type_filter"
            )

        """
        If at least one OccurrenceType is the sheet_inventory_occurrence_type, ensure all of them are
        """
        sheet_inventory_occurrence_type = company.metadata.get(
            "sheet_inventory_occurrence_type", None
        )
        if sheet_inventory_occurrence_type and "inventory" in data:
            inventory_data = data["inventory"]
            prefetch_related_objects(inventory_data, "occurrence_type")
            inventory_count = len(inventory_data)
            matching_occ_types = sum(
                1
                for inventory in inventory_data
                if str(inventory.occurrence_type.pk) == sheet_inventory_occurrence_type
            )
            if matching_occ_types > 0 and matching_occ_types < inventory_count:
                raise serializers.ValidationError(
                    "kartado.error.job.invalid_occurrence_type_in_async_creation"
                )

        """
        Check if any reporting is an inventory (occurrence_kind=2)
        Inventories should not be added directly to job reportings list
        """
        reportings_to_validate = list(data.get("reportings", []) or []) + list(
            data.get("add_reportings", []) or []
        )
        if reportings_to_validate:
            prefetch_related_objects(reportings_to_validate, "occurrence_type")
            has_inventory = any(
                r.occurrence_type and r.occurrence_type.occurrence_kind == "2"
                for r in reportings_to_validate
            )
            if has_inventory:
                raise serializers.ValidationError(
                    "kartado.error.inventory_in_job_exception"
                )

        """
        Check if reportings are not in another job
        """
        if (
            not job_permissions.has_permission("can_reschedule")
            and "reportings" in data.keys()
        ):
            jobs = list(set([a.job_id for a in data["reportings"]]))
            if "uuid" in data.keys() and data["uuid"] in jobs:
                jobs.remove(data["uuid"])

            if any(jobs):
                raise serializers.ValidationError(
                    "kartado.error.job.can_reschedule_permission_needed_to_reschedule_this_reporting"
                )

        """
        Check if job is archived
        """
        if (
            self.instance
            and self.instance.archived
            and not ("archived" in data and not data["archived"])
        ):
            raise serializers.ValidationError("kartado.error.job.not_editable")

        return data

    def create(self, validated_data):
        user = self._context["request"].user
        reportings = validated_data.pop("reportings", None)
        occurrence_type_list = validated_data.pop("occurrence_type", [])
        watcher_users = validated_data.pop("watcher_users", [])
        watcher_firms = validated_data.pop("watcher_firms", [])
        watcher_subcompanies = validated_data.pop("watcher_subcompanies", [])
        company = validated_data["company"]
        inspection = validated_data.pop("inspection", None)
        inventory_list = validated_data.pop("inventory", [])
        filters = self.initial_data.pop("filters", {})
        recuperation_occurrence_types = validated_data.pop(
            "recuperation_occurrence_types", []
        )
        menu = validated_data.pop("menu", None)
        is_recuperation_flow = self.initial_data.pop("is_recuperation_flow", False)

        # Calculated fields if the Job is being created from Reportings
        # This is calculated here to spare a "save()"
        # WARN: This only accounts for initial reportings, not for inventory
        if reportings:
            # Get approved steps if feature is enabled
            approved_steps = get_approved_steps_for_progress(company)
            progress, executed_reportings, reporting_count = calculate_fields(
                reportings, company, approved_steps
            )

            # Create new Job with validated and calculated data
            instance = Job.objects.create(
                progress=progress,
                executed_reportings=executed_reportings,
                reporting_count=reporting_count,
                **validated_data
            )
        else:
            # Create new Job with validated data
            instance = Job.objects.create(**validated_data)

        instance.watcher_users.set(watcher_users)
        instance.watcher_firms.set(watcher_firms)
        instance.watcher_subcompanies.set(watcher_subcompanies)

        # Add the inital reportings to the instance if they exist and update old jobs (if they exist)
        job_list_update = []

        if reportings and not (recuperation_occurrence_types or is_recuperation_flow):
            for reporting in reportings:
                if reporting.job:
                    job_list_update.append(reporting.job)

            instance.reportings.add(*reportings)

        job_list_update = list(set(job_list_update))

        # Create the Reporting instances according to the inventory_list
        # NOTE: If filters field is filled, the inventory_list will be automatically defined
        # NOTE: If dealing with sheets, add UUID filter for the provided Inventory items
        if inventory_list and has_sheet_occurrence_type(inventory_list[0], company):
            filters["uuid"] = ",".join(str(inv.pk) for inv in inventory_list)
        is_manual_usage = bool(inventory_list) and bool(occurrence_type_list)
        if filters or is_manual_usage:
            if not menu:
                raise serializers.ValidationError(
                    "kartado.error.work_plans.menu_is_required_creating_this_kind_of_job"
                )

            reportings_from_inventory(
                job=instance,
                inventories_ids=[str(i.pk) for i in inventory_list],
                occurrence_types_ids=[str(i.pk) for i in occurrence_type_list],
                user=user,
                company=instance.company,
                menu=menu,
                filters=filters,
            )

        if recuperation_occurrence_types or is_recuperation_flow:
            # Ensure recuperation creation also includes a menu
            if not menu:
                raise serializers.ValidationError(
                    "kartado.error.work_plans.menu_is_required_when_creating_recuperations"
                )

            reporting_relation_metadata = get_obj_from_path(
                company.metadata, "recuperation_reporting_relation"
            )

            (
                reportings_with_therapy,
                reportings_without_therapy,
            ) = separate_reportings_by_therapy(reportings)

            if reporting_relation_metadata and reportings_with_therapy:
                instance = create_recuperation_from_inspections(
                    reportings_with_therapy, company, user, menu, instance
                )

            if reporting_relation_metadata and reportings_without_therapy:
                instance = create_recuperation_items(
                    reportings_without_therapy,
                    recuperation_occurrence_types,
                    company,
                    user,
                    reporting_relation_metadata,
                    menu,
                    instance,
                )
            instance.save()

        # Create reportings from inspection
        if inspection:
            if not menu:
                raise serializers.ValidationError(
                    "kartado.error.work_plans.menu_is_required_creating_this_kind_of_job"
                )

            reportings_from_inspection(instance, inspection, user, menu)
            instance.save()

        if not (recuperation_occurrence_types or is_recuperation_flow):
            update_reportings_fields(instance, user, add_reportings=reportings)

        # Update old Jobs
        for job_update in job_list_update:
            reportings = job_update.reportings.all()
            company = job_update.company

            # Get approved steps if feature is enabled
            approved_steps = get_approved_steps_for_progress(company)

            # Calculate the updated fields
            progress, executed_reportings, reporting_count = calculate_fields(
                reportings, company, approved_steps
            )

            # Set the new values
            job_update.progress = progress
            job_update.executed_reportings = executed_reportings
            job_update.reporting_count = reporting_count
            job_update.save()

        create_job_email(instance)

        return instance

    def update(self, instance, validated_data):
        # Refresh the instance to avoid problems with the conditional prefetch
        instance.refresh_from_db()

        user = self._context["request"].user
        inventory_list = validated_data.pop("inventory", [])
        occurrence_type_list = validated_data.pop("occurrence_type", [])
        filters = self.initial_data.pop("filters", {})
        if "recuperation_occurrence_types" in validated_data:
            # Keep to avoid errors in the serializer
            validated_data.pop("recuperation_occurrence_types")
        remove_unexecuted_reportings = (
            "remove_unexecuted_reportings" in self.initial_data
            and self.initial_data["remove_unexecuted_reportings"]
        )
        add_reportings = validated_data.pop("add_reportings", [])
        remove_reportings = validated_data.pop("remove_reportings", [])
        menu = validated_data.pop("menu", None)

        # Get Jobs list
        job_list_update = []

        for reporting in add_reportings:
            if reporting.job:
                job_list_update.append(reporting.job)

        job_list_update = list(set(job_list_update))

        # Remove unexecuted Reportings
        if remove_unexecuted_reportings:
            executed_status_order = instance.company.metadata["executed_status_order"]
            for reporting in instance.reportings.all():
                try:
                    status_order = ServiceOrderActionStatusSpecs.objects.get(
                        status=reporting.status, company=instance.company
                    ).order

                except Exception:
                    continue
                if status_order < executed_status_order:
                    remove_reportings.append(reporting)

        # Inventory
        # NOTE: If filters field is filled, the inventory_list will be automatically defined
        # NOTE: If dealing with sheets, add UUID filter for the provided Inventory items
        if inventory_list and has_sheet_occurrence_type(
            inventory_list[0], instance.company
        ):
            filters["uuid"] = ",".join(str(inv.pk) for inv in inventory_list)
        is_manual_usage = bool(inventory_list) and bool(occurrence_type_list)
        if filters or is_manual_usage:
            if not menu:
                raise serializers.ValidationError(
                    "kartado.error.work_plans.menu_is_required_patching_this_kind_of_job"
                )

            reportings_from_inventory(
                job=instance,
                inventories_ids=[str(i.pk) for i in inventory_list],
                occurrence_types_ids=[str(i.pk) for i in occurrence_type_list],
                user=user,
                company=instance.company,
                menu=menu,
                filters=filters,
            )
            # avoid reportings from being removed if empty array is sent
            validated_data.pop("reportings", None)

        # Change reason update
        reason = ""
        if "reason" in validated_data.keys():
            reason = validated_data.pop("reason")
        instance._change_reason = reason

        # Add and remove reportings from request
        if add_reportings:
            instance.reportings.add(*add_reportings)
        if remove_reportings:
            for remove_reporting in remove_reportings:
                try:
                    instance.reportings.remove(remove_reporting)
                except Exception:
                    pass
        validated_data["reportings"] = instance.reportings.all()

        # Update

        instance = super(JobSerializer, self).update(instance, validated_data)

        update_reportings_fields(instance, user, remove_reportings, add_reportings)

        # Update old Jobs
        for job_update in job_list_update:
            job_update.save()

        instance = (
            Job.objects.filter(pk=instance.pk)
            .prefetch_related(*self._PREFETCH_RELATED_FIELDS)
            .first()
        )
        # GET was not loading reporting fields, so adding a refresh_from_db()
        # worked, same as the first line of this method
        instance.refresh_from_db()

        if remove_reportings or add_reportings:
            update_job_email(instance)

        return instance


class JobWithReportingLimitSerializer(JobSerializer):
    """
    Serializer that'll be used on mobile to avoid syncing too many Reporting instances.
    Assumes jobs_rdos_user_firms filter usage.
    """

    is_automatic_sync = serializers.SerializerMethodField(read_only=True)

    class Meta(JobSerializer.Meta):
        fields = JobSerializer.Meta.fields + ["is_automatic_sync"]
        read_only_fields = JobSerializer.Meta.read_only_fields + ["is_automatic_sync"]

    def get_is_automatic_sync(self, job: Job):
        request = self.context.get("request", None)
        jobs_section, _ = request.query_params["jobs_rdos_user_firms"].split("|")

        # Cache UUIDs on first call
        if not hasattr(self, "_cached_automatic_sync_uuids"):
            self._cached_automatic_sync_uuids = (
                get_uuids_jobs_user_firms(
                    jobs_section,
                    job.company,
                    request.user,
                    use_reporting_limit=False,
                )
                if jobs_section
                else []
            )

        return job.pk in self._cached_automatic_sync_uuids


class NoticeViewManagerSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = NoticeViewManager

        fields = ["uuid", "notice", "views_quantity_limit"]


class UserNoticeViewSerializer(serializers.ModelSerializer, EagerLoadingMixin):
    _PREFETCH_RELATED_FIELDS = ["company", "notice_view_manager", "user"]

    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = UserNoticeView
        fields = [
            "uuid",
            "company",
            "notice_view_manager",
            "user",
            "views_quantity",
        ]
