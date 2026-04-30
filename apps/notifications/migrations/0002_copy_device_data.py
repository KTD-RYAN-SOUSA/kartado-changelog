import logging

from django.db import migrations


def copy_devices(apps, schema_editor):
    try:
        OldDevice = apps.get_model("scarface", "Device")
    except LookupError:
        logging.info(
            "Model 'scarface.Device' not found. Ignoring the migration for copy."
        )
        return

    NewDevice = apps.get_model("notifications", "Device")

    new_devices = [
        NewDevice(
            id=old_device.id,
            device_id=old_device.device_id,
            push_token=old_device.push_token,
        )
        for old_device in OldDevice.objects.all()
    ]

    NewDevice.objects.bulk_create(new_devices, batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(copy_devices, reverse_code=migrations.RunPython.noop),
    ]
