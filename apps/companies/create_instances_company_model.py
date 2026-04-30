import logging
from collections import defaultdict
from datetime import datetime

import pytz
import sentry_sdk
from dateutil.relativedelta import relativedelta
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import DatabaseError, IntegrityError, transaction
from django.utils.timezone import now
from zappa.asynchronous import task

from apps.companies.models import (
    Company,
    CompanyUsage,
    SingleCompanyUsage,
    UserInCompany,
    UserUsage,
)
from helpers.histories import bulk_update_with_history
from helpers.signals import DisableSignals


@task
def create_instances_company_model():
    utc = pytz.UTC
    current_date = now().date()
    current_month = current_date.month
    current_year = current_date.year
    last_month = (current_date - relativedelta(months=1)).month
    start_year = current_year if current_month != 1 else current_year - 1
    start_date = datetime(start_year, last_month, 1, 3, 0).replace(tzinfo=utc)
    end_date = datetime(current_year, current_month, 1, 3, 0).replace(tzinfo=utc)
    next_end_date = end_date + relativedelta(months=1)
    companies_by_cnpj = (
        Company.objects.filter(active=True)
        .exclude(cnpj__isnull=True)
        .exclude(cnpj__exact="")
        .exclude(cnpj__contains="00000000000000")
        .exclude(cnpj__contains="00.000.000/0000-00")
        .values("cnpj")
        .annotate(company_uuids=ArrayAgg("uuid"))
    )

    for company_group in companies_by_cnpj:
        try:
            process_company_usage(company_group, start_date, end_date)
            process_company_usage(company_group, end_date, next_end_date)
        except (DatabaseError, IntegrityError) as e:
            # Re-raise database errors - these are critical
            logging.error(
                f'Database error processing CNPJ {company_group["cnpj"]}: {str(e)}'
            )
            sentry_sdk.capture_exception(e)
            continue
        except Exception as e:
            # Log and continue for non-database errors
            logging.error(f'Error processing CNPJ {company_group["cnpj"]}: {str(e)}')
            sentry_sdk.capture_exception(e)
            # Continue with next company instead of failing entire task
            continue


def process_company_usage(company_group, start_date, end_date):
    """Extracted function to properly handle atomic transactions"""
    with transaction.atomic():
        cnpj = company_group["cnpj"]
        company_uuids = company_group["company_uuids"]

        company_usage, created = CompanyUsage.objects.get_or_create(
            date=end_date.date(),
            cnpj=cnpj,
            defaults={
                "company_names": list(
                    Company.objects.filter(uuid__in=company_uuids).values_list(
                        "name", flat=True
                    )
                ),
                "user_count": 0,
            },
        )

        company_usage.companies.add(*company_uuids)

        uic_list = (
            UserInCompany.objects.filter(company__cnpj=cnpj)
            .exclude(user__email__icontains="@kartado")
            .exclude(user__email__icontains="@roadlabs")
            .exclude(user__email__icontains="@hermes")
            .exclude(user__email__iregex=r"@[^@]*\.amp\.")
            .exclude(user__email__iregex=r"@[^@]*\.ajr\.")
            .prefetch_related("user", "company")
            .order_by("user")
        )

        active_users, inactive_users = get_history_per_company(
            uic_list, start_date, end_date
        )

        active_count_by_company = defaultdict(int)
        update_user_usage = set()

        with DisableSignals():
            for user in active_users:
                user_company_objs = list(
                    Company.objects.filter(
                        cnpj=cnpj,
                        userincompany__user=user,
                    ).only("uuid", "name")
                )
                user_companies = [str(c.uuid) for c in user_company_objs]
                for company_obj in user_company_objs:
                    active_count_by_company[company_obj] += 1
                usage, created = UserUsage.objects.get_or_create(
                    user=user,
                    company_usage=company_usage,
                    defaults={"is_counted": True, "companies": user_companies},
                )
                if not created:
                    if usage.is_counted is False:
                        usage.is_counted = True
                        update_user_usage.add(usage)
                    if set(usage.companies) != set(user_companies):
                        usage.companies = user_companies
                        update_user_usage.add(usage)

            for user in inactive_users:
                user_companies = [
                    str(c.uuid)
                    for c in Company.objects.filter(
                        cnpj=cnpj,
                        userincompany__user=user,
                    ).only("uuid", "name")
                ]
                usage, created = UserUsage.objects.get_or_create(
                    user=user,
                    company_usage=company_usage,
                    defaults={"is_counted": False, "companies": user_companies},
                )
                if not created:
                    if usage.is_counted is True:
                        usage.is_counted = False
                        update_user_usage.add(usage)
                    if set(usage.companies) != set(user_companies):
                        usage.companies = user_companies
                        update_user_usage.add(usage)

        update_user_usage = list(update_user_usage)
        if update_user_usage:
            bulk_update_with_history(
                update_user_usage, UserUsage, batch_size=50, use_django_bulk=True
            )

        company_usage.refresh_from_db()
        company_usage.user_count = len(active_users)
        company_usage.save()

        # Criar/atualizar SingleCompanyUsage para cada company do CNPJ
        for company_obj, active_count in active_count_by_company.items():
            SingleCompanyUsage.objects.update_or_create(
                company_usage=company_usage,
                company=company_obj,
                defaults={"user_count": active_count},
            )


