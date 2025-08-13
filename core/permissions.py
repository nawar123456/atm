# core/permissions.py

from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """
    يسمح فقط للمدراء (role='admin').
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'role') and
            request.user.role == 'admin'
        )


class IsDeliveryStaff(BasePermission):
    """
    يسمح فقط لمندوبي التسليم (role='delivery').
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, 'role') and
            request.user.role == 'delivery'
        )


class IsApprovedUser(BasePermission):
    """
    يسمح فقط للمستخدمين الموثقين (status='verified').
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.status == 'verified'
        )


class IsUserOrAdmin(BasePermission):
    """
    يسمح للمستخدم العادي أو المدير.
    مفيد للعمليات العامة.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return (
            request.user.role == 'user' or
            request.user.role == 'admin' or
            request.user.role == 'delivery'
        )