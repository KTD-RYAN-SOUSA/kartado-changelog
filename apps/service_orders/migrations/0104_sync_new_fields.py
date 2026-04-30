from django.db import migrations
from django.db.models import Q
from django_bulk_update.helper import bulk_update
from tqdm import tqdm

from apps.service_orders.const import kind_types
from helpers.strings import keys_to_snake_case


def migrate_data_new_fields(apps, schema_editor):
    """
    Search inside the Firm's history to determine the user who created it
    and set the created_by field for existing Firms
    """

    db_alias = schema_editor.connection.alias
    App = apps.get_model("service_orders", "ServiceOrder")
    service_orders = (
        App.objects.using(db_alias)
        .filter(kind=kind_types.LAND)
        .filter(
            Q(offender_name__isnull=True)
            | Q(sequencial__isnull=True)
            | Q(identificador__isnull=True)
            | Q(obra__isnull=True)
        )
    ).distinct()

    # List of updated firms
    updated_service_order = []

    for instance in tqdm(service_orders):
        try:
            process_type = instance.get_process_type_display()
            if process_type == "Correção de uso e ocupação":
                main_property = instance.get_main_property()
                attributes = keys_to_snake_case(main_property["attributes"])

                instance.offender_name = instance.get_offender_name()
                instance.sequencial = attributes.get("sequencial", None)
                instance.obra = attributes.get("identificador", None)
                instance.obra = attributes.get("obra", None)

                updated_service_order.append(instance)
        except Exception:
            pass

    bulk_update(
        updated_service_order,
        batch_size=2000,
        update_fields=["obra", "sequencial", "identificador", "offender_name"],
    )


def revese_code(apps, schema_editor):
    """
    Undoes all the changes made in determine_firm_creator_field
    """

    db_alias = schema_editor.connection.alias
    App = apps.get_model("service_orders", "ServiceOrder")
    service_orders = (
        App.objects.using(db_alias)
        .filter(kind=kind_types.LAND)
        .filter(
            Q(offender_name__isnull=False)
            | Q(sequencial__isnull=False)
            | Q(identificador__isnull=False)
            | Q(obra__isnull=False)
        )
    ).distinct()

    # List of updated firms
    updated_service_order = []

    for instance in tqdm(service_orders):
        try:
            process_type = instance.get_process_type_display()
            if process_type == "Correção de uso e ocupação":
                instance.offender_name = None
                instance.sequencial = None
                instance.obra = None
                instance.obra = None

                updated_service_order.append(instance)
        except Exception:
            pass

    bulk_update(
        updated_service_order,
        batch_size=2000,
        update_fields=["obra", "sequencial", "identificador", "offender_name"],
    )


class Migration(migrations.Migration):
    dependencies = [
        ("service_orders", "0103_auto_20240422_1157"),
    ]
    operations = [
        migrations.RunPython(migrate_data_new_fields, reverse_code=revese_code)
    ]
