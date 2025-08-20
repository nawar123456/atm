# core/views.py

from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import get_object_or_404
from decimal import Decimal
from django.core.exceptions import ValidationError

# --- النماذج ---from .serializers import DeliveryLocationSerializer
from .models import User, CardDetail, Transaction, DigitalSignature,DeliveryLocation
from django.contrib.auth import get_user_model
from django.core.cache import cache
import secrets
from .models import generate_otp ,EmailOTP
from .utils2 import send_otp_email  # ✅ الاستيراد هنا

# --- السيريالايزر ---
from .serializers import (
    UserSerializer,
    CardDetailSerializer,
    TransactionSerializer,
    DigitalSignatureSerializer,
    DeliveryLocationSerializer,
    TransferSerializer,
    VerifyOTPSerializer,
    RegisterSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PassportLoginSerializer,
    
)

# --- الصلاحيات المخصصة ---
from .permissions import IsAdminUser, IsApprovedUser, IsDeliveryStaff

User = get_user_model()
# ================================
# 1. تسجيل مستخدم جديد (Register)
# ================================
class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            cache.set(
                f"register_data_{email}",
                {
                    'email': email,
                    'password': request.data['password'],
                    'data': {
                        'username': request.data.get('username'),
                        'first_name': request.data.get('first_name'),
                        'last_name': request.data.get('last_name'),
                        'phone_number': request.data.get('phone_number'),
                        'birth_date': request.data.get('birth_date'),
                        'emirates_id': request.data.get('emirates_id'),
                        'passport': request.data.get('passport'),
                        'passport_number': request.data.get('passport_number'),

                        
                    }
                },
                timeout=900  # صالح 15 دقيقة
            )

            # ✅ توليد مفتاح فريد
            # token = secrets.token_urlsafe(32)

            # ✅ حفظ البيانات مؤقتًا (بما في ذلك كلمة المرور)
        
            # إرسال OTP (كما كان)
            otp_code = generate_otp()
            otp_obj, created = EmailOTP.objects.update_or_create(
                email=email,
                defaults={'otp': otp_code}
            )
            send_otp_email(email, otp_code)

            return Response({
                "message": "تم إرسال رمز OTP إلى بريدك الإلكتروني.",
                "email": email,
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# views.py

class PasswordResetRequestView(APIView):
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "تم إرسال رمز OTP إلى بريدك الإلكتروني."
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmView(APIView):
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "تم تغيير كلمة المرور بنجاح. يمكنك الآن تسجيل الدخول."
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
class VerifyOTPView(APIView):
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "تم تفعيل الحساب بنجاح. يمكنك الآن تسجيل الدخول.",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "full_name": f"{user.first_name} {user.last_name}".strip(),
                    "role": user.role
                }
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
# ================================
# 2. تسجيل الدخول
# ================================
class LoginView(APIView):
    """
    تسجيل الدخول وإصدار JWT tokens.
    """
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"error": "البريد الإلكتروني وكلمة المرور مطلوبان"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(email=email, password=password)
        if not user:
            return Response(
                {"error": "البريد الإلكتروني أو كلمة المرور غير صحيحة"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        lat = request.data.get("latitude")
        lng = request.data.get("longitude")

        # فقط للمندوبين وبوجود إحداثيات صالحة
        if user.role == 'delivery' and lat is not None and lng is not None:
            try:
                lat = Decimal(str(lat))
                lng = Decimal(str(lng))
                if lat < -90 or lat > 90 or lng < -180 or lng > 180:
                    raise ValidationError("Invalid lat/lng")
            except Exception:
                return Response(
                    {"error": "إحداثيات غير صالحة"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ تخزين/تحديث موقع المندوب (upsert)
            DeliveryLocation.objects.update_or_create(
                delivery_agent=user,
                defaults={"latitude": lat, "longitude": lng}
            )

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            # 'refresh': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'status': user.status,
                'is_approved': user.is_approved,
                'role': user.role,
                'full_name': user.get_full_name() or user.username
            }
        })
        

# ================================
# 3. إدارة المستخدمين (للإدارة فقط)
# ================================
class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    عرض المستخدمين (فقط للمدراء).
    لا يُعرض أي حقل حساس.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsApprovedUser]
    # http_method_names = ['get', 'head', 'options']

    def get_queryset(self):
        # دعم التصفية حسب الحالة (كما في Postman)
        status_filter = self.request.query_params.get('status')
        queryset = User.objects.only(
            'id', 'first_name', 'last_name', 'email', 'status', 'role',
            'phone_number', 'emirates_id', 'passport', 'birth_date'
        )
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset
    @action(detail=True, methods=['get'], url_path='cards')
    def user_cards(self, request, pk=None):
        """
        إرجاع جميع البطاقات الخاصة بالمستخدم.
        - المستخدم العادي: فقط بطاقاته.
        - المدير: يمكنه رؤية بطاقات أي مستخدم.
        """
        target_user = self.get_object()  # المستخدم الذي نريد رؤية بطاقاته

    # ✅ التحقق: هل المستخدم العادي يحاول رؤية بطاقات شخص آخر؟
        if request.user != target_user and not request.user.is_staff and request.user.role != 'admin':
         return Response(
            {"error": "لا يمكنك رؤية بطاقات مستخدم آخر."},
            status=status.HTTP_403_FORBIDDEN
        )

        cards = CardDetail.objects.filter(user=target_user)
        serializer = CardDetailSerializer(cards, many=True)
        return Response(serializer.data)
    @action(detail=True, methods=['post'], url_path='change_status')
    def change_status(self, request, pk=None):
        user = self.get_object()
        new_status = request.data.get('status')

        if new_status not in dict(User.STATUS_CHOICES).keys():
            return Response(
                {'error': 'الحالة غير صالحة'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.status = new_status
        user.save(update_fields=['status'])
        return Response({'status': f'تم تحديث الحالة إلى {new_status}'})




class DeliveryLocationViewSet(viewsets.ModelViewSet):
    """
    مندوب التسليم يُحدّث موقعه الجغرافي.
    الموقع يُربط تلقائيًا بـ request.user.
    """
    serializer_class = DeliveryLocationSerializer
    permission_classes = [IsAuthenticated, IsDeliveryStaff]

    def get_queryset(self):
        # فقط موقع المستخدم الحالي
        return DeliveryLocation.objects.filter(delivery_agent=self.request.user)

    def perform_create(self, serializer):
        # ربط الموقع بالمندوب تلقائيًا
        serializer.save(delivery_agent=self.request.user)

    def perform_update(self, serializer):
        serializer.save(delivery_agent=self.request.user)
# ================================
# 4. إدارة البطاقات
# ================================


class CardDetailViewSet(viewsets.ModelViewSet):
    """
    عرض وإنشاء بطاقات المستخدم.
    
    """
    
    serializer_class = CardDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CardDetail.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # ✅ السماح بإنشاء البطاقة
        serializer.save(user=self.request.user)

# ================================
# 5. المعاملات (سحب، إيداع، تحويل)
# ================================
class TransactionViewSet(viewsets.ModelViewSet):
    """
    إدارة المعاملات (مثل السحب أو الإيداع أو التحويل).
    """
    serializer_class = TransactionSerializer
    permission_classes = [IsApprovedUser]

    def get_queryset(self):
                return Transaction.objects.filter(user=self.request.user)

        
    @action(detail=False, methods=['get'], url_path='credit')
    def credit_transactions(self, request):
        """
        إرجاع جميع المعاملات التي زادت رصيد المستخدم
        """
        credit_types = ['receive_money', 'deposit']
        transactions = Transaction.objects.filter(
            user=request.user,
            transaction_type__in=credit_types
        )
        serializer = self.get_serializer(transactions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='debit')
    def debit_transactions(self, request):
        """
        إرجاع جميع المعاملات التي نقصت رصيد المستخدم
        """
        debit_types = ['send_money', 'withdrawal']
        transactions = Transaction.objects.filter(
            user=request.user,
            transaction_type__in=debit_types
        )
        serializer = self.get_serializer(transactions, many=True)
        return Response(serializer.data)

    # ✅ إذا كان مندوب تسليم، يرى جميع المعاملات بحالة 'pending'
        if hasattr(user, 'role') and user.role == 'delivery':
            return Transaction.objects.filter(delivery_status='pending')

    # ✅ إذا كان مستخدمًا عاديًا أو مُعتمدًا، يرى معاملاته فقط
        if user.is_authenticated:
            return Transaction.objects.filter(user=user)

    # ✅ إذا لم يكن مسجل دخوله
        return Transaction.objects.none()
    @action(detail=False, methods=['post'])
    def start(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transaction = serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsDeliveryStaff],url_path='assign_to_me')
    def assign_to_me(self, request, pk=None):
        """
        مندوب التسليم يأخذ المعاملة
        """
        transaction = self.get_object()
        if transaction.delivery_status != 'pending':
            return Response({'error': 'هذه المعاملة غير متاحة للتسليم'}, status=400)

        transaction.delivery_agent = request.user
        transaction.delivery_status = 'assigned'
        transaction.save(update_fields=['delivery_agent', 'delivery_status'])
        return Response({'status': 'تم تعيين المعاملة لك'})

    @action(detail=True, methods=['post'], permission_classes=[IsDeliveryStaff])
    def mark_delivered(self, request, pk=None):
        """
        مندوب التسليم يُكمل التسليم
        """
        transaction = self.get_object()
        if transaction.delivery_agent != request.user:
            return Response({'error': 'أنت لست المندوب المخصص لهذه المعاملة'}, status=403)

        if transaction.delivery_status != 'assigned':
            return Response({'error': 'لا يمكن تسليم هذه المعاملة الآن'}, status=400)

        transaction.delivery_status = 'delivered'
        transaction.status = 'completed'
        transaction.save(update_fields=['delivery_status', 'status'])
        return Response({'status': 'تم تسليم المعاملة بنجاح'})


# ================================
# 6. التحويلات (send_money / receive_money)
# ================================
class TransferTransactionView(APIView):
    permission_classes = [IsApprovedUser]

    def post(self, request):
        serializer = TransferSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        transaction = serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
# ================================
# 7. التحقق من الهوية (وجه + هوية)
# ================================
class FaceIDVerificationView(APIView):
    """
    رفع صورة الوجه وهوية الإمارات
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        face_scan = request.data.get("face_scan")
        emirates_id = request.data.get("emirates_id")

        if not face_scan or not emirates_id:
            return Response(
                {"error": "الرجاء رفع صورة الوجه وهوية الإمارات"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        user.face_scan = face_scan
        user.emirates_id = emirates_id
        user.status = 'pending'
        user.save(update_fields=['face_scan', 'emirates_id', 'status'])

        return Response({
            "message": "تم رفع بيانات التحقق. سيتم مراجعتها من قبل الإدارة."
        }, status=status.HTTP_200_OK)


# ================================
# 8. التوقيع الرقمي
# ================================

class SignatureView(APIView):
    """
    حفظ التوقيع الرقمي
    """
    permission_classes = [IsApprovedUser]

    def post(self, request):
        signature_data = request.data.get("signature_data")
        transaction_id = request.data.get("transaction_id")

        if not signature_data:  # ✅ التصحيح هنا
            return Response(
                {"error": "الرجاء إرسال بيانات التوقيع"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            transaction = Transaction.objects.get(id=transaction_id)
        except Transaction.DoesNotExist:
            return Response({"error": "المعاملة غير موجودة"}, status=404)

        # التحقق: هل المستخدم هو المستلم؟
        if request.user != transaction.recipient:
            return Response({"error": "أنت لست المستلم لهذه المعاملة"}, status=403)

        DigitalSignature.objects.update_or_create(
            transaction=transaction,
            defaults={
                "user": request.user,
                "signature_data": signature_data
            }
        )
        return Response({"message": "تم حفظ التوقيع الرقمي بنجاح"}, status=status.HTTP_200_OK)
# ================================
# 9. دفع التسليم (مثل Postman)
# ================================
class PaymentView(APIView):
    """
    بدء عملية دفع (مثل: سحب نقد)
    """
    permission_classes = [IsApprovedUser]

    def post(self, request):
        amount = request.data.get("amount")
        currency_from = request.data.get("currency_from")
        currency_to = request.data.get("currency_to")

        if not all([amount, currency_from, currency_to]):
            return Response(
                {"error": "الرجاء إدخال المبلغ والعملات"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # إنشاء معاملة
        transaction = Transaction.objects.create(
            user=request.user,
            transaction_type="deposit",  # أو "withdrawal"
            amount=amount,
            currency_from=currency_from,
            currency_to=currency_to,
            status="pending"
        )

        return Response({
            "message": "تم بدء عملية الدفع",
            "transaction_id": transaction.id
        }, status=status.HTTP_201_CREATED)
    

# views.py

from rest_framework_simplejwt.tokens import RefreshToken

class PassportLoginView(APIView):
    """
    تسجيل دخول عبر رقم الجواز وكلمة المرور
    """
    def post(self, request):
        serializer = PassportLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.user

            # ✅ إصدار توكن
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'full_name': f"{user.first_name} {user.last_name}".strip(),
                    'role': user.role,
                    'status': user.status
                }
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)