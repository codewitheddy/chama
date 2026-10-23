"""
Custom template filters for Finance Wise TBM.

Usage in templates:
    {% load finance_tags %}
    {{ value|kes }}         → 1,234.56
    {{ value|kes:0 }}       → 1,235  (no decimals)
"""
from django import template
from decimal import Decimal, InvalidOperation

register = template.Library()


@register.filter
def kes(value, decimal_places=2):
    """
    Format a number with thousand separators and fixed decimal places.
    Examples:
        1000      → 1,000.00
        1234567.5 → 1,234,567.50
        None / '' → 0.00
    """
    try:
        decimal_places = int(decimal_places)
        v = Decimal(str(value)) if value not in (None, '', 'None') else Decimal('0')
        # Format with commas and fixed decimals
        quantized = v.quantize(Decimal(10) ** -decimal_places)
        # Build the formatted string manually so it works without babel/humanize
        parts = f'{abs(quantized):,.{decimal_places}f}'
        return f'-{parts}' if quantized < 0 else parts
    except (InvalidOperation, TypeError, ValueError):
        return f'0.{"0" * int(decimal_places)}'
