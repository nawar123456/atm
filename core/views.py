# core/views.py

from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import get_object_or_404

# --- النماذج ---
from .models import User, CardDetail, Transaction, DigitalSignature

# --- السيريالايزر ---
from .serializers import (
    UserSerializer,
    CardDetailSerializer,
    TransactionSerializer,
    DigitalSignatureSerializer,
)

# --- الصلاحيات المخصصة ---
from .permissions import IsAdminUser, IsApprovedUser, IsDeliveryStaff


# ================================
# 1. تسجيل مستخدم جديد (Register)
# ================================
class RegisterView(APIView):
    """
    إنشاء مستخدم جديد.
    """
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "تم إنشاء الحساب بنجاح. انتظر الموافقة من الإدارة.",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "status": user.status, # سيكون 'pending'
                    "role":user.role
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
    permission_classes = [IsAdminUser]
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


# ================================
# 4. إدارة البطاقات
# ================================
class CardDetailViewSet(viewsets.ModelViewSet):
    """
    عرض بطاقات المستخدم فقط.
    لا يمكن إنشاء بطاقة من هنا.
    """
    serializer_class = CardDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CardDetail.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        raise PermissionError("لا يمكن إضافة بطاقة من خلال هذه الواجهة.")


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
        user = self.request.user

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
    """
    واجهة مخصصة للتحويلات (كما في Postman: /api/transfers/)
    """
    permission_classes = [IsApprovedUser]

    def post(self, request):
        serializer = TransactionSerializer(data=request.data, context={'request': request})
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