from typing import Dict, Iterable

from django.contrib.gis.db.backends.postgis.schema import PostGISSchemaEditor
from django.db import migrations
from django.db.migrations.state import StateApps
from tqdm import tqdm

from apps.users.models import UserNotification as UserNotificationType


def merge_equivalent_user_notifications(
    apps: StateApps, schema_editor: PostGISSchemaEditor
):
    """
    Now that a UserNotification can hold many Company instances,
    find and merge all UserNotification instances that are equivalent
    when considering their unique_together fields.

    Args:
        apps (StateApps): Django app manager
        schema_editor (PostGISSchemaEditor): Database schema manager
    """

    # Basic model setup
    db_alias = schema_editor.connection.alias
    UserNotification = apps.get_model("users", "UserNotification")

    # Get ordered query to make the loop easier
    unique_fields = ["user", "notification", "notification_type", "time_interval"]
    user_notifications: Iterable[UserNotificationType] = (
        UserNotification.objects.using(db_alias).all().order_by(*unique_fields)
    )

    combination_to_rep_instance: Dict[tuple, UserNotificationType] = {}
    for usr_notif in tqdm(user_notifications):
        # Use unique combination as key
        key = (
            usr_notif.user,
            usr_notif.notification_type,
            usr_notif.notification,
            usr_notif.time_interval,
        )

        # The current usr_notif is going to be the representative instance
        if key not in combination_to_rep_instance:
            combination_to_rep_instance[key] = usr_notif
        # The current usr_notif is going to be deleted after adding
        # its Company instances to the representative instance
        else:
            # Get representative instance
            rep_instance = combination_to_rep_instance[key]

            # IDs of the new Company instances being processed
            new_companies = usr_notif.companies.values_list("uuid", flat=True)

            # Add new Company instances to representative instance
            # NOTE: add() already deals with duplicates
            rep_instance.companies.add(*new_companies)

            # Delete non-representative instance
            usr_notif.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0040_auto_20230809_1117"),
    ]

    operations = [
        migrations.RunPython(
            merge_equivalent_user_notifications, reverse_code=migrations.RunPython.noop
        )
    ]
