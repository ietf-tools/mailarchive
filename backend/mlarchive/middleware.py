from django.http.response import JsonResponse
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from mlarchive.exceptions import HttpJson400, HttpJson404


class JsonExceptionMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        if isinstance(exception, HttpJson400):
            return JsonResponse({'error': exception.args[0]}, status=400)
        if isinstance(exception, HttpJson404):
            return JsonResponse({'error': exception.args[0]}, status=404)