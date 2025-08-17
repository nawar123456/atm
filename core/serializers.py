# core/serializers.py

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction as db_transaction
from .models import User, CardDetail, Transaction, DigitalSignature,DeliveryLocation
from decimal import Decimal
from datetime import datetime
import re
import math

User = get_user_model()
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
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'username', 'email',
            'password', 'phone_number', 'birth_date', 'emirates_id',
            'passport', 'status', 'role'
        ]

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user



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

    class Meta:
        model = Transaction
        fields = [
            'id',
            'transaction_type',
            'amount',
            'currency_from',
            'currency_to',
            'card_id',
            'recipient_id',
            'sender_latitude',
            'sender_longitude',
            'recipient_latitude',
            'recipient_longitude',
            'timestamp',
            'delivery_agent'
        ]
        read_only_fields = ['timestamp']

    def create(self, validated_data):
        transaction_type = validated_data['transaction_type']
        user = self.context['request'].user
        card_id = validated_data.pop('card_id')
        amount = validated_data['amount']

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
                currency_from=validated_data['currency_from'],
                currency_to=validated_data['currency_to'],
                sender_latitude=sender_lat,
                sender_longitude=sender_lng,
                recipient_latitude=recipient_lat,
                recipient_longitude=recipient_lng,
                delivery_agent=closest_delivery_agent  # 💥 هنا التعيين التلقائي

            )

        return transaction


class DigitalSignatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = DigitalSignature
        fields = ['signature_data', 'transaction']