from .services import reset_request, set_request


class AuditContextMiddleware:
    """يحفظ الطلب الحالي ليستعمله log_action لالتقاط المستخدم وIP."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_request(request)
        try:
            return self.get_response(request)
        finally:
            reset_request(token)
