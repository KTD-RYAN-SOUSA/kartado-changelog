import json
import os
import re
import shutil
import time

import psycopg2
from django.apps import apps
from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, connections
from git import Repo
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def run_sql(sql):
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


def use_temp_db():
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


def restore_credentials():
    shutil.move(
        "RoadLabsAPI/settings/credentials-orig.py",
        "RoadLabsAPI/settings/credentials.py",
    )


def delete_folder_files(folder):
    for the_file in os.listdir(folder):
        file_path = os.path.join(folder, the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(e)


def step_one():
    # Create directory for temp files
    if not os.path.exists("fixtures/temp"):
        os.makedirs("fixtures/temp")

    # Save ref of current branch
    repo = Repo()
    current_ref = str(repo.head.ref)
    with open("fixtures/temp/current_ref", "w+") as fo:
        fo.write(current_ref)

    # Load hash of commit with which the fixtures were last generated
    with open("fixtures/commit_hash", "r+") as fo:
        fixtures_commit = fo.read().strip()

    # Save any work you're doing
    stash_result = repo.git.stash()
    if stash_result != "No local changes to save":
        with open("fixtures/temp/stashed", "w+") as fo:
            fo.write("true")

    # Go back to when the fixtures were ok
    repo.git.checkout(fixtures_commit)

    # Make sure we're set to run local
    with open(".env", "w+") as fo:
        fo.write("STAGE=LOCAL")

    # Generate a name for the temp database
    temp_db_name = "hidros_temp_{}".format(str(time.time()).split(".")[0])
    with open("fixtures/temp/db_name", "w+") as fo:
        fo.write(temp_db_name)

    # Create the temp database and switch to it through the credentials file
    run_sql("DROP DATABASE IF EXISTS {}".format(temp_db_name))
    run_sql("CREATE DATABASE {}".format(temp_db_name))

    use_temp_db()


# Restart the shell to reload EVERYTHIGN (I couldn't find other way to do it)
def step_two():
    repo = Repo()

    # Execute old migrations
    call_command("migrate")

    # Import existing fixtures
    import_fixtures()

    # Restore original credentials to avoid conflicts when switching branch
    restore_credentials()

    with open("fixtures/temp/current_ref", "r+") as fo:
        current_ref = fo.read().strip()

    # Go back to branch we were working and apply the stash
    repo.git.checkout(current_ref)
    if os.path.exists("fixtures/temp/stashed"):
        repo.git.stash("apply")

    # Switch to temp db
    use_temp_db()


# Restart again
def step_three():

    # Execute new migrations
    call_command("migrate")

    # Get models
    models = apps.get_models()

    # Dump new fixtures
    delete_folder_files("fixtures/fixed")
    models = [
        "{}.{}".format(a._meta.app_label, a._meta.model_name) for a in list(models)
    ]
    excludes = ["admin", "historical", "scarface", "silk"]
    keep = [
        "reportings.historicalreporting",
        "service_orders.administrativeinformation",
    ]
    models = [
        a for a in models if ((not any([b in a for b in excludes])) or (a in keep))
    ]

    def get_recursive_strip(acc, all, field_name):
        try:
            next_object = next(
                a for a in all if a["fields"][field_name] == acc[-1]["pk"]
            )
            acc.append(next_object)
            return get_recursive_strip(acc, all, field_name)
        except StopIteration:
            return acc

    for index, model in enumerate(models):
        # print(model)
        file_name = "fixtures/fixed/{}_{}.json".format(index, model.replace(".", "_"))
        call_command("dumpdata", model, verbosity=0, output=file_name, indent=4)

        # Handle special case for Procedure because of the FK to itself
        if model == "service_orders.procedure":
            with open(file_name, "r+") as fo:
                procedures = json.load(fo)
            first_procedures = [
                a for a in procedures if a["fields"]["procedure_previous"] is None
            ]
            sorted_procedures = []
            for procedure in first_procedures:
                strip = get_recursive_strip(
                    [procedure], procedures, "procedure_previous"
                )
                sorted_procedures += strip
            with open(file_name, "w+") as fo:
                json.dump(sorted_procedures, fo, indent=4)

    restore_credentials()
    delete_folder_files("fixtures/temp")


def import_fixtures():
    connection = connections[DEFAULT_DB_ALIAS]
    path = "fixtures/fixed/"
    files = [a for a in os.listdir(path) if a.split(".")[-1] == "json"]
    # print(files)
    files = [(int(a.split("_")[0]), a) for a in files]
    # print(files)
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
