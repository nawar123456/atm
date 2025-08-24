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
from .models import User, CardDetail, Transaction, DigitalSignature,DeliveryLocation,GuestUser
from django.contrib.auth import get_user_model
from django.core.cache import cache
import secrets
from .models import generate_otp ,EmailOTP
from .utils2 import send_otp_email  # ✅ الاستيراد هنا
from rest_framework.decorators import api_view,permission_classes

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
    GuestRegisterSerializer,
    GuestTransactionSerializer,
    DeliveryTransactionSerializer,
    CreateEmployeeSerializer,
    EmployeeListSerializer,
    haversine_distance,
    
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
class UserViewSet(viewsets.ModelViewSet):
    """
    عرض المستخدمين (فقط للمدراء).
    لا يُعرض أي حقل حساس.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsApprovedUser]
    # http_method_names = ['get', 'head', 'options']

    def get_queryset(self):
        # دعم التصفية حسب الحالة
        status_filter = self.request.query_params.get('status')
        queryset = User.objects.all()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset
    
    @action(detail=False, methods=['put'], url_path='update-profile')
    def update_profile(self, request):
        """
        تعديل بيانات المستخدم الشخصية (الاسم الأول، الاسم الأخير، رقم الجوال)
        """
        user = request.user
        data = request.data

        # تحديث الحقول المسموح بها
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        user.phone_number = data.get('phone_number', user.phone_number)

        # يمكنك إضافة حقول أخرى مثل birth_date, emirates_id إذا أردت

        user.save(update_fields=['first_name', 'last_name', 'phone_number'])
        
        return Response({
            "message": "تم تحديث الملف الشخصي بنجاح.",
            "user": {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "phone_number": user.phone_number,
                "role": user.role
            }
        }, status=status.HTTP_200_OK)
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

    @action(detail=True, methods=['get'], url_path='track')
    def track_delivery(self, request, pk=None):
        """
        تتبع موقع مندوب التسليم
        """
        transaction = self.get_object()

        if not transaction.delivery_agent:
            return Response(
                {"error": "لا يوجد مندوب مُعين لهذه المعاملة."},
                status=404
            )

        delivery_location = getattr(transaction.delivery_agent, 'location', None)
        if not delivery_location:
            return Response(
                {"error": "المندوب لم يُفعّل تتبع الموقع بعد."},
                status=404
            )

        # حساب المسافة من المندوب إلى المستقبل
        distance = haversine_distance(
            float(transaction.recipient_latitude),
            float(transaction.recipient_longitude),
            float(delivery_location.latitude),
            float(delivery_location.longitude)
        )

        return Response({
            "delivery_agent": {
                "id": transaction.delivery_agent.id,
                "full_name": f"{transaction.delivery_agent.first_name} {transaction.delivery_agent.last_name}",
                "phone_number": transaction.delivery_agent.phone_number,
            },
            "current_location": {
                "latitude": delivery_location.latitude,
                "longitude": delivery_location.longitude,
                "updated_at": delivery_location.updated_at
            },
            "destination": {
                "latitude": transaction.recipient_latitude,
                "longitude": transaction.recipient_longitude
            },
            "distance_to_destination_km": round(distance, 2),
            "estimated_time_minutes": round(distance / 0.6, 1),  # افتراض سرعة 36 كم/ساعة
            "delivery_status": transaction.delivery_status
        })    
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
# views.py

class FaceIDVerificationView(APIView):
    """
    رفع صورة الوجه وهوية الإمارات
    بعد الرفع، يصبح المستخدم مُحققًا تلقائيًا
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
        # ✅ تغيير الحالة إلى 'verified' تلقائيًا
        user.status = 'verified'
        user.save(update_fields=['face_scan', 'emirates_id', 'status'])

        return Response({
            "message": "تم التحقق من هويتك بنجاح. يمكنك الآن استلام الأموال."
        }, status=status.HTTP_200_OK)

# ================================
# 8. التوقيع الرقمي
# ================================

# views.py

