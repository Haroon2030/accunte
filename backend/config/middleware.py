"""
Custom Middleware
"""


class DisableCOOPMiddleware:
    """
    Middleware لإزالة Cross-Origin-Opener-Policy header
    لأنه يسبب تحذيرات في المتصفح عند استخدام HTTP
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # إزالة COOP header إذا كان موجوداً
        if 'Cross-Origin-Opener-Policy' in response:
            del response['Cross-Origin-Opener-Policy']
        return response
