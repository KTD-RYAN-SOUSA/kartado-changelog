from django.db.models import Count, Prefetch, Sum
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from rest_framework_json_api import serializers

from apps.reportings.models import Reporting
from apps.service_orders.models import ServiceOrderActionStatusSpecs
from apps.work_plans.models import Job
from helpers.histories import bulk_update_with_history


def update_reportings_fields(
    instance, user=None, remove_reportings=None, add_reportings=None
):
    # Updates Reportings status when they are assigned to a Job
    if add_reportings:
        reportings = []
        company = add_reportings[0].company

        try:
            in_job_status = (
                ServiceOrderActionStatusSpecs.objects.filter(company=company, order=2)
                .first()
                .status
            )
        except Exception:
            raise serializers.ValidationError("Job Status não encontrado")

        status_ids = (
            ServiceOrderActionStatusSpecs.objects.filter(company=company, order__lt=2)
            .distinct()
            .values_list("status_id", flat=True)
        )

        for reporting in add_reportings:
            if reporting.status_id in status_ids:
                reporting.status = in_job_status

            reporting.firm = instance.firm
            reporting.job = instance
            reportings.append(reporting)

        if reportings:
            bulk_update_with_history(
                objs=reportings,
                model=Reporting,
                user=user,
                use_django_bulk=True,
            )

    """
    Look at the Reporting history. If its status changed while it was associated with the Job, keep it that way. Otherwise, change the status back to the one it had before it was added to the Job.
    """
    if remove_reportings:
        reportings = []
        for reporting in remove_reportings:
            status_changed = (
                reporting.history.filter(job_id=instance.pk)
                .values_list("status_id", flat=True)
                .distinct()
                .count()
                > 1
            )

            if not status_changed:
                # Get status
                try:
                    status_id = (
                        reporting.history.exclude(job_id=instance.pk).first().status_id
                    )
                except Exception:
                    pass
                else:
                    reporting.status_id = status_id

            # must set to None before update the reporting,
            # create history for removing job
            reporting.job = None
            reportings.append(reporting)

        if reportings:
            bulk_update_with_history(
                objs=reportings,
                model=Reporting,
                user=user,
                use_django_bulk=True,
            )


def total_and_executed_reporting(reportings, company, approved_approval_steps=None):
    """
    Calculate total and executed reportings for a Job.

    Args:
        reportings: QuerySet of Reporting instances
        company: Company instance
        approved_approval_steps: Optional list of approval step UUIDs (strings).
            If provided, a reporting is only considered "executed" if its
            approval_step_id is in this list.

    Returns:
        tuple: (total, executed) counts
    """
    try:
        executed_status_order = company.metadata["executed_status_order"]
    except Exception:
        raise serializers.ValidationError("Company não possui executed_status_order.")

    total = 0
    executed = 0

    # Build query fields based on whether we need approval_step
    query_fields = [
        "uuid",
        "status__status_specs__company",
        "status__status_specs__order",
    ]
    if approved_approval_steps is not None:
        query_fields.append("approval_step_id")

    # Force a fresh query to ensure we get the latest approval_step values
    # This is necessary because the reportings QuerySet may have been cached
    reporting_ids = list(reportings.values_list("uuid", flat=True))
    ser_reportings = (
        Reporting.objects.filter(uuid__in=reporting_ids)
        .prefetch_related(
            "status", "status__status_specs", "status__status_specs__company"
        )
        .values_list(*query_fields)
    )

    processed_reps = []
    executed_reps = []
    for row in ser_reportings:
        if approved_approval_steps is not None:
            rep_id, spec_company, spec_order, approval_step_id = row
        else:
            rep_id, spec_company, spec_order = row
            approval_step_id = None

        str_rep_id = str(rep_id)

        not_processed_yet = str_rep_id not in processed_reps
        not_marked_as_executed_yet = str_rep_id not in executed_reps
        is_executed_order = spec_order and spec_order >= executed_status_order
        company_matches = spec_company and spec_company == company.uuid

        # Check approval status if required
        is_approved = True
        if approved_approval_steps is not None:
            is_approved = str(approval_step_id) in approved_approval_steps

        if not_processed_yet:
            total += 1
            processed_reps.append(str_rep_id)

        if (
            company_matches
            and not_marked_as_executed_yet
            and is_executed_order
            and is_approved
        ):
            executed += 1
            executed_reps.append(str_rep_id)
    return total, executed


def calculate_fields(reportings, company, approved_approval_steps=None):
    """
    Returns the fields 'progress' 'executed_reportings' and 'reporting_count'
    of a Job instance.

    Args:
        reportings: QuerySet or list of Reporting instances
        company: Company instance
        approved_approval_steps: Optional list of approval step UUIDs (strings).
            If provided, a reporting is only considered "executed" if its
            approval_step_id is in this list. This is used when
            company.metadata['consider_approval_for_job_progress'] is True.

    Returns:
        tuple: (progress, executed_reportings, reporting_count)
    """

    # Ensure Reporting instances are inside a QuerySet
    if isinstance(reportings, QuerySet):
        input_reps: QuerySet = reportings
    else:
        id_list = [rep.pk for rep in reportings]
        input_reps: QuerySet = Reporting.objects.filter(pk__in=id_list)

    # Prepare the data
    reporting_count, executed_reportings = total_and_executed_reporting(
        input_reps, company, approved_approval_steps
    )

    # Calculate progress
    try:
        progress = executed_reportings / reporting_count
    except Exception:
        progress = 0

    progress = round(progress, 2)  # round to 2 decimal digits

    return progress, executed_reportings, reporting_count


def get_approved_steps_for_progress(company):
    """
    Get the approved_approval_steps list if the company has
    consider_approval_for_job_progress enabled.

    Args:
        company: Company instance

    Returns:
        list or None: List of approval step UUIDs if feature is enabled,
            None otherwise (to maintain backward compatibility)
    """
    consider_approval = company.metadata.get(
        "consider_approval_for_job_progress", False
    )
    if consider_approval:
        return company.metadata.get("approved_approval_steps", [])
    return None


def get_sync_jobs_info_from_uuids(uuids, company_jobs):
    if len(uuids) == 0:
        return dict()

    jobs = company_jobs.filter(uuid__in=uuids).prefetch_related(
        Prefetch(
            "reportings",
            queryset=Reporting.objects.only("uuid", "reporting_count").prefetch_related(
                "reporting_files"
            ),
        )
    )

    sync_info = jobs.annotate(
        files_count=Count("reportings__reporting_files")
    ).aggregate(
        total=Count("uuid"),
        reportings_total=Coalesce(Sum("reporting_count"), 0),
        reportings_files_total=Coalesce(Sum("files_count"), 0),
    )

    return sync_info


def get_jobs_to_archive(company):
    jobs_to_archive = Job.objects.filter(
        company=company,
        archived=False,
        progress=1,
        reportings__isnull=False,
    )

    return list(set(jobs_to_archive.values_list("uuid", flat=True)))
