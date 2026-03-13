from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from app.models import Profile


class ObtainJSONWebTokenSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        return {"token": data["access"]}


class ObtainJSONWebTokenView(TokenObtainPairView):
    serializer_class = ObtainJSONWebTokenSerializer

    # The default implementation returns both refresh and access tokens.  We
    # only expose the access token for backward compatibility with the
    # previous djangorestframework-jwt response payload.
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class TokenBaseView(APIView):
    permission_classes = [IsAuthenticated]

    def get_profile(self, request):
        profile, _created = Profile.objects.get_or_create(user=request.user)
        return profile

    def get(self, request, *args, **kwargs):
        profile = self.get_profile(request)
        return Response({'api_key': profile.api_key})

    def regenerate(self, request):
        profile = self.get_profile(request)
        profile.regenerate_api_key()
        return Response({'api_key': profile.api_key})


class TokenView(TokenBaseView):
    def post(self, request, *args, **kwargs):
        return self.regenerate(request)


class TokenRegenerateView(TokenBaseView):
    def post(self, request, *args, **kwargs):
        return self.regenerate(request)
