import logging
from itertools import product
from typing import Dict, List

import sentry_sdk
from django.db.models.signals import pre_save
from django.utils.timezone import now
from fieldsignals.signals import post_save_changed
from rest_framework_json_api import serializers
from simple_history.utils import bulk_create_with_history
from zappa.asynchronous import task

from apps.companies.models import Company
from apps.occurrence_records.models import OccurrenceType
from apps.reportings.models import (
    Reporting,
    ReportingInReporting,
    ReportingInReportingAsyncBatch,
)
from apps.service_orders.models import ServiceOrderActionStatusSpecs
from apps.users.models import User
from apps.work_plans.const.async_batches import FILTERED, MANUAL
from apps.work_plans.models import Job, JobAsyncBatch
from apps.work_plans.signals import (
    update_calculated_fields,
    update_calculated_fields_after_reporting_change,
)
from helpers.apps.inventory import (
    add_last_monitoring_files_async,
    process_reporting_from_inventory,
)
from helpers.apps.job import (
    calculate_fields,
    get_approved_steps_for_progress,
    get_jobs_to_archive,
    update_reportings_fields,
)


def process_queryset(
    job_queryset,
    archived,
    company,
    remove_unexecuted_reportings,
    executed_status_order,
    user=None,
    approved_approval_steps=None,
):
    """
    Helper function to process either archival or unarchival

    Args:
        job_queryset: QuerySet of Job instances to process
        archived: Boolean indicating whether to archive (True) or unarchive (False)
        company: Company instance
        remove_unexecuted_reportings: Whether to remove unexecuted reportings
        executed_status_order: The order value for executed status
        user: Optional User instance for history tracking
        approved_approval_steps: Optional list of approval step UUIDs for progress calculation
    """
    jobs_to_update = []
    # Jobs that need only progress update (not archival)
    jobs_to_update_progress_only = []
    # Track if we need to update progress fields (for bulk_update)
    needs_progress_update = False

    for job_instance in job_queryset:
        if remove_unexecuted_reportings:
            remove_reportings = []
            for reporting in job_instance.reportings.all():
                try:
                    status_order = ServiceOrderActionStatusSpecs.objects.get(
                        status=reporting.status_id, company=company
                    ).order
                except Exception:
                    continue
                if status_order < executed_status_order:
                    remove_reportings.append(reporting)
            update_reportings_fields(job_instance, user, remove_reportings)
            # NOTE: this is needed because zappa doesn't trigger signals
            job_instance.refresh_from_db()
            (progress, executed_reportings, reporting_count,) = calculate_fields(
                job_instance.reportings.all(), company, approved_approval_steps
            )
            job_instance.progress = progress
            job_instance.executed_reportings = executed_reportings
            job_instance.reporting_count = reporting_count
            needs_progress_update = True

        # When archiving with approval flow enabled, recalculate progress first
        # This ensures jobs that were at 100% before the feature was enabled
        # are properly recalculated considering approval status
        elif archived and approved_approval_steps is not None:
            (progress, executed_reportings, reporting_count,) = calculate_fields(
                job_instance.reportings.all(), company, approved_approval_steps
            )
            job_instance.progress = progress
            job_instance.executed_reportings = executed_reportings
            job_instance.reporting_count = reporting_count
            needs_progress_update = True

            # Skip archiving if progress is no longer 100% after recalculation
            # but still save the updated progress
            if progress < 1:
                jobs_to_update_progress_only.append(job_instance)
                continue

        job_instance.archived = archived
        jobs_to_update.append(job_instance)

    if jobs_to_update:
        update_fields = ["archived"]
        if remove_unexecuted_reportings or needs_progress_update:
            update_fields.extend(["progress", "executed_reportings", "reporting_count"])
        Job.objects.bulk_update(jobs_to_update, update_fields)

    # Update progress for jobs that were not archived (progress < 1 after recalculation)
    if jobs_to_update_progress_only:
        Job.objects.bulk_update(
            jobs_to_update_progress_only,
            ["progress", "executed_reportings", "reporting_count"],
        )


def archive_completed_jobs():
    """
    Dispatches async archiving tasks for all companies with auto_archive_completed_jobs enabled.

    This function runs as a scheduled Zappa task (cron job). Instead of processing
    companies sequentially — which would timeout with a large number of companies —
    it dispatches one async Lambda per company so all run in parallel, each with
    its own timeout.
    """
    companies_with_auto_archive = Company.objects.filter(
        metadata__auto_archive_completed_jobs=True
    )

    for company in companies_with_auto_archive:
        async_archive_completed_jobs_for_company(str(company.pk))


