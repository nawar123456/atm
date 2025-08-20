# core/utils.py

from django.core.mail import send_mail
from django.conf import settings

def send_otp_email(email, otp):
    """
    إرسال رمز OTP إلى البريد الإلكتروني
    """
    subject = "رمز التحقق (OTP) لحسابك"
    message = f"""
    مرحباً،

    رمز التحقق الخاص بك هو: {otp}

    يُرجى استخدام هذا الرمز لتفعيل حسابك.

    شكرًا،
    فريق الدعم
    """
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )