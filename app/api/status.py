from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView


class APIStatus(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, *args, **kwargs):
        return Response({
            'ok': True,
            'authenticated': bool(request.user and request.user.is_authenticated),
            'protected_resources_require_authentication': True,
            'authentication': {
                'session': '/login/',
                'api_token': 'Authorization: Token <api_key>',
                'jwt': {
                    'obtain': '/api/token-auth/',
                    'header': 'Authorization: JWT <token>',
                    'query_string': '?jwt=<token>',
                },
            },
            'protected_examples': [
                '/api/projects/',
                '/api/processingnodes/',
            ],
        }, status=status.HTTP_200_OK)
