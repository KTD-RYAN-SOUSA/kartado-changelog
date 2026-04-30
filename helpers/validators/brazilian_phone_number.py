import re

from django.core.validators import EMPTY_VALUES
from django.forms import ValidationError


def phone_validation(value):
    """
    Validates Brazilian phone number formats. Can either be an string in (XX) XXXX-XXXX or (XX) XXXXX-XXXX format.
    It can also be an 10 or 11 digit number.
    """
    if not isinstance(value, str):
        value = str(value)
    if value in EMPTY_VALUES:
        return ""
    if not value.isdigit():
        value = re.sub("[-\.() ]", "", value)  # noqa
    orig_value = value[:]
    try:
        int(value)
    except ValueError:
        raise ValidationError("kartado.error.phone_need_to_be_digits_only")
    if len(value) != 11 and len(value) != 10:
        raise ValidationError("kartado.error.phone_wrong_digit_count")

    return orig_value
