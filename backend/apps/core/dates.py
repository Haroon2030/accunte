"""
تحليل التواريخ من مدخلات المستخدم بأمان.

django.utils.dateparse.parse_date يرمي ValueError (لا يُرجع None) للتاريخ المنسّق جيدًا لكن غير الموجود
مثل 2026-13-99، فيتحول أي مرشح أو حقل تاريخ إلى خطأ 500. هذه الدوال تُرجع None بدلًا من ذلك.
"""
from django.utils.dateparse import parse_date, parse_datetime


def safe_parse_date(value):
    try:
        return parse_date((value or '').strip())
    except (ValueError, TypeError):
        return None


def safe_parse_datetime(value):
    try:
        return parse_datetime((value or '').strip())
    except (ValueError, TypeError):
        return None
