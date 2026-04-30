from . import version_2, version_3


def get_serializer(number):
    if number == 2:
        return version_2

    return version_3