def get_history_per_company(uic_list, start_date, end_date):
    companies = list(set(uic_list.values_list("company__name", flat=True)))

    # If there's only one company in the same CNPJ
    if len(companies) == 1:
        active_users, inactive_users = get_user_status(uic_list, start_date, end_date)

    # If there's more than one company, we have to see all possibilites, e.g., if user is active in one company and inactive in another
    else:
        active_users, inactive_users, = (
            [],
            [],
        )
        for company in companies:
            uic_list_filtered = uic_list.filter(company__name=company)

            company_active, company_inactive = get_user_status(
                uic_list_filtered, start_date, end_date
            )

            active_users.extend(company_active)
            inactive_users.extend(company_inactive)

        inactive_users = list(
            set([user for user in inactive_users if user not in active_users])
        )
        active_users = list(set(active_users))

    return active_users, inactive_users


def get_user_status(uic_list, start_date, end_date):
    active_users = []
    inactive_users = []

    for uic in uic_list:
        try:
            # Check if user was created after search period
            user_created_after_period = False

            # Look for first history
            first_record = uic.history.filter(history_type="+").first()
            if first_record and first_record.history_date > end_date:
                # User was created after period
                user_created_after_period = True

            if user_created_after_period:
                # User will be ignored
                continue

            active_during_period = is_user_active(uic, start_date, end_date)

            # Adding to the list
            if active_during_period:
                if uic.user not in active_users:
                    active_users.append(uic.user)
            else:
                if uic.user not in inactive_users:
                    inactive_users.append(uic.user)

        except Exception as e:
            logging.error(f'Error in "get_user_status" function: {str(e)}')
            sentry_sdk.capture_exception(e)

    return active_users, inactive_users


def is_user_active(uic, start_date, end_date):
    # Not active until found otherwise
    active_during_period = False

    # Case 1: Checking if user is currently active
    if uic.is_active:
        active_during_period = True

    # Case 2: Checking if user was activated between the dates
    elif uic.history.filter(
        is_active=True,
        user=uic.user,
        history_date__gte=start_date,
        history_date__lte=end_date,
    ).exists():
        active_during_period = True

    # Case 3: Checking if user was deactivated (meaning the user was active during the period)
    elif (
        uic.history.filter(
            is_active=False,
            user=uic.user,
            history_date__gte=start_date,
            history_date__lte=end_date,
        )
        .exclude(history_type="+")
        .exists()
    ):
        active_during_period = True

    # Case 4: Checking if user was deactivated after the period (meaning the user was active during)
    elif (
        uic.history.filter(is_active=False, user=uic.user, history_date__gt=end_date)
        .exclude(history_type="+")
        .exists()
    ):
        active_during_period = True

    return active_during_period
