# core/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

# إنشاء الراوتر
router = DefaultRouter()

# تسجيل الـ ViewSets
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'transactions', views.TransactionViewSet, basename='transaction')
router.register(r'cards', views.CardDetailViewSet, basename='card')
router.register(r'delivery-locations', views.DeliveryLocationViewSet, basename='delivery-location')

# قائمة الـ URLs
urlpatterns = [
    # -------------------------------
    # Auth & User
    # -------------------------------
    path('api/register/', views.RegisterView.as_view(), name='register'),
    path('api/verify-otp/', views.VerifyOTPView.as_view(), name='verify-otp'),
    path('api/login/', views.LoginView.as_view(), name='login'),
    path('api/password-reset/', views.PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('api/password-reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    # -------------------------------
    # Transactions
    # -------------------------------
    # path('api/transactions/start/', views.TransactionViewSet.as_view({'post': 'start'}), name='transaction-start'),

    # -------------------------------
    # Transfers (send/receive money)
    # -------------------------------
    path('api/transfers/', views.TransferTransactionView.as_view(), name='transfer-create'),

    # -------------------------------
    # Delivery & Verification
    # -------------------------------
    path('api/delivery/payment/', views.PaymentView.as_view(), name='delivery-payment'),
    path('api/delivery/verify-face/', views.FaceIDVerificationView.as_view(), name='verify-face'),
    path('api/delivery/signature/', views.SignatureView.as_view(), name='digital-signature'),

    # -------------------------------
    # Default Router URLs
    # -------------------------------
    path('api/', include(router.urls)),
]