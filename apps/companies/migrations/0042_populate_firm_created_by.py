from django.db import migrations
from django_bulk_update.helper import bulk_update
from tqdm import tqdm


def determine_firm_creator_field(apps, schema_editor):
    """
    Search inside the Firm's history to determine the user who created it
    and set the created_by field for existing Firms
    """

    db_alias = schema_editor.connection.alias
    Firm = apps.get_model("companies", "Firm")
    HistoricalFirm = apps.get_model("companies", "HistoricalFirm")
    firms = Firm.objects.using(db_alias).filter(created_by__isnull=True)

    # List of updated firms
    updated_firms = []

    for firm in tqdm(firms):
        creator = HistoricalFirm.objects.get(
            uuid=firm.uuid, history_type="+"
        ).history_user

        if creator is not None:
            firm.created_by = creator

            # Add to updated firms
            updated_firms.append(firm)

    # Bulk update the firms in updated_firms
    bulk_update(updated_firms, batch_size=2000, update_fields=["created_by"])


def reset_firm_creator_field(apps, schema_editor):
    """
    Undoes all the changes made in determine_firm_creator_field
    """

    db_alias = schema_editor.connection.alias
    Firm = apps.get_model("companies", "Firm")
    firms = Firm.objects.using(db_alias).filter(created_by__isnull=False)

    # List of updated firms
    updated_firms = []

    for firm in tqdm(firms):
        firm.created_by = None
        updated_firms.append(firm)

    # Bulk update the firms in updated_firms
    bulk_update(updated_firms, batch_size=2000, update_fields=["created_by"])


class Migration(migrations.Migration):

    dependencies = [("companies", "0041_auto_20210514_1013")]

    operations = [
        migrations.RunPython(
            determine_firm_creator_field, reverse_code=reset_firm_creator_field
        )
    ]
