import pytest

from apps.occurrence_records.const.field_names import get_readable_field_name
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestConst(TestBase):
    model = ""

    def test_readable_function(self, mailoutbox):

        fieldname = get_readable_field_name("company")

        assert fieldname == "Companhia"
