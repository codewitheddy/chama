"""
Desktop-safe CSRF middleware.

Django 4.x's CsrfViewMiddleware rejects POST requests where HTTP_ORIGIN
doesn't match CSRF_TRUSTED_ORIGINS exactly — including the port number.

The desktop app binds to a random port (e.g. http://127.0.0.1:54321), so
the browser sends Origin: http://127.0.0.1:54321 which Django rejects because
CSRF_TRUSTED_ORIGINS only lists http://127.0.0.1 (no port).

This middleware overrides _origin_verified() so that any origin whose
hostname is 127.0.0.1 / localhost is automatically trusted on the desktop app.
The actual CSRF token is still validated — we only skip the origin check.
"""

import os
from urllib.parse import urlparse
from django.middleware.csrf import CsrfViewMiddleware

_is_desktop = bool(os.environ.get('DESKTOP_DB_PATH', ''))

_LOCAL_HOSTS = {'127.0.0.1', 'localhost', '::1'}


class DesktopCsrfMiddleware(CsrfViewMiddleware):
    """
    Drop-in replacement for CsrfViewMiddleware.

    On the desktop app (DESKTOP_DB_PATH set):
      - Any request whose HTTP_ORIGIN hostname is 127.0.0.1 / localhost
        bypasses the origin check. The CSRF token itself is still verified.

    On a real web server (DESKTOP_DB_PATH not set):
      - Behaves identically to the standard CsrfViewMiddleware.
    """

    def _origin_verified(self, request):
        # Standard check first — if Django is happy, we're done
        if super()._origin_verified(request):
            return True

        # On the desktop app, also accept any localhost origin regardless of port
        if _is_desktop:
            origin = request.META.get('HTTP_ORIGIN', '')
            if origin:
                try:
                    hostname = urlparse(origin).hostname or ''
                    if hostname in _LOCAL_HOSTS:
                        return True
                except Exception:
                    pass

        return False
