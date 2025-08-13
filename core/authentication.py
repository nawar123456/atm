from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

class ApprovedUserTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if not user.is_approved:
            raise AuthenticationFailed("تم رفض حسابك أو لم يتم الموافقة عليه بعد.")
        return user, token