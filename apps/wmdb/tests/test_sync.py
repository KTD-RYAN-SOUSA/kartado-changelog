import json
import time
from copy import deepcopy

import pytest

from apps.reportings.models import Reporting
from helpers.testing.fixtures import TestBase

SCHEMA_VERSIONS = [2, 3]

pytestmark = pytest.mark.django_db


def client_get(client, company, schema_version, lastpulledat, token):
    return client.get(
        path="/WmDBSync/?company={}&page=1&schemaVersion={}&lastPulledAt={}".format(
            str(company.pk), schema_version, lastpulledat
        ),
        content_type="application/vnd.api+json",
        HTTP_AUTHORIZATION="JWT {}".format(token),
        data={},
    )


class TestSyncCreated(TestBase):
    model = "wmdb"

    @pytest.fixture(scope="function")
    def setup_created(self, client):
        inventory = Reporting.objects.filter(
            company=self.company, occurrence_type__occurrence_kind="2"
        ).first()
        new_inventory = deepcopy(inventory)
        new_inventory.pk = None
        new_inventory.save(force_insert=True)

        # Pipeline failure. Wait insert in database to work.
        time.sleep(10)

        return {"inventory": new_inventory}

    def get_inventory(self, client, version):
        response = client_get(client, self.company, version, 0, self.token)
        content = json.loads(response.content)

        return content["changes"]["inventory"]["created"]

    def test_get_created(self, client, setup_created):
        created_pk = str(setup_created["inventory"].pk)

        for version in SCHEMA_VERSIONS:
            response_inventory_created = self.get_inventory(client, version)
            assert response_inventory_created[-1]["id"] == created_pk


class TestSyncUpdated(TestBase):
    model = "wmdb"

    @pytest.fixture(scope="function")
    def setup_updated(self, client):
        response = client_get(client, self.company, SCHEMA_VERSIONS[0], 0, self.token)
        content = json.loads(response.content)

        inventory = Reporting.objects.filter(
            company=self.company, occurrence_type__occurrence_kind="2"
        ).first()
        inventory.save(force_update=True)

        return {"timestamp": content["timestamp"], "inventory": inventory}

    def get_inventory(self, client, version, time_stamp):
        response = client_get(client, self.company, version, time_stamp, self.token)
        content = json.loads(response.content)

        return content["changes"]["inventory"]["updated"]

    def test_get_updated(self, client, setup_updated):
        updated_pk = str(setup_updated["inventory"].pk)

        for version in SCHEMA_VERSIONS:
            response_inventory_updated = self.get_inventory(
                client, version, setup_updated["timestamp"]
            )
            assert response_inventory_updated[0]["id"] == updated_pk


class TestSyncDeleted(TestBase):
    model = "wmdb"

    @pytest.fixture(scope="function")
    def setup_deleted(self, client):
        response = client_get(client, self.company, SCHEMA_VERSIONS[0], 0, self.token)
        content = json.loads(response.content)

        inventory = Reporting.objects.filter(
            company=self.company, occurrence_type__occurrence_kind="2"
        ).first()
        inventory_pk = inventory.pk
        inventory.delete()

        return {"timestamp": content["timestamp"], "inventory_pk": inventory_pk}

    def get_inventory(self, client, version, time_stamp):
        response = client_get(client, self.company, version, time_stamp, self.token)
        content = json.loads(response.content)

        return content["changes"]["inventory"]["deleted"]

    def test_get_deleted(self, client, setup_deleted):
        deleted_pk = str(setup_deleted["inventory_pk"])

        for version in SCHEMA_VERSIONS:
            response_inventory_deleted = self.get_inventory(
                client, version, setup_deleted["timestamp"]
            )
            assert response_inventory_deleted[0] == deleted_pk


class TestSyncLastVersion(TestBase):
    model = "wmdb"

    def test_get(self, client):
        response = client_get(client, self.company, 999, 0, self.token)
        content = json.loads(response.content)
        created = content.get("changes").get("inventory").get("created", dict())

        return len(created) > 0
