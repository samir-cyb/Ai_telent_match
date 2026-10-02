from django.core.cache import cache
from django.http import JsonResponse
from django.middleware.csrf import get_token


class ClientContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        get_token(request)
        key = None
        if request.method == 'POST' and request.path.startswith('/api/auth/') and request.path.endswith('/login/'):
            key = 'login:' + request.META.get('REMOTE_ADDR', '') + ':' + request.path
            if cache.get(key, 0) >= 10:
                return JsonResponse({'status': 'error', 'message': 'Too many login attempts. Retry in five minutes.'}, status=429)
        response = self.get_response(request)
        if key:
            if response.status_code == 401:
                cache.set(key, cache.get(key, 0) + 1, 300)
            elif response.status_code < 400:
                cache.delete(key)
        return response


def csrf_failure(request, reason=''):
    return JsonResponse({'status': 'error', 'message': 'Reload this page and retry the request.'}, status=403)
