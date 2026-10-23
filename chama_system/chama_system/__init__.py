# Python 3.14 compatibility patch for Django Context copy in test client
try:
    from django.template import context as django_context

    def _safe_context_copy(self):
        duplicate = self.__class__.__new__(self.__class__)
        duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    django_context.BaseContext.__copy__ = _safe_context_copy
    django_context.Context.__copy__ = _safe_context_copy
    django_context.RequestContext.__copy__ = _safe_context_copy
except Exception:
    pass