@task
def async_archive_completed_jobs_for_company(company_id):
    """
    Asynchronously archive all completed jobs for a single company.

    Intended to be dispatched once per company during the initial activation of
    auto_archive_completed_jobs (e.g. via data migration), allowing parallel
    Lambda execution instead of a single sequential run.
    """
    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        logging.error(f"Company {company_id} not found for async archive")
        return

    approved_steps = get_approved_steps_for_progress(company)
    job_ids_to_archive = get_jobs_to_archive(company)

    archive_jobs_queryset = Job.objects.filter(
        uuid__in=job_ids_to_archive
    ).prefetch_related("reportings")

    executed_status_order = company.metadata.get("executed_status_order")

    process_queryset(
        archive_jobs_queryset,
        True,
        company,
        remove_unexecuted_reportings=None,
        executed_status_order=executed_status_order,
        user=None,
        approved_approval_steps=approved_steps,
    )


@task
def async_bulk_archive(input_data, company_id, user_id):
    """
    Asynchronously archive or unarchive jobs in bulk.

    This function respects the consider_approval_for_job_progress setting
    when recalculating progress after removing unexecuted reportings.
    """
    archive_jobs_ids = input_data.get("archiveJobs", [])
    unarchive_jobs_ids = input_data.get("unarchiveJobs", [])
    remove_unexecuted_reportings = input_data.get("removeUnexecutedReportings", False)

    try:
        company = Company.objects.get(pk=company_id)
        user = User.objects.get(pk=user_id)
        archive_jobs_queryset = Job.objects.filter(
            uuid__in=archive_jobs_ids, archived=False, company=company
        ).prefetch_related("reportings")
        unarchive_jobs_queryset = Job.objects.filter(
            uuid__in=unarchive_jobs_ids, archived=True, company=company
        ).prefetch_related("reportings")
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logging.error("Error while building job querysets")

    executed_status_order = company.metadata["executed_status_order"]

    # Get approved steps if feature is enabled
    approved_steps = get_approved_steps_for_progress(company)

    process_queryset(
        unarchive_jobs_queryset,
        False,
        company,
        remove_unexecuted_reportings,
        executed_status_order,
        user,
        approved_steps,
    )
    process_queryset(
        archive_jobs_queryset,
        True,
        company,
        remove_unexecuted_reportings,
        executed_status_order,
        user,
        approved_steps,
    )


@task
def async_recalculate_job_progress(company_id):
    """
    Asynchronously recalculate progress for all jobs at 100% for a company.

    This function is called when consider_approval_for_job_progress is enabled,
    to ensure that jobs which were at 100% before the feature was enabled
    are properly recalculated considering approval status.

    Args:
        company_id: UUID string of the company
    """
    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        logging.error(f"async_recalculate_job_progress: Company {company_id} not found")
        return

    # Get approved steps for progress calculation
    approved_steps = get_approved_steps_for_progress(company)

    if approved_steps is None:
        logging.info(
            f"async_recalculate_job_progress: Company {company_id} does not have "
            "consider_approval_for_job_progress enabled, skipping"
        )
        return

    # Get all non-archived jobs at 100% progress
    jobs_at_100 = (
        Job.objects.filter(
            company=company,
            archived=False,
            progress=1,
            reportings__isnull=False,
        )
        .distinct()
        .prefetch_related("reportings")
    )

    jobs_to_update = []
    for job_instance in jobs_at_100:
        (
            progress,
            executed_reportings,
            reporting_count,
        ) = calculate_fields(job_instance.reportings.all(), company, approved_steps)
        # Only update if progress changed
        if (
            job_instance.progress != progress
            or job_instance.executed_reportings != executed_reportings
            or job_instance.reporting_count != reporting_count
        ):
            job_instance.progress = progress
            job_instance.executed_reportings = executed_reportings
            job_instance.reporting_count = reporting_count
            jobs_to_update.append(job_instance)

    if jobs_to_update:
        Job.objects.bulk_update(
            jobs_to_update, ["progress", "executed_reportings", "reporting_count"]
        )
        logging.info(
            f"async_recalculate_job_progress: Updated {len(jobs_to_update)} jobs "
            f"for company {company_id}"
        )
    else:
        logging.info(
            f"async_recalculate_job_progress: No jobs needed update "
            f"for company {company_id}"
        )


