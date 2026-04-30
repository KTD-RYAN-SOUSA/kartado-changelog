from django.db import connection, migrations


def reset_notification_sequences(apps, schema_editor):
    with connection.cursor() as cursor:
        # Reset Device model sequence
        cursor.execute(
            """
            SELECT pg_get_serial_sequence('"notifications_device"', 'id');
        """
        )
        device_seq = cursor.fetchone()[0]
        if device_seq:
            cursor.execute("SELECT COALESCE(MAX(id), 1) FROM notifications_device;")
            max_id = cursor.fetchone()[0]
            cursor.execute(f"SELECT setval('{device_seq}', {max_id}, true);")

        # Reset PushNotification model sequence
        cursor.execute(
            """
            SELECT pg_get_serial_sequence('"notifications_pushnotification"', 'id');
        """
        )
        push_seq = cursor.fetchone()[0]
        if push_seq:
            cursor.execute(
                "SELECT COALESCE(MAX(id), 1) FROM notifications_pushnotification;"
            )
            max_id = cursor.fetchone()[0]
            cursor.execute(f"SELECT setval('{push_seq}', {max_id}, true);")


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0005_migrate_userpush_data"),
    ]

    operations = [
        migrations.RunPython(reset_notification_sequences),
    ]
