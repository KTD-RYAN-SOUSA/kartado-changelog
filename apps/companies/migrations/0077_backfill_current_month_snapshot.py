from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import pytz
from dateutil.relativedelta import relativedelta
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import migrations


def backfill_current_month_snapshot(apps, schema_editor):
    from apps.companies.create_instances_company_model import process_company_usage
    from apps.companies.models import Company

    companies_by_cnpj = list(
        Company.objects.filter(active=True)
        .exclude(cnpj__isnull=True)
        .exclude(cnpj__exact="")
        .exclude(cnpj__contains="00000000000000")
        .exclude(cnpj__contains="00.000.000/0000-00")
        .values("cnpj")
        .annotate(company_uuids=ArrayAgg("uuid"))
    )

    utc = pytz.UTC
    today = date.today()
    end_date = datetime(today.year, today.month, 1, 3, 0).replace(tzinfo=utc)
    next_end_date = end_date + relativedelta(months=1)
    errors = []

    def process(company_group):
        process_company_usage(company_group, end_date, next_end_date)

    with ThreadPoolExecutor(max_workers=16) as executor:
        for cg in companies_by_cnpj:
            executor.submit(process, cg)
        executor.shutdown(wait=True)


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0076_auto_20260325_1722"),
    ]

    operations = [
        migrations.RunPython(
            backfill_current_month_snapshot,
            migrations.RunPython.noop,
        ),
    ]
