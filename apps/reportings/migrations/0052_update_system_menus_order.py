""" 
The signal version of this logic works as expected but the original migration written for 
this purpose sets the order to 3 instead of 9999.
"""

from django.db import migrations


def update_system_menus_order(apps, schema_editor):
    RecordMenu = apps.get_model("reportings", "recordmenu")
    db_alias = schema_editor.connection.alias

    RecordMenu.objects.using(db_alias).filter(name="Todos Apontamentos").update(
        order=99999
    )


class Migration(migrations.Migration):

    dependencies = [
        ("reportings", "0051_fill_reportings_menus"),
    ]

    operations = [migrations.RunPython(update_system_menus_order)]
