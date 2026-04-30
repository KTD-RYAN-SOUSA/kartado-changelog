# Generated on 2022-09-01 14:00

from datetime import datetime

from django.db import migrations
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def fill_header_info(apps, schema_editor):

    db_alias = schema_editor.connection.alias
    MultipleDailyReport = apps.get_model("daily_reports", "MultipleDailyReport")

    mdr_qs = MultipleDailyReport.objects.using(db_alias).all()

    updated_items = []

    for mdr in tqdm(mdr_qs):

        header_info = {}

        if (
            hasattr(mdr, "firm")
            and hasattr(mdr.firm, "subcompany")
            and mdr.firm.subcompany is not None
        ):

            subcompany = mdr.firm.subcompany

            office_hirer = subcompany.office
            contract_number = subcompany.contract
            contract_starts_at = (
                subcompany.contract_start_date.strftime("%d/%m/%Y")
                if subcompany.contract_start_date
                else None
            )
            contract_deadline = (
                (subcompany.contract_end_date - mdr.date).days
                if subcompany.contract_end_date
                else None
            )
            contract_execution_days = (
                (mdr.date - subcompany.contract_start_date).days
                if subcompany.contract_start_date
                else None
            )

            construction_name = subcompany.construction_name

            if subcompany.subcompany_type == "HIRING":
                responsibles_hirer = (
                    subcompany.responsible.first_name
                    + " "
                    + subcompany.responsible.last_name
                    if subcompany.responsible is not None
                    else ""
                )
                responsibles_hired = ""
                hirer_name = subcompany.name
                hired_name = ""
            elif subcompany.subcompany_type == "HIRED":
                responsibles_hirer = (
                    subcompany.hired_by_subcompany.responsible.first_name
                    + " "
                    + subcompany.hired_by_subcompany.responsible.last_name
                    if subcompany.hired_by_subcompany.responsible is not None
                    else ""
                )
                responsibles_hired = (
                    subcompany.responsible.first_name
                    + " "
                    + subcompany.responsible.last_name
                    if subcompany.responsible is not None
                    else ""
                )
                hirer_name = subcompany.hired_by_subcompany.name
                hired_name = subcompany.name

            header_info = {
                "office_hirer": office_hirer,
                "contract_number": contract_number,
                "contract_starts_at": contract_starts_at,
                "contract_deadline": contract_deadline,
                "contract_execution_days": contract_execution_days,
                "responsibles_hirer": responsibles_hirer,
                "responsibles_hired": responsibles_hired,
                "object_description": "",
                "construction_name": construction_name,
                "hirer_name": hirer_name,
                "hired_name": hired_name,
            }

        mdr.header_info = header_info

        updated_items.append(mdr)

    bulk_update(updated_items, batch_size=1000, update_fields=["header_info"])


class Migration(migrations.Migration):

    dependencies = [("daily_reports", "0058_merge_20221111_1348")]

    operations = [
        migrations.RunPython(fill_header_info, reverse_code=migrations.RunPython.noop)
    ]
