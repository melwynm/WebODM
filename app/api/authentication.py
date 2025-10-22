from typing import Optional, Tuple

from django.contrib.auth.base_user import AbstractBaseUser
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import UntypedToken


class JSONWebTokenAuthenticationQS(JWTAuthentication):
    """Allow JWT authentication via query string parameter.

    The default :class:`~rest_framework_simplejwt.authentication.JWTAuthentication`
    implementation only inspects the Authorization header. Some of our
    integrations rely on being able to pass the token via the ``jwt`` query
    parameter, so we extend the default behaviour to support both methods.
    """

    def authenticate(self, request: Request) -> Optional[Tuple[AbstractBaseUser, UntypedToken]]:
        # First attempt the standard header based authentication.
        header_result = super().authenticate(request)
        if header_result is not None:
            return header_result

        raw_token = request.query_params.get("jwt")
        if not raw_token:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
