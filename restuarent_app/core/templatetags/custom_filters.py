# core/templatetags/custom_filters.py
from django import template
register = template.Library()

@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except:
        return 0

@register.filter
def percentage(value, perc):
    try:
        return (float(value) * float(perc)) / 100
    except:
        return 0

@register.filter
def repeat(value, count):
    try:
        return str(value) * int(count)
    except:
        return ""
