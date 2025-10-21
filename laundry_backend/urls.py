# project/urls.py (main URL configuration)
from django.contrib import admin
from django.urls import path, include
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse

@ensure_csrf_cookie
def get_csrf_token(request):
    """Endpoint to get CSRF token"""
    return JsonResponse({'detail': 'CSRF cookie set'})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('laundry_app.urls')),
    path('api/auth/', include('rest_framework.urls')),
    path('api/csrf/', get_csrf_token, name='csrf'),
]