"""
Custom template filters
"""
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def add(value, arg):
    """Concatenate value with arg"""
    return str(value) + str(arg)
