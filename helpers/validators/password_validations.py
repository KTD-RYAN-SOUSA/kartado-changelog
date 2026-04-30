import re
from difflib import SequenceMatcher
from pathlib import Path

from django.conf import settings
from django.contrib.auth.password_validation import (
    CommonPasswordValidator,
    MinimumLengthValidator,
    NumericPasswordValidator,
    UserAttributeSimilarityValidator,
    exceeds_maximum_length_ratio,
    get_password_validators,
)
from django.core.exceptions import ValidationError


def validate_password(password, user=None, general=False):
    """
    Validate whether the password meets all validator requirements.

    If the password is valid, return ``None``.
    If the password is invalid, raise ValidationError with all error messages.
    """
    password_validators = get_password_validators(settings.AUTH_PASSWORD_VALIDATORS)
    errors = []
    for validator in password_validators:
        try:
            validator.validate(password, user, general=general)
        except ValidationError as error:
            errors.append(error)
    if errors:
        raise ValidationError(errors)


class MinimumLengthValidatorCustom(MinimumLengthValidator):
    def validate(self, password, user=None, general=False):
        if len(password) < self.min_length:
            raise ValidationError("kartado.error.password.need_at_least_eight_chars")


class UserAttributeSimilarityValidatorCustom(UserAttributeSimilarityValidator):
    def validate(self, password, user=None, general=False):
        if not user:
            return

        password = password.lower()
        for attribute_name in self.user_attributes:
            value = getattr(user, attribute_name, None)
            if not value or not isinstance(value, str):
                continue
            value_lower = value.lower()
            value_parts = re.split(r"\W+", value_lower) + [value_lower]
            for value_part in value_parts:
                if exceeds_maximum_length_ratio(
                    password, self.max_similarity, value_part
                ):
                    continue
                if (
                    SequenceMatcher(a=password, b=value_part).quick_ratio()
                    >= self.max_similarity
                ):
                    raise ValidationError(
                        "kartado.error.password.it_cant_be_your_{}".format(
                            attribute_name
                        )
                        if not general
                        else "kartado.error.password.contains_user_personal_info"
                    )


class CommonPasswordValidatorCustom(CommonPasswordValidator):
    DEFAULT_PASSWORD_LIST_PATH = (
        Path(__file__).resolve().parent / "common-passwords.txt.gz"
    )

    def validate(self, password, user=None, general=False):
        if password.lower().strip() in self.passwords:
            raise ValidationError("kartado.error.password.too_common")


class NumericPasswordValidatorCustom(NumericPasswordValidator):
    def validate(self, password, user=None, general=False):
        if password.isdigit():
            raise ValidationError("kartado.error.password.only_numbers")
