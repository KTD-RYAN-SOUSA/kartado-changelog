import re
from datetime import date, datetime

import pytz
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import m2m_changed, post_save, pre_delete
from django.dispatch import receiver
from fieldsignals.signals import pre_save_changed

from apps.companies.models import UserInCompany
from apps.occurrence_records.models import RecordPanel, RecordPanelShowList
from apps.reportings.helpers.default_menus import create_company_menus, create_user_menu
from apps.reportings.models import RecordMenu
from helpers.apps.occurrence_records import handle_record_panel_show

from .models import (
    Company,
    CompanyUsage,
    Firm,
    SingleCompanyUsage,
    UserInFirm,
    UserUsage,
)


@receiver(pre_save_changed, sender=Company)
def update_firms_cnpj(sender, instance, changed_fields, **kwargs):
    if not instance._state.adding:
        for field, (old, new) in changed_fields.items():
            new_value = str(new)
            if field == "cnpj":
                Firm.objects.filter(
                    company=instance, is_company_team=True
                ).select_related("company").update(cnpj=new_value)


@receiver(post_save, sender=UserInCompany)
def create_users_record_menu(sender, instance: UserInCompany, created, **kwargs):
    if created is True:
        create_user_menu(instance.user, instance.company)


@receiver(post_save, sender=Company)
def auto_create_company_menus(sender, instance: Company, created, **kwargs):
    if created is True:
        create_company_menus(instance)


@receiver(pre_save_changed, sender=Company)
def create_active_company_menus(sender, instance, changed_fields, **kwargs):
    if not instance._state.adding:
        for field, (old, new) in changed_fields.items():
            if field == "active":
                if old is False and new is True:
                    has_default_menu = RecordMenu.objects.filter(
                        company=instance, system_default=True
                    ).exists()
                    if not has_default_menu:
                        create_company_menus(instance)


@receiver(pre_delete, sender=UserInFirm)
def delete_panels(sender, instance, **kwargs):

    firm = instance.firm
    user = instance.user
    subcompany = firm.subcompany

    query = Q(viewer_firms=firm) | Q(editor_firms=firm)

    if subcompany:
        query |= Q(viewer_subcompanies=subcompany) | Q(editor_subcompanies=subcompany)
    panels = RecordPanel.objects.filter(query).distinct()

    for panel in panels:
        handle_record_panel_show(RecordPanelShowList, panel, False, user, True)


@receiver(m2m_changed, sender=CompanyUsage.companies.through)
def update_company_usage_auto_companies_fields(
    sender, instance, action, pk_set, **kwargs
):
    if "post" in action:
        company_data = list(instance.companies.values_list("name", "cnpj"))

        instance.cnpj = next((cnpj for _, cnpj in company_data if cnpj), "")
        instance.company_names = [name for name, _ in company_data if name]
        instance.save()


@receiver(post_save, sender=UserUsage)
def update_company_usage_auto_users_fields(sender, instance: UserUsage, **kwargs):
    company_usage = instance.company_usage
    company_usage.user_count = company_usage.user_usages.filter(is_counted=True).count()
    company_usage.save()


def _handle_user_activation_for_billing(uic: UserInCompany):
    """Called when a user is activated. Adds them to the upcoming month's CompanyUsage."""
    user = uic.user
    company = uic.company
    cnpj = company.cnpj

    if not cnpj:
        return

    third_party_patterns = [
        r"@kartado",
        r"@roadlabs",
        r"@hermes",
        r"@[^@]*\.amp\.",
        r"@[^@]*\.ajr\.",
    ]
    if any(re.search(p, user.email, re.IGNORECASE) for p in third_party_patterns):
        return

    utc = pytz.UTC
    today = date.today()
    end_date = datetime(today.year, today.month, 1, 3, 0).replace(tzinfo=utc)
    next_end_date = end_date + relativedelta(months=1)

    company_uuids = list(
        Company.objects.filter(cnpj=cnpj, active=True).values_list("uuid", flat=True)
    )

    with transaction.atomic():
        company_usage, _ = CompanyUsage.objects.get_or_create(
            date=next_end_date.date(),
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

        user_usage, _ = UserUsage.objects.get_or_create(
            user=user, company_usage=company_usage, defaults={"is_counted": False}
        )
        user_usage = UserUsage.objects.select_for_update().get(pk=user_usage.pk)
        if (uic.is_active and user_usage.is_counted) or (
            not uic.is_active and not user_usage.is_counted
        ):
            user_usage.companies = list(
                set(user_usage.companies) | set([str(company.uuid)])
            )
            user_usage.companies.sort()
            user_usage.save()
        elif uic.is_active and not user_usage.is_counted:
            user_usage.companies = [str(company.uuid)]
            user_usage.is_counted = True
            user_usage.save()

        count = (
            UserUsage.objects.filter(
                company_usage=company_usage,
                is_counted=True,
                user__companies_membership__company=company,
            )
            .distinct()
            .count()
        )

        SingleCompanyUsage.objects.update_or_create(
            company_usage=company_usage,
            company=company,
            defaults={"user_count": count},
        )


@receiver(post_save, sender=UserInCompany)
def handle_active_user_for_billing(sender, instance: UserInCompany, created, **kwargs):
    _handle_user_activation_for_billing(instance)
