import os
from datetime import datetime

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Switches from 'cached' to 'live build database' for tests (and vice versa)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            action="store_true",
            help="Run tests using database generated from fixtures",
        )

    def handle(self, *args, **options):
        message_template = "Cached fixture database {}"

        # Paths
        use_cached_path = "fixtures/temp/use_cached"
        db_name_path = "fixtures/temp/db_name"

        # Scenarios
        use_cached_exists = os.path.exists(use_cached_path)
        db_name_exists = os.path.exists(db_name_path)

        if options["status"]:
            active = os.path.exists(use_cached_path)
            status_message_template = "Cached database is {}"

            if active:
                status = "ACTIVE"
            else:
                status = "INACTIVE"

            self.stdout.write(
                status_message_template.format(self.style.WARNING(status))
            )
        elif use_cached_exists:
            os.remove(use_cached_path)

            self.stdout.write(
                message_template.format(self.style.WARNING("DEACTIVATED"))
            )
        elif db_name_exists:
            with open(use_cached_path, "w+") as file:
                file.write("true")
            self.stdout.write(message_template.format(self.style.WARNING("ACTIVATED")))
        else:
            self.stdout.write(
                self.style.ERROR(
                    "You need to run 'python manage.py cachefixtures 1' and then 'python manage.py cachefixtures 2'"
                    " before running this command."
                )
            )

        # Always show last cached when available
        if db_name_exists:
            # epoch time
            db_name_modified = os.path.getmtime(db_name_path)
            # to datetime
            db_name_modified_date = datetime.fromtimestamp(db_name_modified)
            # to string
            db_name_modified_date = db_name_modified_date.strftime("%Y-%m-%d %H:%M:%S")

            self.stdout.write("Last cached in: {}".format(db_name_modified_date))
