from django import template

register = template.Library()

colors = {
    "m": "blue",
    "s": "orange",
}


@register.filter
def gang_color(header_text):
    """Associates a color to each of the user team.
    Example:
        * text-{{ user.gang | gang_color }}-500
    """
    return colors.get(header_text, "base")
