import os

import psycopg2
import pytest
from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, connections
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from apps.companies.models import UserInCompany
from apps.permissions.models import UserPermission
from apps.users.models import User

# from apps.permissions.const import usertypes
from helpers.testing import auth_testing

# FIXTURES
pytestmark = pytest.mark.django_db

# PATHS
use_cached_path = "fixtures/temp/use_cached"
db_name_path = "fixtures/temp/db_name"


@pytest.fixture()
def initial_data():
    super_users = User.objects.filter(is_superuser=True, is_staff=True, is_active=True)

    homologator = UserPermission.objects.filter(name="HOMOLOGATOR")

    user_in_companies = UserInCompany.objects.filter(
        permissions__in=homologator, user__in=super_users
    ).first()

    user = user_in_companies.user
    company = user_in_companies.company
    token = auth_testing.get_user_token(user)

    return user, company, token


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


# If set to use cached db and db is configured, use it for tests
if os.path.exists(use_cached_path) and os.path.exists(db_name_path):

    @pytest.yield_fixture(scope="session")
    def django_db_setup():

        # If using cached db and db is configured
        from django.conf import settings

        with open(db_name_path, "r+") as fo:
            temp_db_name = fo.read().strip()

        settings.DATABASES["default"]["NAME"] = "hidros_local_testing"

        run_sql("DROP DATABASE IF EXISTS hidros_local_testing")
        run_sql(
            'CREATE DATABASE hidros_local_testing TEMPLATE "{}"'.format(temp_db_name)
        )

        yield

        for connection in connections.all():
            connection.close()

        run_sql("DROP DATABASE hidros_local_testing")


# Otherwise import fixtures at runtime
else:

    @pytest.fixture(scope="session")
    def django_db_setup(django_db_setup, django_db_blocker):
        with django_db_blocker.unblock():
            import_fixtures()


def import_fixtures():
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


SUBTEST_FIXTURES = [
    "fixtures/specific/200_companies_sub_company_subtest.json",
    "fixtures/specific/201_companies_firm_subtest.json",
    "fixtures/specific/202_companies_userinfirm_subtest.json",
    "fixtures/specific/203_reportings_reporting_subtest.json",
    "fixtures/specific/204_work_plans_job_subtest.json",
]


@pytest.fixture()
def subcompany_subtest_data(db):
    for fixture in SUBTEST_FIXTURES:
        call_command("loaddata", fixture)


@pytest.fixture()
def enable_unaccent():
    connection = connections[DEFAULT_DB_ALIAS]
    cursor = connection.cursor()
    cursor.execute("CREATE EXTENSION IF NOT EXISTS unaccent;")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
