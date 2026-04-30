import os
import re
import shutil
import time

import psycopg2
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS, connections
from dotenv import dotenv_values
from git import Repo
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


class Command(BaseCommand):
    help = "Creates a database using the fixtures to be used with test --fast command"

    def use_temp_db(self):
        # Make a copy of credentials file
        shutil.copy(
            "RoadLabsAPI/settings/credentials.py",
            "RoadLabsAPI/settings/credentials-orig.py",
        )

        with open("fixtures/temp/db_name", "r+") as fo:
            temp_db_name = fo.read()

        with open("RoadLabsAPI/settings/credentials.py", "r+") as fo:
            config = fo.read()

        config = re.sub(
            r"DB_USER,.*.\n",
            '"postgres", "postgres", "localhost", "5432", "{}"\n'.format(temp_db_name),
            config,
        )

        with open("RoadLabsAPI/settings/credentials.py", "w+") as fo:
            fo.write(config)

    def run_sql(self, sql):
        from django.conf import settings

        db = settings.DATABASES["default"]
        conn = psycopg2.connect(
            user=db["USER"],
            password=db["PASSWORD"],
            database="postgres",
            host=db["HOST"],
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        cur.execute(sql)
        conn.close()

    def import_fixtures(self):
        connection = connections[DEFAULT_DB_ALIAS]
        path = "fixtures/fixed/"
        files = [a for a in os.listdir(path) if a.split(".")[-1] == "json"]
        files = [(int(a.split("_")[0]), a) for a in files]
        files = sorted(files, key=lambda x: x[0])
        files = [a[1] for a in files]
        for file in files:
            if file.split(".")[-1] == "json":
                file_path = path + file
                print(file_path)
                cursor = connection.cursor()
                cursor.execute("SET session_replication_role = 'replica';")
                try:
                    call_command("loaddata", file_path)
                except Exception as e:
                    print(e)

        cursor = connection.cursor()
        cursor.execute("SET session_replication_role = 'origin';")

    def restore_credentials(self):
        shutil.move(
            "RoadLabsAPI/settings/credentials-orig.py",
            "RoadLabsAPI/settings/credentials.py",
        )

    def add_arguments(self, parser):
        parser.add_argument(
            "step", nargs="?", type=int, help="Step number to be executed"
        )

    def handle(self, *args, **options):
        step = options["step"]

        # STEP ONE
        if step == 1:
            self.stdout.write(self.style.WARNING("Running step 1..."))

            # Create directory for temp files
            if not os.path.exists("fixtures/temp"):
                os.makedirs("fixtures/temp")

            # Save ref of current branch
            repo = Repo()
            current_ref = str(repo.head.ref)
            with open("fixtures/temp/current_ref", "w+") as fo:
                fo.write(current_ref)

            # Load hash of last commit
            last_commit_hash = repo.head.commit.hexsha

            # Save any work you're doing
            stash_result = repo.git.stash()
            if stash_result != "No local changes to save":
                with open("fixtures/temp/stashed", "w+") as fo:
                    fo.write("true")

            # Go back to when the fixtures were ok
            repo.git.checkout(last_commit_hash)

            # Make sure we're set to run local
            if os.path.exists(".env"):
                env_values = dotenv_values(".env")
                if "STAGE" in env_values and env_values["STAGE"] != "LOCAL":
                    env_values["STAGE"] = "LOCAL"
                    with open(".env", "w+") as fo:
                        for key, value in env_values.items():
                            fo.write("{}={}\n".format(key, value))
                    self.stdout.write(
                        self.style.WARNING(
                            "STAGE was changed to LOCAL inside .env file!"
                        )
                    )
            else:
                with open(".env", "w+") as fo:
                    fo.write("STAGE=LOCAL")

            # Generate a name for the temp database
            temp_db_name = "hidros_temp_{}".format(str(time.time()).split(".")[0])
            with open("fixtures/temp/db_name", "w+") as fo:
                fo.write(temp_db_name)

            # Create the temp database and switch to it through the credentials file
            self.run_sql("DROP DATABASE IF EXISTS {}".format(temp_db_name))
            self.run_sql("CREATE DATABASE {}".format(temp_db_name))

            self.use_temp_db()

            self.stdout.write(
                self.style.WARNING(
                    "Finished running step 1. Now run 'python manage.py cachefixtures 2'."
                )
            )

        # STEP TWO
        elif step == 2:
            self.stdout.write(self.style.WARNING("Running step 2..."))

            repo = Repo()

            # Execute old migrations
            call_command("migrate")

            # Import existing fixtures
            self.import_fixtures()

            # Restore original credentials to avoid conflicts when switching branch
            self.restore_credentials()

            with open("fixtures/temp/current_ref", "r+") as fo:
                current_ref = fo.read().strip()

            # Go back to branch we were working and apply the stash
            repo.git.checkout(current_ref)
            if os.path.exists("fixtures/temp/stashed"):
                repo.git.stash("apply")
                # Remove file after stash is applied
                os.remove("fixtures/temp/stashed")

            self.stdout.write(
                self.style.WARNING(
                    "Finished running step 2. Now run 'python manage.py togglecache' to activate the cache during tests"
                )
            )

        else:
            self.stderr.write(
                self.style.ERROR(
                    "You need to run 'python manage.py cachefixtures 1' and then 'python manage.py cachefixtures 2'."
                )
            )
