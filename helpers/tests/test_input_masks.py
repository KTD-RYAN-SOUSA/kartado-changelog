import pytest

from helpers.input_masks import (
    format_cpf_brazilin,
    format_mobile_number_brazilin,
    format_phone_number_brazilin,
)
from helpers.testing.fixtures import TestBase

pytestmark = pytest.mark.django_db


class TestHelpersInputMask(TestBase):
    model = "Helpers"

    def test_format_mobile_number_brazilin(self):
        # Valid mobile number
        assert format_mobile_number_brazilin("11233334444") == "(11) 23333-4444"

    def test_format_phone_number_brazilin(self):
        # Valid phone number
        assert format_phone_number_brazilin("1122223333") == "(11) 2222-3333"

    def test_format_cpf_brazilin(self):
        # Valid phone number
        assert format_cpf_brazilin("09919929939") == "099.199.299-39"
