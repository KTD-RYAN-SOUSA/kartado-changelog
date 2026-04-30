from django import template

register = template.Library()


@register.filter(name="sort_dict_by_key")
def sort_dict_by_key(list_dicts, key):
    return sorted(list_dicts, key=lambda x: x[key])
