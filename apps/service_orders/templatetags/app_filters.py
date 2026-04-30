from django import template

register = template.Library()


@register.filter
def to_abs(value):
    return abs(value)
