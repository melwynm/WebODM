from django.utils.translation import gettext_lazy as _
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from app.models import Profile


class APIKeyAuthentication(BaseAuthentication):
    keyword = b"token"

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword:
            return None

        if len(auth) != 2:
            raise AuthenticationFailed(_("Invalid API token header."))

        api_key = auth[1].decode("utf-8", errors="ignore").strip()
        if not api_key:
            raise AuthenticationFailed(_("Invalid API token"))

        try:
            profile = Profile.objects.select_related('user').get(api_key=api_key)
        except Profile.DoesNotExist:
            raise AuthenticationFailed(_("Invalid API token"))

        if not profile.user.is_active:
            raise AuthenticationFailed(_("User inactive or deleted."))

        return profile.user, None

    def authenticate_header(self, request):
        return "Token"
