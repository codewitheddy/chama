"""
Stores the current request in a thread-local so signals can access
the logged-in user and IP address without needing request in their scope.
"""
import threading

_thread_locals = threading.local()


def get_current_user():
    return getattr(_thread_locals, 'user', None)


def get_current_ip():
    return getattr(_thread_locals, 'ip', None)


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.user = request.user if request.user.is_authenticated else None
        _thread_locals.ip   = self._get_ip(request)
        try:
            response = self.get_response(request)
        finally:
            _thread_locals.user = None
            _thread_locals.ip   = None
        return response

    @staticmethod
    def _get_ip(request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