class SignatureView(APIView):
    """
    رفع التوقيع الرقمي → إكمال المعاملة تلقائيًا
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        signature_data = request.data.get("signature_data")
        transaction_id = request.data.get("transaction_id")

        if not signature_data:
            return Response(
                {"error": "التوقيع مطلوب"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            transaction = Transaction.objects.get(id=transaction_id)
        except Transaction.DoesNotExist:
            return Response(
                {"error": "المعاملة غير موجودة"},
                status=status.HTTP_404_NOT_FOUND
            )

        # ✅ التحقق: هل المندوب هو من يُكمل المعاملة؟
        if request.user != transaction.delivery_agent:
            return Response(
                {"error": "ليس لديك صلاحية إكمال هذه المعاملة"},
                status=status.HTTP_403_FORBIDDEN
            )

        # ✅ إنشاء التوقيع
        DigitalSignature.objects.create(
            transaction=transaction,
            signature_data=signature_data
        )

        # ✅ تحديث حالة المعاملة إلى "مكتملة"
        transaction.delivery_status = 'delivered'
        transaction.status = 'completed'
        transaction.save(update_fields=['delivery_status', 'status'])

        return Response({
            "message": "تم التوقيع وإكمال المعاملة بنجاح.",
            "transaction": {
                "id": transaction.id,
                "status": "completed",
                "delivery_status": "delivered"
            }
        }, status=status.HTTP_200_OK)
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
                # 'refresh': str(refresh),
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'full_name': f"{user.first_name} {user.last_name}".strip(),
                    'role': user.role,
                    'status': user.status
                }
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    


class GuestRegisterView(APIView):
    """
    تسجيل كضيف: رفع الوثائق
    """
    def post(self, request):
        serializer = GuestRegisterSerializer(data=request.data)
        if serializer.is_valid():
            guest = serializer.save()
            return Response({
                "message": "تم التسجيل كضيف بنجاح.",
                "temp_token": guest.get_temporary_token(),
                "user": {
                    "id": guest.id,
                    "first_name": guest.first_name,
                    "last_name": guest.last_name,
                    # "phone_number": guest.phone_number
                }
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GuestTransactionView(APIView):
    """
    إجراء معاملة كضيف
    """
    def post(self, request):
        # التحقق من توكن الضيف
        temp_token = request.headers.get('X-Guest-Token')
        if not temp_token:
            return Response({"error": "توكن الضيف مطلوب."}, status=401)

        try:
            guest = GuestUser.objects.get(temp_token=temp_token)
        except GuestUser.DoesNotExist:
            return Response({"error": "توكن الضيف غير صحيح أو منتهي الصلاحية."}, status=401)

        # التحقق من أن الضيف لم يُجرِ معاملة من قبل
        if hasattr(guest, 'transaction') and guest.transaction:
            return Response({"error": "الضيف قد أجرى معاملة من قبل."}, status=400)

        # إنشاء المعاملة
        serializer = GuestTransactionSerializer(data=request.data)
        if serializer.is_valid():
            transaction = serializer.save()

            # ربط المعاملة بالضيف (اختياري)
            # guest.transaction = transaction
            # guest.save()

            return Response({
                "message": "تم إجراء المعاملة بنجاح.",
                "transaction": {
                    "id": transaction.id,
                    "transaction_type": transaction.transaction_type,
                    "amount": transaction.amount,
                    "currency_from": transaction.currency_from,
                    "status": transaction.delivery_status
                }
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
# views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .permissions import IsDeliveryStaff

class DeliveryTransactionView(APIView):
    """
    عرض جميع المعاملات المُسندة للمندوب
    """
    permission_classes = [IsAuthenticated, IsDeliveryStaff]

    def get(self, request):
        # الحصول على جميع المعاملات المُسندة للمندوب
        transactions = Transaction.objects.filter(
            delivery_agent=request.user
        ).select_related('user', 'recipient').order_by('-timestamp')

        serializer = DeliveryTransactionSerializer(transactions, many=True)
        return Response({
            "count": transactions.count(),
            "transactions": serializer.data
        })

# views.py



@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdminUser])
def create_employee(request):
    serializer = CreateEmployeeSerializer(data=request.data)
    if serializer.is_valid():
        employee = serializer.save()
        return Response({
            "message": "تم إنشاء الموظف بنجاح.",
            "employee": {
                "id": employee.id,
                "first_name": employee.first_name,
                "last_name": employee.last_name,
                "username": employee.username,
                "email": employee.email,
                "role": employee.role,
                "status": employee.status
            }
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def list_employees(request):
    """
    عرض جميع الموظفين الذين دورهم 'staff' فقط
    """
    employees = User.objects.filter(role='staff')  # ✅ التصفية على role
    serializer = EmployeeListSerializer(employees, many=True)
    return Response(serializer.data)
