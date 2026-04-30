import pytest

from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestPendingProceduresExport(TestBase):
    model = "PendingProceduresExport"

    ATTRIBUTES = {
        "done": True,
        "filters": {},
    }
