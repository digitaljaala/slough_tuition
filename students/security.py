"""Object-level access-control helpers for the Parent Portal.

Every user-scoped read/write must go through these guards so that a logged-in
parent can only ever touch rows that belong to their own User account. Any
attempt to access another user's data raises an immediate 403 PermissionDenied.
"""
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404


def get_owned_or_403(model, owner_field, request, **lookup):
    """Return a single row owned by ``request.user`` or raise 403.

    ``lookup`` is the unique lookup (usually ``pk=``). The row is fetched AND
    filtered by ``owner_field=request.user`` in one query, so a row belonging
    to someone else simply does not match -> get_object_or_404 -> PermissionDenied.
    """
    return get_object_or_404(
        model,
        owner_field=request.user,
        **lookup,
    )


def get_owned_queryset(model, owner_field, request):
    """Return the queryset narrowed to rows owned by ``request.user``.

    Use this to guarantee .get() / .filter() inside a view only ever sees the
    requesting user's own data.
    """
    return model._default_manager.filter(**{owner_field: request.user})


def raise_403_if_not_owned(obj, owner_field, request):
    """Raise PermissionDenied unless ``obj`` belongs to ``request.user``."""
    if getattr(obj, owner_field) != request.user:
        raise PermissionDenied("You do not have permission to access this record.")