def process_job_async_batch():
    """
    Process an existing JobAsyncBatch that's not already in progress by creating the respective Reporting instances
    for each Inventory found (according to the batch type).

    NOTE: This is a schedule Zappa task and will execute every minute.
    NOTE: You can check the configured BATCH_SIZE in apps/work_plans/const/async_batches.py
    NOTE: You can tweak the previously mentioned settings according to the current performance needs.
    """

    batch = (
        JobAsyncBatch.objects.filter(in_progress=False).order_by("created_at").first()
    )
    if batch:
        # Disable Reporting calculated fields signal
        # NOTE: We won't need this signal since the job.save() will take care of this in the last batch
        post_save_changed.disconnect(
            update_calculated_fields_after_reporting_change, sender=Reporting
        )

        # Disable Job calculated fields signal to avoid multiple calls
        # NOTE: This signal should still be called in the final batch
        pre_save.disconnect(update_calculated_fields, sender=Job)

        # Needs to be set in progress to avoid duplicate calls
        # NOTE: Since we are deleting the instance after this, there's no need for setting batch.in_progress = False
        batch.in_progress = True
        batch.save()

        batch_id = str(batch.pk)
        batch_inv_count = batch.inventories.count()
        start_time = now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(
            f"reportings_from_inventory: [{start_time}] Started processing Inventory batch {batch_id} with {batch_inv_count} items"
        )

        job = batch.job
        inventory_to_reporting_id = job.pending_inventory_to_reporting_id
        in_job_status = batch.in_job_status
        user = batch.created_by
        company = batch.company
        approval_step = batch.approval_step
        found_at = batch.found_at
        mappers = company.metadata.get(
            "sheet_inventory_occurrence_type_mapper_for_inspection", []
        )
        inventories = batch.inventories.all().prefetch_related("occurrence_type")
        menu = batch.menu

        created_reps_count = 0
        if batch.batch_type == FILTERED:
            # Get all target OccurrenceType instances using one query
            target_ids: List[str] = [mapper["target"] for mapper in mappers]
            targets = OccurrenceType.objects.filter(pk__in=target_ids)
            target_id_to_instance = {str(ins.pk): ins for ins in targets}

            # Convert the mappers to a lookup friendly version
            origin_to_target: Dict[str, OccurrenceType] = {}
            for mapper in mappers:
                try:
                    origin = mapper["origin"]
                    target = target_id_to_instance[mapper["target"]]

                    if target.occurrence_kind == "2":
                        raise serializers.ValidationError(
                            "kartado.error.inventory.occurrence_type_has_invalid_occurrence_kind"
                        )
                except Exception as e:
                    sentry_sdk.capture_exception(e)
                    continue
                else:
                    origin_to_target[origin] = target

            # Process the Inventory instances by creating the respective Reporting items
            # NOTE: The Reporting will only be present in the dict if the origin was mapped
            inventory_to_new_rep: Dict[str, Reporting] = {}
            for inventory in inventories:
                inventory_id = str(inventory.pk)
                origin = (
                    str(inventory.occurrence_type.pk)
                    if inventory.occurrence_type
                    else None
                )

                if origin in origin_to_target:
                    target = origin_to_target[origin]
                    new_rep = process_reporting_from_inventory(
                        inventory,
                        target,
                        job,
                        in_job_status,
                        user,
                        inventory_to_reporting_id,
                        approval_step,
                        found_at,
                        menu,
                        False,
                    )
                    if new_rep:
                        inventory_to_new_rep[inventory_id] = new_rep
                        created_reps_count += 1
                else:
                    logging.info(
                        f"process_job_async_batch: Skipped Inventory ({str(inventory.pk)}) due to origin not being mapped"
                    )

            # Bulk create the Reporting instances and add to the Job
            new_reps = list(inventory_to_new_rep.values())
            bulk_create_with_history(new_reps, Reporting, default_user=user)

            for rep in new_reps:
                add_last_monitoring_files_async(str(rep.uuid))

            job.reportings.add(*new_reps)
        elif batch.batch_type == MANUAL:
            logging.info("process_job_async_batch: entered manual batch type")
            occurrence_types = batch.occurrence_types.all()
            new_reps = []
            logging.info("process_job_async_batch: before loop")
            for inventory, occ_type in product(inventories, occurrence_types):
                logging.info("process_job_async_batch: start of loop")
                new_rep = process_reporting_from_inventory(
                    inventory,
                    occ_type,
                    job,
                    in_job_status,
                    user,
                    inventory_to_reporting_id,
                    approval_step,
                    found_at,
                    menu,
                    True,
                )
                logging.info("process_job_async_batch: loop after creating new rep")
                if new_rep:
                    logging.info("process_job_async_batch: new_rep exists")
                    new_reps.append(new_rep)
                    created_reps_count += 1

            # Bulk create the Reporting instances and add to the Job
            bulk_create_with_history(new_reps, Reporting, default_user=user)
            logging.info("process_job_async_batch: after bulk create")

            job.reportings.add(*new_reps)
            logging.info("process_job_async_batch: after adding reportings to job")

            for rep in new_reps:
                add_last_monitoring_files_async(str(rep.uuid))

            logging.info("process_job_async_batch: after copying monitoring files")

        else:
            logging.error(
                "process_job_async_batch: Task received an unsupported batch type"
            )

        # Delete the JobAsyncBatch
        batch.delete()
        logging.info("process_job_async_batch: after deleting batch")

        # Enable the Job signal again
        pre_save.connect(update_calculated_fields, sender=Job)

        # If this was the last batch, clear the ref dict
        if job.job_async_batches.count() == 0:
            job.pending_inventory_to_reporting_id = None

            # Trigger the Job signals to recalculate the totals
            job.save()

        end_time = now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(
            f"reportings_from_inventory: [{end_time}] Finished processing Inventory batch {batch_id} and created {created_reps_count} Reporting items"
        )

        # Enable the Reporting signal again
        post_save_changed.connect(
            update_calculated_fields_after_reporting_change, sender=Reporting
        )


