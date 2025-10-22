from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


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
