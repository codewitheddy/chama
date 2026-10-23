"""
Middleware that recovers from a stale SQLite database connection.

After a backup restore the live db.sqlite3 file is replaced while the
Django process is still running.  SQLite keeps the old file handle open,
so the very next request gets an OperationalError ("database disk image is
malformed", "unable to open database file", etc.) and returns a 500.

This middleware intercepts those errors, closes every connection in the
pool so Django re-opens them, and retries the request once.  On the second
attempt the fresh handle points to the restored database and everything
works normally.

It is only active when running as the desktop app (DESKTOP_DB_PATH set),
so there is zero overhead in production / web deployments.
"""

import os
from django.db import connections, OperationalError, DatabaseError
from django.contrib.sessions.exceptions import SessionInterrupted
from django.http import HttpResponseRedirect


# Errors that indicate a stale / replaced SQLite file
_STALE_MESSAGES = (
    'database disk image is malformed',
    'unable to open database file',
    'disk image is malformed',
    'no such table',          # new DB doesn't have migrated tables yet
    'database is locked',
)


def _is_stale_connection_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(fragment in msg for fragment in _STALE_MESSAGES)


def _close_all_connections():
    for conn in connections.all():
        try:
            conn.close()
        except Exception:
            pass


class DbReconnectMiddleware:
    """
    On any DB error that looks like a stale SQLite handle problem (e.g. after
    a database restore), close all connections and replay the request once.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        except (OperationalError, DatabaseError) as exc:
            if _is_stale_connection_error(exc):
                # Close stale handles and retry once
                _close_all_connections()
                try:
                    return self.get_response(request)
                except Exception:
                    raise  # second failure → let Django's error handler deal with it
            raise
        except SessionInterrupted:
            # Handle situations where the session row in DB was deleted or replaced
            # (e.g. during a database restore or table clear).
            _close_all_connections()
            try:
                if hasattr(request, 'session'):
                    request.session.flush()
            except Exception:
                try:
                    request.session.clear()
                    request.session._session_key = None
                    request.session.modified = False
                except Exception:
                    pass
            target_url = request.get_full_path() if hasattr(request, 'get_full_path') else '/backup/'
            if '?' not in target_url and getattr(request, 'method', '') == 'POST':
                target_url += '?restored=1'
            return HttpResponseRedirect(target_url or '/')