def process_job_rep_in_rep_batches():
    """
    Process an existing ReportingInReportingAsyncBatch that's not already in progress by creating the
    respective ReportingInReporting instances for each serialized pending_batch_item.

    NOTE: This is a schedule Zappa task and will execute every minute.
    NOTE: You can check the configured BATCH_SIZE in apps/work_plans/const/async_batches.py
    NOTE: You can tweak the previously mentioned settings according to the current performance needs.
    """

    batch = (
        ReportingInReportingAsyncBatch.objects.filter(
            in_progress=False,
            # Only process the batch if all Inventory batches for that Job are done
            job__job_async_batches__isnull=True,
        )
        .order_by("created_at")
        .first()
    )
    if batch:
        # Disable Reporting calculated fields signal
        # NOTE: We won't need this signal since the job.save() will take care of this in the last batch
        post_save_changed.disconnect(
            update_calculated_fields_after_reporting_change, sender=Reporting
        )

        # Disable Job calculated fields signal to avoid multiple calls
        # NOTE: This signal should still be called in the final batch
        pre_save.disconnect(update_calculated_fields, sender=Job)

        # Needs to be set in progress to avoid duplicate calls
        # NOTE: Since we are deleting the instance after this, there's no need for setting batch.in_progress = False
        batch.in_progress = True
        batch.save()

        batch_id = str(batch.pk)
        pending_batch_items = batch.pending_batch_items
        batch_inv_count = len(pending_batch_items)
        start_time = now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(
            f"reportings_from_inventory: [{start_time}] Started processing Inventory batch {batch_id} with {batch_inv_count} items"
        )

        created_relations_count = 0
        if pending_batch_items:
            for pending_item in pending_batch_items:
                parent, child, relation = pending_item.split(",")

                try:
                    ReportingInReporting.objects.create(
                        parent_id=parent,
                        child_id=child,
                        reporting_relation_id=relation,
                    )
                except Exception as e:
                    logging.warning(
                        "process_job_rep_in_rep_batches: Error while trying to create a new ReportingInReporting with the provided IDs"
                    )
                    sentry_sdk.capture_exception(e)
                else:
                    created_relations_count += 1

        # Delete the JobAsyncBatch
        batch.delete()

        # Enable the Job signal again
        pre_save.connect(update_calculated_fields, sender=Job)

        # Ensure all calculated fields take all new items into account
        if batch.job.rep_in_rep_async_batches.count() == 0:
            batch.job.save()

        end_time = now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(
            f"reportings_from_inventory: [{end_time}] Finished processing ReportingInReporting batch {batch_id} and created {created_relations_count} items"
        )

        # Enable the Reporting signal again
        post_save_changed.connect(
            update_calculated_fields_after_reporting_change, sender=Reporting
        )
