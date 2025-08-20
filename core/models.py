# core/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.conf import settings
import random

# --- مُحقق هوية الإمارات ---
UAE_ID_REGEX = r'^\d{3}-\d{4}-\d{7}-\d{1}$'
emirates_id_validator = RegexValidator(
    regex=UAE_ID_REGEX,
    message="صيغة الهوية الإماراتية غير صحيحة. يجب أن تكون بالشكل: 784-1995-1234567-1"
)

User = settings.AUTH_USER_MODEL  # ✅ هذا آمن في models.py
def generate_otp():
    return str(random.randint(10000, 99999))

class PasswordResetOTP(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.email} - {self.otp}"
    
class EmailOTP(models.Model):
    email = models.EmailField(unique=True)
    otp = models.CharField(max_length=5)
    created_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.email} - {self.otp}"

    def regenerate_otp(self):
        self.otp = generate_otp()
        self.save()
        return self.otp

# --- نموذج المستخدم ---
class User(AbstractUser):
    passport_number = models.CharField(max_length=15, blank=True,null=True,)

    ROLE_CHOICES = [
        ('user', 'User'),           # مستخدم عادي
        ('delivery', 'Delivery'),   # مندوب التسليم
        ('admin', 'Admin'),         # مدير النظام
    ]

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')

    # البيانات الشخصية
    birth_date = models.DateField(null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)

    # الوثائق
    emirates_id = models.FileField(
        upload_to='documents/emirates_ids/',
        null=True,
        blank=True
    )
    
    passport = models.FileField(
        upload_to='documents/passports/',
        null=True,
        blank=True
    )
    # الصور
    face_scan = models.ImageField(upload_to='face_scans/', null=True, blank=True)

    # الحالة
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('blocked', 'Blocked'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending',null=True, blank=True)

    # التحكم في الوصول
    @property
    def is_approved(self):
        return self.status == 'verified'

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email


# --- نموذج البطاقة ---
class CardDetail(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cards',null=True, blank=True)
    last_four = models.CharField(max_length=4,null=True, blank=True)  # آخر 4 أرقام
    expiry = models.DateField(null=True, blank=True)  # تاريخ كامل: YYYY-MM-DD
    cardholder_name = models.CharField(max_length=100,null=True, blank=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2,null=True, blank=True)  # الرصيد الحالي
    card_number= models.CharField(max_length=20,null=True, blank=True)  # آخر 4 أرقام
    cvv = models.CharField(max_length=5, null=True, blank=True)  # CVV: 3 أو 4 أرقام



    def __str__(self):
        return f"Card ending in {self.last_four}"


# --- نموذج المعاملة ---
class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('withdrawal', 'Withdrawal'),
        ('deposit', 'Deposit'),
        ('send_money', 'Send Money'),
        ('receive_money', 'Receive Money'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    DELIVERY_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
    ]

    # المرسل (مُحدد تلقائيًا حسب نوع المعاملة)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='transactions',
        help_text="المرسل أو صاحب الحساب"
    )

    # المستلم (اختياري)
    recipient = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_transactions'
    )

    # بطاقة الدفع
    card = models.ForeignKey(
        CardDetail,
        on_delete=models.SET_NULL,
        null=True,
        related_name='transactions'
    )

    # نوع المعاملة
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES,null=True, blank=True)

    # المبلغ والعملة
    amount = models.DecimalField(max_digits=12, decimal_places=2,null=True, blank=True)
    amount_to = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    currency_from = models.CharField(max_length=3, default='AED',null=True, blank=True)
    currency_to = models.CharField(max_length=3, default='USD',null=True, blank=True)

    # الحالة
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending',null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True,null=True, blank=True)

    # --- حقول التسليم والموقع ---
    # موقع المرسل
    sender_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    sender_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # موقع المستلم
    recipient_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    recipient_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # مندوب التسليم
    delivery_agent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'delivery'},
        related_name='assigned_deliveries'
    )

    # حالة التسليم
    delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUS_CHOICES, default='pending',null=True, blank=True)

    def __str__(self):
        return f"{self.transaction_type} - {self.amount} {self.currency_from}"

# core/models.py
class DeliveryLocation(models.Model):
    delivery_agent = models.OneToOneField(
    User,
    on_delete=models.CASCADE,
    related_name='location',
    limit_choices_to={'role': 'delivery'})
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    updated_at = models.DateTimeField(auto_now=True)

# --- التوقيع الرقمي ---
class DigitalSignature(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE,null=True, blank=True)
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE,null=True, blank=True)
    signature_data = models.FileField(
        upload_to='documents/signatures/',
        null=True,
        blank=True
    )
    signed_at = models.DateTimeField(auto_now_add=True,null=True, blank=True)

    def __str__(self):
        return f"Signature for Transaction {self.transaction.id}"