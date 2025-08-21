# core/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from .models import User, CardDetail, Transaction, DigitalSignature,GuestUser
from .models import DeliveryLocation

# --- 1. إدارة المستخدمين ---
class UserAdmin(BaseUserAdmin):
    # الحقول التي تُعرض في قائمة المستخدمين
    list_display = (
        'email', 'first_name', 'last_name', 'status', 'role', 'is_staff', 'date_joined'
    )

    # دعم التصفية في الجانب الأيمن
    list_filter = ('status', 'role', 'is_staff', 'is_superuser', 'date_joined')

    # دعم البحث
    search_fields = ('email', 'first_name', 'last_name', 'emirates_id', 'passport')

    # الحقول التي تُعرض عند عرض/تعديل المستخدم
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('البيانات الشخصية', {'fields': ('first_name', 'last_name', 'phone_number', 'birth_date')}),
        ('الهوية', {'fields': ('emirates_id', 'passport', 'face_scan','passport_number')}),
        ('الحالة والدور', {'fields': ('status', 'role')}),
        ('الأذونات', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        ('التواريخ', {'fields': ('last_login', 'date_joined'), 'classes': ('collapse',)}),
    )

    # الحقول عند إنشاء مستخدم جديد
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
        ('البيانات الشخصية', {
            'fields': ('first_name', 'last_name', 'phone_number', 'birth_date')
        }),
        ('الحالة والدور', {
            'fields': ('status', 'role')
        }),
    )

    # الترتيب
    ordering = ('email',)
    readonly_fields = ('date_joined', 'last_login')


# تسجيل النموذج
admin.site.register(User, UserAdmin)


# --- 2. إدارة البطاقات ---
@admin.register(CardDetail)
class CardDetailAdmin(admin.ModelAdmin):
    list_display = ('user', 'last_four', 'expiry', 'cardholder_name')
    search_fields = ('user__email', 'last_four')
    list_filter = ('expiry',)
    # readonly_fields = ('user', 'last_four', 'expiry', 'cardholder_name')


# --- 3. إدارة المعاملات ---
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'transaction_type', 'amount', 'currency_from',
        'status', 'delivery_status', 'timestamp', 'delivery_agent'
    )
    list_filter = (
        'transaction_type', 'status', 'delivery_status', 'timestamp',
        'currency_from', 'currency_to'
    )
    search_fields = ('user__email', 'recipient__email', 'card__last_four')
    date_hierarchy = 'timestamp'

    # عرض حقول الموقع
    # readonly_fields = (
    #     'sender_latitude', 'sender_longitude',
    #     'recipient_latitude', 'recipient_longitude'
    # )

    # fieldsets = (
    #     ('المستخدمين', {
    #         'fields': ('user', 'recipient')
    #     }),
    #     ('التفاصيل المالية', {
    #         'fields': ('transaction_type', 'amount', 'currency_from', 'currency_to', 'card')
    #     }),
    #     ('الحالة', {
    #         'fields': ('status', 'delivery_status', 'delivery_agent')
    #     }),
    #     ('الموقع', {
    #         'fields': (
    #             ('sender_latitude', 'sender_longitude'),
    #             ('recipient_latitude', 'recipient_longitude')
    #         ),
    #         'classes': ('collapse',)
    #     }),
    #     ('التوقيت', {
    #         'fields': ('timestamp',)
    #     }),
    # )
@admin.register(DeliveryLocation)
class DeliveryLocationAdmin(admin.ModelAdmin):
    list_display = ('delivery_agent', 'latitude', 'longitude', 'updated_at')
    search_fields = ('delivery_agent__email',)
    list_filter = ('updated_at',)

# --- 4. إدارة التوقيع الرقمي ---
@admin.register(DigitalSignature)
class DigitalSignatureAdmin(admin.ModelAdmin):
    list_display = ('user', 'transaction', 'signed_at')
    list_filter = ('signed_at',)
    search_fields = ('user__email', 'transaction__id')
    # readonly_fields = ('user', 'transaction', 'signature_data', 'signed_at')

class GuestUserAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'phone_number', 'created_at', 'has_emirates_id', 'has_passport', 'has_face_scan')
    list_filter = ('created_at',)
    search_fields = ('first_name', 'last_name', 'phone_number')
    readonly_fields = ('temp_token', 'created_at')
    fieldsets = (
        ('المعلومات الشخصية', {
            'fields': ('first_name', 'last_name', 'phone_number')
        }),
        ('الوثائق', {
            'fields': ('emirates_id_front', 'emirates_id_back', 'passport', 'face_scan'),
            'classes': ('collapse',)
        }),
        ('المعلومات الفنية', {
            'fields': ('temp_token', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def has_emirates_id(self, obj):
        return bool(obj.emirates_id_front or obj.emirates_id_back)
    has_emirates_id.boolean = True
    has_emirates_id.short_description = 'هوية الإمارات'

    def has_passport(self, obj):
        return bool(obj.passport)
    has_passport.boolean = True
    has_passport.short_description = 'جواز السفر'

    def has_face_scan(self, obj):
        return bool(obj.face_scan)
    has_face_scan.boolean = True
    has_face_scan.short_description = 'مسح الوجه'

admin.site.register(GuestUser, GuestUserAdmin)

    # fieldsets = (
    #     (None, {
    #         'fields': ('user', 'transaction', 'signed_at')
    #     }),
    #     ('بيانات التوقيع', {
    #         'fields': ('signature_data',),
    #         'classes': ('collapse',)
    #     }),
    # )


# --- تغيير عنوان لوحة التحكم ---
admin.site.site_header = "لوحة تحكم ATM"
admin.site.site_title = "ATM Admin"
admin.site.index_title = "مرحبًا بكم في لوحة تحكم نظام ATM"