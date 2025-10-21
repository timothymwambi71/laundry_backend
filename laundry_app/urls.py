from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    StaffUserViewSet, ClientViewSet, ServiceViewSet,
    OrderViewSet, PaymentViewSet, ConsumableInventoryViewSet,
    register_user
)

router = DefaultRouter()
router.register(r'staff', StaffUserViewSet, basename='staff')
router.register(r'clients', ClientViewSet, basename='client')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'inventory', ConsumableInventoryViewSet, basename='inventory')

urlpatterns = [
    path('', include(router.urls)),
    path('register/', register_user, name='register'),
]
