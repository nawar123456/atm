# core/serializers.py

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction as db_transaction
from .models import User, CardDetail, Transaction, DigitalSignature,DeliveryLocation,EmailOTP,PasswordResetOTP,GuestUser
from decimal import Decimal
from datetime import datetime
import re
import math
from .utils import get_exchange_rate
from django.contrib.auth import get_user_model
from .models import generate_otp
from django.core.cache import cache
from django.core.cache import cache
from django.utils import timezone
import json
User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'email', 'username', 'first_name', 'last_name',
            'phone_number', 'birth_date', 'password','passport_number'
        ]

    def create(self, validated_data):
        # لا نُنشئ المستخدم فورًا
        email = validated_data['email']

        # إنشاء أو تحديث OTP
        otp_code = generate_otp()
        otp_obj, created = EmailOTP.objects.update_or_create(
            email=email,
            defaults={'otp': otp_code}
        )

        # إرسال OTP إلى البريد
        self.send_otp_email(email, otp_code)
        return {'email': email}

  

        # إرجاع البريد فقط (المستخدم لم يُنشَأ بعد)

    def send_otp_email(self, email, otp):
        from django.core.mail import send_mail
        from django.conf import settings

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

# serializers.py
# serializers.py


# serializers.py

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("لا يوجد حساب بهذا البريد الإلكتروني.")
        return value

    def save(self, **kwargs):
        email = self.validated_data['email']

        # توليد OTP
        otp = generate_otp()

        # حفظ أو تحديث OTP
        PasswordResetOTP.objects.update_or_create(
            email=email,
            defaults={'otp': otp}
        )

        # إرسال OTP إلى البريد
        self.send_otp_email(email, otp)

    def send_otp_email(self, email, otp):
        from django.core.mail import send_mail
        from django.conf import settings

        subject = "رمز إعادة تعيين كلمة المرور"
        message = f"""
        مرحباً،

        رمز إعادة تعيين كلمة المرور الخاص بك هو: {otp}

        يُرجى استخدام هذا الرمز لتغيير كلمة المرور.

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

# serializers.py

class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, data):
        email = data['email']
        otp = data['otp']

        try:
            otp_obj = PasswordResetOTP.objects.get(email=email)
        except PasswordResetOTP.DoesNotExist:
            raise serializers.ValidationError("لا يوجد طلب إعادة تعيين لهذا البريد.")

        if otp_obj.otp != otp:
            raise serializers.ValidationError("رمز OTP غير صحيح.")

        # التحقق من انتهاء الصلاحية (15 دقيقة)
        from django.utils import timezone
        if (timezone.now() - otp_obj.created_at).total_seconds() > 900:
            raise serializers.ValidationError("انتهت صلاحية رمز OTP.")

        self.otp_obj = otp_obj
        return data

    def save(self, **kwargs):
        # تغيير كلمة المرور
        user = User.objects.get(email=self.validated_data['email'])
        user.set_password(self.validated_data['new_password'])
        user.save()

        # حذف OTP بعد الاستخدام
        self.otp_obj.delete()

        return user
class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

    def validate(self, data):
        email = data['email']
        otp = data['otp']

        # التحقق من OTP
        try:
            otp_obj = EmailOTP.objects.get(email=email)
        except EmailOTP.DoesNotExist:
            raise serializers.ValidationError("لا يوجد طلب تحقق لهذا البريد.")

        if otp_obj.otp != otp:
            raise serializers.ValidationError("رمز OTP غير صحيح.")

        # التحقق من انتهاء الصلاحية
        if (timezone.now() - otp_obj.created_at).total_seconds() > 900:
            raise serializers.ValidationError("انتهت صلاحية رمز OTP.")

        # ✅ استرجاع البيانات من الذاكرة المؤقتة
        cache_key = f"register_data_{email}"
        register_data = cache.get(cache_key)
        if not register_data:
            raise serializers.ValidationError("الجلسة منتهية الصلاحية. يرجى المحاولة مرة أخرى.")

        self.register_data = register_data
        self.otp_obj = otp_obj
        return data

    def save(self, **kwargs):
        email = self.validated_data['email']
        register_data = self.register_data

        # ✅ إنشاء المستخدم باستخدام البيانات المحفوظة
        user = User.objects.create_user(
            email=email,
            username=register_data['data'].get('username') or email.split('@')[0],
            password=register_data['password'],
            first_name=register_data['data'].get('first_name', ''),
            last_name=register_data['data'].get('last_name', ''),
            phone_number=register_data['data'].get('phone_number', ''),
            birth_date=register_data['data'].get('birth_date'),
            passport_number=register_data['data'].get('passport_number'),
            emirates_id=register_data['data'].get('emirates_id'),
            passport=register_data['data'].get('passport'),
            status='verified',
            role='user'
        )

        # ✅ حذف OTP وبيانات التسجيل
        self.otp_obj.delete()
        cache.delete(f"register_data_{email}")

        return user
def haversine_distance(lat1, lon1, lat2, lon2):
    """
    حساب المسافة بين نقطتين (lat, lon) بالكيلومتر.
    """
    R = 6371  # نصف قطر الأرض

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c




class UserSerializer(serializers.ModelSerializer):
    # password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'username', 'email',
            'password', 'phone_number', 'birth_date', 'emirates_id',
            'passport', 'status', 'role','passport_number'
        ]
        extra_kwargs = {
            'username': {'required': False},
            'email': {'required': False},
            'password': {'required': False},
            'first_name': {'required': False},
            'last_name': {'required': False},
            # يمكنك إضافة باقي الحقول حسب الحاجة
        }

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
       
        instance.save()
        return instance
   
  



class CardDetailSerializer(serializers.ModelSerializer):
    
    # الحقول المطلوبة لإنشاء البطاقة
    card_number = serializers.CharField(write_only=True, max_length=19)
    expiry = serializers.DateField()  # توقع تاريخ كامل

    class Meta:
        model = CardDetail
        fields = [
            'id', 'card_number', 'expiry', 'cardholder_name',
            'last_four', 'balance'
        ]
        # read_only_fields = ['last_four', 'balance']

    # def validate_card_number(self, value):
    #     cleaned = value.replace(' ', '').replace('-', '')
    #     if not re.match(r'^\d{13,19}$', cleaned):
    #         raise serializers.ValidationError("رقم البطاقة غير صالح.")
    #     return cleaned

  

    def create(self, validated_data):
        card_number = validated_data.pop('card_number')
        # expiry_str = validated_data.pop('expiry')

        # تحويل MM/YY إلى تاريخ
        # month, year = map(int, expiry_str.split('/'))
        # full_year = 2000 + year if year < 50 else 1900 + year
        # expiry_date = datetime(full_year, month, 1).date()

        # استخراج آخر 4 أرقام
        last_four = card_number[-4:]

        # إنشاء البطاقة
        card = CardDetail.objects.create(
            # user=self.context['request'].user,
            last_four=last_four,
            # expiry=expiry,
            **validated_data
        )
        return card

class TransactionSerializer(serializers.ModelSerializer):
    recipient_id = serializers.IntegerField(write_only=True, required=False)
    card_id = serializers.PrimaryKeyRelatedField(
        queryset=CardDetail.objects.all(),
        write_only=True
    )
    sender_latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    sender_longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    recipient_latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    recipient_longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    message = serializers.CharField(max_length=255, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    class Meta:
        model = Transaction
        fields = [
            'id',
            'transaction_type',
            'amount',
            'amount_to',
            'currency_from',
            'currency_to',
            'card_id',
            'recipient_id',
            'sender_latitude',
            'sender_longitude',
            'recipient_latitude',
            'recipient_longitude',
            'timestamp',
            'delivery_agent',
            'message',      # ✅ تم الإضافة
            'address',      # ✅ تم الإضافة
        ]
        read_only_fields = ['timestamp']

    def create(self, validated_data):
        transaction_type = validated_data['transaction_type']
        user = self.context['request'].user
        card_id = validated_data.pop('card_id')
        amount = validated_data['amount']
        amount_to = validated_data.get('amount_to')  # يمكن أن يكون None
        message = validated_data.pop('message', '')
        address = validated_data.pop('address', '')
        # ✅ التحقق من أن المبلغ موجب
        if amount <= 0:
            raise serializers.ValidationError({"amount": "يجب أن يكون المبلغ أكبر من صفر."})

        # ✅ التحقق من أن البطاقة تخص المستخدم
        if card_id.user != user:
            raise serializers.ValidationError({
                "error": "لا يمكنك استخدام بطاقة لا تخصك."
            })

        # ✅ التحقق من أن رصيد البطاقة كافٍ
        if card_id.balance < amount:
            raise serializers.ValidationError({
                "error": f"رصيد البطاقة غير كافٍ. الرصيد الحالي: {card_id.balance} {validated_data['currency_from']}"
            })

        # استخراج حقول الموقع
        sender_lat = validated_data.pop('sender_latitude', None)
        sender_lng = validated_data.pop('sender_longitude', None)
        recipient_lat = validated_data.pop('recipient_latitude', None)
        recipient_lng = validated_data.pop('recipient_longitude', None)

        recipient_id = validated_data.pop('recipient_id', None)
        recipient = None
        sender = None

        # التحقق من الموقع حسب نوع المعاملة
        if transaction_type == 'send_money':
            sender = user
            if not recipient_id:
                raise serializers.ValidationError("حقل 'recipient_id' مطلوب عند إرسال الأموال.")
            try:
                recipient = User.objects.get(id=recipient_id)
            except User.DoesNotExist:
                raise serializers.ValidationError("المستخدم المستلم غير موجود.")
            if sender == recipient:
                raise serializers.ValidationError("لا يمكنك إرسال أموال لنفسك.")
            if not all([sender_lat, sender_lng, recipient_lat, recipient_lng]):
                raise serializers.ValidationError("حقلَي الموقع (المرسل والمستقبل) مطلوبان.")

            # ✅ التحقق من أن المستقبل لديه بطاقة
            if not recipient.cards.exists():
                raise serializers.ValidationError({
                    "error": "المستلم لا يملك بطاقة. لا يمكن إرسال الأموال."
                })
        elif transaction_type == 'receive_money':
            sender = None
            if not recipient_id:
                raise serializers.ValidationError("حقل 'recipient_id' يمثل المرسل في حالة الاستلام.")
            try:
                sender = User.objects.get(id=recipient_id)
            except User.DoesNotExist:
                raise serializers.ValidationError("المرسل غير موجود.")
            recipient = user
            if not all([sender_lat, sender_lng, recipient_lat, recipient_lng]):
                raise serializers.ValidationError("حقلَي الموقع (المرسل والمستقبل) مطلوبان.")

            # ✅ التحقق من أن المستقبل (أنا) لديه بطاقة
            if not recipient.cards.exists():
                raise serializers.ValidationError({
                    "error": "ليس لديك بطاقة لتلقي الأموال."
                })

            # ✅ التحقق من أن المرسل لديه بطاقة
            sender_card = sender.cards.first()
            if not sender_card:
                raise serializers.ValidationError({
                    "error": "المرسل لا يملك بطاقة. لا يمكن إتمام العملية."
                })
            if sender_card.balance < amount:
                raise serializers.ValidationError({
                    "error": f"رصيد بطاقة المرسل غير كافٍ. الرصيد الحالي: {sender_card.balance} {currency_from}"
                })
        elif transaction_type == 'withdrawal':
            sender = None
            recipient = user
            if not all([recipient_lat, recipient_lng]):
                raise serializers.ValidationError("حقلَي 'recipient_latitude' و'recipient_longitude' مطلوبان (مكان السحب).")

        elif transaction_type == 'deposit':
            sender = user
            recipient = user
            if not all([sender_lat, sender_lng]):
                raise serializers.ValidationError("حقلَي 'sender_latitude' و'sender_longitude' مطلوبان (مكان الإيداع).")
        else:
            raise serializers.ValidationError("نوع المعاملة غير صالح.")
        
        closest_delivery_agent = None
        min_distance = None
        if recipient_lat and recipient_lng:
            delivery_locations = DeliveryLocation.objects.select_related('delivery_agent').all()

            for location in delivery_locations:
                if not location.delivery_agent.is_approved:
                    continue

                distance = haversine_distance(
                    float(recipient_lat),
                    float(recipient_lng),
                    float(location.latitude),
                    float(location.longitude)
                )

                if min_distance is None or distance < min_distance:
                    min_distance = distance
                    closest_delivery_agent = location.delivery_agent
        # ✅ استخدام المعاملات (atomic) لضمان الأمان
        with db_transaction.atomic():
            # ✅ خصم المبلغ من بطاقة المرسل
            card_id.balance -= amount
            card_id.save(update_fields=['balance'])

            # ✅ إضافة المبلغ إلى بطاقة المستقبل (في حالات send_money و receive_money)
            if transaction_type in ['send_money', 'receive_money']:
        
                # مثال: إذا كانت العمولة 10%، فإن المستقبل يستلم 90%
                currency_from = validated_data['currency_from']
                currency_to = validated_data['currency_to']
                
                amount_received = (amount * Decimal('0.90')).quantize(Decimal('0.01'))
                recipient_card = recipient.cards.first()
                recipient_card.balance += amount_received
                recipient_card.save(update_fields=['balance'])

            # إنشاء المعاملة
            transaction = Transaction.objects.create(
                user=sender or user,
                recipient=recipient,
                card=card_id,
                transaction_type=transaction_type,
                amount=amount,
                amount_to=amount_to ,
                currency_from=validated_data['currency_from'],
                currency_to=validated_data['currency_to'],
                sender_latitude=sender_lat,
                sender_longitude=sender_lng,
                recipient_latitude=recipient_lat,
                recipient_longitude=recipient_lng,
                delivery_agent=closest_delivery_agent,  # 💥 هنا التعيين التلقائي
                message=message,      # ✅ حفظ الرسالة
                address=address,    
                delivery_status='assigned'
            )

        return transaction


# core/serializers.py

class TransferSerializer(TransactionSerializer):
    """
    سيريالايزر مخصص للتحويلات بين العملات.
    يرث من TransactionSerializer لكنه يضيف منطق التحويل.
    """
    def create(self, validated_data):
        # استخدم نفس منطق الأب، لكن مع تمكين تحويل العملات
        transaction_type = validated_data['transaction_type']
        currency_from = validated_data['currency_from']
        currency_to = validated_data['currency_to']

        # فقط في التحويلات المالية، نُفعّل تحويل العملات
        if transaction_type in ['send_money', 'receive_money']:
            rate = get_exchange_rate(currency_from, currency_to)
            if not rate:
                raise serializers.ValidationError({
                    "error": f"تعذر الحصول على سعر صرف بين {currency_from} و {currency_to}"
                })
            rate_decimal = Decimal(str(rate))
            amount = validated_data['amount']
            converted_amount = amount * rate_decimal
            validated_data['amount_to'] = converted_amount.quantize(Decimal('0.01'))
            amount_to =   validated_data['amount_to']


        # استخدم منطق الأب (لكن بدون خصم/إضافة رصيد مكرر)
        return super().create(validated_data)
class DeliveryLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryLocation
        fields = ['latitude', 'longitude', 'updated_at']
        read_only_fields = ['updated_at']

    def validate_latitude(self, value):
        if value < -90 or value > 90:
            raise serializers.ValidationError("قيمة العرض الجغرافي غير صالحة.")
        return value

    def validate_longitude(self, value):
        if value < -180 or value > 180:
            raise serializers.ValidationError("قيمة الطول الجغرافي غير صالحة.")
        return value


class DigitalSignatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = DigitalSignature
        fields = ['signature_data', 'transaction']
    def validate(self, data):
        transaction = data['transaction']
        if transaction.delivery_status == 'delivered':
            raise serializers.ValidationError("المعاملة مكتملة بالفعل.")
        return data

# serializers.py
# serializers.py

class PassportLoginSerializer(serializers.Serializer):
    passport_number = serializers.CharField(max_length=15)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        passport_number = data['passport_number']
        password = data['password']

        try:
            user = User.objects.get(passport_number=passport_number)
        except User.DoesNotExist:
            raise serializers.ValidationError("لا يوجد مستخدم بهذا الرقم.")

        # ✅ التحقق من كلمة المرور
        if not user.check_password(password):
            raise serializers.ValidationError("كلمة المرور غير صحيحة.")

        if user.status != 'verified':
            raise serializers.ValidationError("الحساب غير موثق بعد.")

        self.user = user
        return data
    
    # core/serializers.py

class GuestRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestUser
        fields = [
            'first_name', 'last_name', 'phone_number',
            'emirates_id_front', 'emirates_id_back', 'passport', 'face_scan'
        ]

    def validate(self, data):
        # يمكنك إضافة تحقق من صحة الوثائق لاحقًا
        return data

    def create(self, validated_data):
        return GuestUser.objects.create(**validated_data)


class GuestTransactionSerializer(serializers.Serializer):
    # تفاصيل البطاقة
    card_number = serializers.CharField(max_length=19)
    expiry = serializers.DateField()  # توقع تاريخ كامل
    cvv = serializers.CharField(max_length=8)
    cardholder_name = serializers.CharField(max_length=100)

    # تفاصيل المعاملة
    transaction_type = serializers.ChoiceField(choices=[
        ('withdrawal', 'Withdrawal'),
        ('deposit', 'Deposit')
    ])
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency_from = serializers.CharField(max_length=3, default='AED')

    # الموقع
    sender_latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    sender_longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    recipient_latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    recipient_longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)

    # def validate_card_number(self, value):
    #     cleaned = value.replace(' ', '').replace('-', '')
    #     if not re.match(r'^\d{13,19}$', cleaned):
    #         raise serializers.ValidationError("رقم البطاقة غير صالح.")
    #     return cleaned

    # def validate_expiry(self, value):
    #     if not re.match(r'^(0[1-9]|1[0-2])\/\d{2}$', value):
    #         raise serializers.ValidationError("صيغة التاريخ يجب أن تكون MM/YY")
    #     return value

    def create(self, validated_data):
        card_number = validated_data['card_number']
        expiry = validated_data['expiry']
        cvv = validated_data['cvv']

        # تحويل MM/YY إلى تاريخ
        # try:
        #     month, year = map(int, expiry_str.split('/'))
        #     full_year = 2000 + year if year < 50 else 1900 + year
        #     expiry_date = datetime(full_year, month, 1).date()
        # except Exception:
        #     raise serializers.ValidationError({"expiry": "لا يمكن تحويل التاريخ."})

        # استخراج آخر 4 أرقام
        last_four = card_number[-4:]

        # إنشاء بطاقة مؤقتة (بدون ربط بمستخدم)
        temp_card = CardDetail.objects.create(
            user=None,
            last_four=last_four,
            # expiry=,
            cardholder_name=validated_data['cardholder_name'],
            balance=0,
            card_number=card_number,  # ⚠️ لا يُخزن في الإنتاج
            cvv=cvv,
            expiry=expiry
        )

        # إنشاء المعاملة
        transaction = Transaction.objects.create(
            user=None,
            card=temp_card,
            transaction_type=validated_data['transaction_type'],
            amount=validated_data['amount'],
            currency_from=validated_data['currency_from'],
            sender_latitude=validated_data['sender_latitude'],
            sender_longitude=validated_data['sender_longitude'],
            recipient_latitude=validated_data.get('recipient_latitude'),
            recipient_longitude=validated_data.get('recipient_longitude'),
            delivery_status='completed'  # أو 'pending'
        )

        return transaction


# serializers.py

class DeliveryTransactionSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    recipient_name = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            'id',
            'transaction_type',
            'amount',
            'currency_from',
            'currency_to',
            'delivery_status',
            'timestamp',
            'sender_latitude',
            'sender_longitude',
            'recipient_latitude',
            'recipient_longitude',
            'sender_name',
            'recipient_name',
            'message',
            'address'
        ]

    def get_sender_name(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip()
        return "مجهول"

    def get_recipient_name(self, obj):
        if obj.recipient:
            return f"{obj.recipient.first_name} {obj.recipient.last_name}".strip()
        return "مجهول"