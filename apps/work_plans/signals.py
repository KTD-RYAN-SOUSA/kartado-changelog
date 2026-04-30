from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from fieldsignals.signals import post_save_changed

from apps.reportings.models import Reporting
from helpers.apps.job import calculate_fields, get_approved_steps_for_progress
from helpers.signals import auto_add_job_number

from .models import Job


@receiver(pre_save, sender=Job)
def job_name_format(sender, instance, **kwargs):
    if instance.number in [None, ""]:
        number = auto_add_job_number(instance.company)

        instance.number = number


@receiver(pre_save, sender=Job)
def update_calculated_fields(sender, instance, **kwargs):
    """
    Update the fields 'progress', 'executed_reportings' and 'reporting_count'
    in the Job model before saving it.

    Only happens on updates to Job. The serializer handles the calculation
    when creating new Jobs.

    If company.metadata['consider_approval_for_job_progress'] is True,
    reportings are only considered "executed" if they are also in an
    approved approval step (defined in company.metadata['approved_approval_steps']).
    """

    # If it's not a pre_save adding a new instance
    # Reference: https://stackoverflow.com/a/31696303
    if not instance._state.adding:
        # Prepare the data
        reportings = instance.reportings.all()
        company = instance.company

        # Get approved steps if feature is enabled
        approved_steps = get_approved_steps_for_progress(company)

        # Calculate the updated fields
        progress, executed_reportings, reporting_count = calculate_fields(
            reportings, company, approved_steps
        )

        # Set the new values
        instance.progress = progress
        instance.executed_reportings = executed_reportings
        instance.reporting_count = reporting_count


@receiver(post_save_changed, sender=Reporting)
def update_calculated_fields_after_reporting_change(
    sender, instance, changed_fields, created, **kwargs
):
    """
    Triggers the update_calculated_fields signal when the associated Reporting
    instance changes its status or approval_step.

    When company.metadata['consider_approval_for_job_progress'] is True,
    changes to approval_step also affect the job progress calculation.
    """

    # If the Reporting has an attached Job
    if instance.job:
        # If the Reporting was just created calculate fields
        if created:
            instance.job.save()
        # Otherwise the Reporting is being updated
        else:
            for field, (old, new) in changed_fields.items():
                # If status or approval_step is among the changed fields, trigger the signal
                if field in ("status", "approval_step"):
                    instance.job.save()
                    break


@receiver(post_delete, sender=Reporting)
def update_calculated_fields_after_reporting_deletion(sender, instance, **kwargs):
    """
    Triggers the update_calculated_fields signal when the associated Reporting
    instance is deleted
    """
    if instance.job:
        instance.job.save()
