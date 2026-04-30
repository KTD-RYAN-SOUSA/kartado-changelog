import functools


def rgetattr(obj, attr, *args):
    return functools.reduce(getattr, [obj] + attr.split("."))


def rsetattr(obj, attr, val):
    pre, _, post = attr.rpartition(".")
    return setattr(rgetattr(obj, pre) if pre else obj, post, val)


def reporting_rgetattr(obj, attr, *args):
    if attr[-8:] == "__isnull":
        return False if getattr(obj, attr[:-8]) else True

    return functools.reduce(getattr, [obj] + attr.split("."))
