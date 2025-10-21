from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from datetime import timedelta, datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import (
    StaffUser, Client, Service, Order, 
    OrderItem, Payment, ConsumableInventory
)
from .serializers import (
    StaffUserSerializer, ClientSerializer, ServiceSerializer,
    OrderListSerializer, OrderDetailSerializer, OrderCreateUpdateSerializer,
    PaymentSerializer, ConsumableInventorySerializer,
    OutstandingDemandSerializer, SalesReportSerializer
)


@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    """
    Register a new staff user.
    Public endpoint - no authentication required.
    """
    data = request.data
    
    # Validate required fields
    required_fields = ['username', 'password', 'first_name', 'last_name', 'email']
    for field in required_fields:
        if not data.get(field):
            return Response(
                {'error': f'{field} is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    # Check if username already exists
    if StaffUser.objects.filter(username=data['username']).exists():
        return Response(
            {'error': 'Username already exists'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if email already exists
    if StaffUser.objects.filter(email=data['email']).exists():
        return Response(
            {'error': 'Email already exists'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate password strength
    try:
        validate_password(data['password'])
    except ValidationError as e:
        return Response(
            {'error': list(e.messages)},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Create user
    try:
        user = StaffUser.objects.create_user(
            username=data['username'],
            email=data['email'],
            password=data['password'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            phone=data.get('phone', ''),
            role=data.get('role', 'COUNTER')  # Default to counter staff
        )
        
        serializer = StaffUserSerializer(user)
        return Response(
            {
                'message': 'Registration successful',
                'user': serializer.data
            },
            status=status.HTTP_201_CREATED
        )
    
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


class StaffUserViewSet(viewsets.ModelViewSet):
    """ViewSet for managing staff users"""
    queryset = StaffUser.objects.filter(is_active_staff=True)
    serializer_class = StaffUserSerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def drivers(self, request):
        """Get list of active drivers"""
        drivers = self.queryset.filter(role='DRIVER')
        serializer = self.get_serializer(drivers, many=True)
        return Response(serializer.data)


class ClientViewSet(viewsets.ModelViewSet):
    """ViewSet for managing clients"""
    queryset = Client.objects.filter(is_active=True)
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get('search', None)
        
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(phone__icontains=search) |
                Q(email__icontains=search)
            )
        
        return queryset
    
    @action(detail=True, methods=['get'])
    def orders(self, request, pk=None):
        """Get all orders for a specific client"""
        client = self.get_object()
        orders = client.orders.all()
        serializer = OrderListSerializer(orders, many=True)
        return Response(serializer.data)


class ServiceViewSet(viewsets.ModelViewSet):
    """ViewSet for managing laundry services"""
    queryset = Service.objects.filter(is_active=True)
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated]


class OrderViewSet(viewsets.ModelViewSet):
    """ViewSet for managing orders with financial reporting"""
    queryset = Order.objects.all().select_related(
        'client', 'created_by', 'assigned_driver'
    ).prefetch_related('items__service', 'payments')
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return OrderListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return OrderCreateUpdateSerializer
        return OrderDetailSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        
        if start_date:
            queryset = queryset.filter(order_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(order_date__lte=end_date)
        
        # Filter by client
        client_id = self.request.query_params.get('client', None)
        if client_id:
            queryset = queryset.filter(client_id=client_id)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def recalculate_total(self, request, pk=None):
        """Manually trigger total recalculation"""
        order = self.get_object()
        new_total = order.calculate_total()
        
        return Response({
            'order_number': order.order_number,
            'total_amount': new_total,
            'balance_due': order.balance_due
        })
    
    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """Update order status"""
        order = self.get_object()
        new_status = request.data.get('status')
        
        # Get valid status choices
        valid_statuses = [choice[0] for choice in Order.STATUS_CHOICES]
        
        if new_status not in valid_statuses:
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = order.status
        order.status = new_status
        
        if new_status == 'COMPLETED':
            order.completed_date = timezone.now()
        
        order.save()
        
        # Trigger notification signal here (will be handled by signals.py)
        
        serializer = self.get_serializer(order)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def outstanding_demands(self, request):
        """
        Get all orders with outstanding balance.
        API Endpoint: /api/orders/outstanding_demands/
        """
        outstanding_orders = Order.objects.filter(
            total_amount__gt=F('amount_paid')
        ).exclude(
            status='CANCELLED'
        ).select_related('client').order_by('due_date')
        
        # Build response data
        demands = []
        for order in outstanding_orders:
            demands.append({
                'order_number': order.order_number,
                'client_name': order.client.full_name,
                'client_phone': order.client.phone,
                'total_amount': order.total_amount,
                'amount_paid': order.amount_paid,
                'balance_due': order.balance_due,
                'due_date': order.due_date,
                'is_overdue': order.is_overdue,
                'order_date': order.order_date
            })
        
        serializer = OutstandingDemandSerializer(demands, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def sales_report(self, request):
        """
        Generate sales report for specified period.
        Query params: period (daily|weekly|monthly), date (YYYY-MM-DD for daily)
        API Endpoint: /api/orders/sales_report/?period=daily&date=2025-10-21
        """
        period = request.query_params.get('period', 'daily')
        custom_date = request.query_params.get('date', None)
        today = timezone.now().date()
        
        # Determine date range based on period
        if period == 'daily':
            if custom_date:
                try:
                    start_date = datetime.strptime(custom_date, '%Y-%m-%d').date()
                except ValueError:
                    return Response(
                        {'error': 'Invalid date format. Use YYYY-MM-DD'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                start_date = today
            end_date = start_date
        elif period == 'weekly':
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
        elif period == 'monthly':
            start_date = today.replace(day=1)
            # Get last day of month
            if today.month == 12:
                end_date = today.replace(day=31)
            else:
                end_date = (today.replace(month=today.month + 1, day=1) - timedelta(days=1))
        else:
            return Response(
                {'error': 'Invalid period. Use: daily, weekly, or monthly'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Query orders within date range
        orders = Order.objects.filter(
            order_date__date__gte=start_date,
            order_date__date__lte=end_date
        )
        
        # Aggregate statistics
        stats = orders.aggregate(
            total_orders=Count('id'),
            completed_orders=Count('id', filter=Q(status='COMPLETED')),
            total_revenue=Sum('total_amount'),
            total_payments=Sum('amount_paid')
        )
        
        # Calculate outstanding balance for the period
        outstanding = orders.aggregate(
            outstanding=Sum(F('total_amount') - F('amount_paid'))
        )['outstanding'] or Decimal('0.00')
        
        # Calculate average order value
        avg_order_value = (
            stats['total_revenue'] / stats['total_orders'] 
            if stats['total_orders'] > 0 
            else Decimal('0.00')
        )
        
        report_data = {
            'period': period,
            'start_date': start_date,
            'end_date': end_date,
            'total_orders': stats['total_orders'],
            'completed_orders': stats['completed_orders'],
            'total_revenue': stats['total_revenue'] or Decimal('0.00'),
            'total_payments': stats['total_payments'] or Decimal('0.00'),
            'outstanding_balance': outstanding,
            'average_order_value': avg_order_value
        }
        
        serializer = SalesReportSerializer(report_data)
        return Response(serializer.data)


class PaymentViewSet(viewsets.ModelViewSet):
    """ViewSet for managing payments"""
    queryset = Payment.objects.all().select_related('order', 'received_by')
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        # Set received_by to current user
        serializer.save(received_by=self.request.user)
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Get recent payments (last 30 days)"""
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_payments = self.queryset.filter(payment_date__gte=thirty_days_ago)
        serializer = self.get_serializer(recent_payments, many=True)
        return Response(serializer.data)


class ConsumableInventoryViewSet(viewsets.ModelViewSet):
    """ViewSet for managing consumable inventory"""
    queryset = ConsumableInventory.objects.all()
    serializer_class = ConsumableInventorySerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get items that need reordering"""
        low_stock_items = self.queryset.filter(
            quantity__lte=F('reorder_level')
        )
        serializer = self.get_serializer(low_stock_items, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def restock(self, request, pk=None):
        """Add stock to an inventory item"""
        item = self.get_object()
        quantity = request.data.get('quantity')
        
        if not quantity or float(quantity) <= 0:
            return Response(
                {'error': 'Invalid quantity'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        item.quantity += Decimal(str(quantity))
        item.last_restocked = timezone.now()
        item.save()
        
        serializer = self.get_serializer(item)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def consume(self, request, pk=None):
        """Deduct stock from an inventory item"""
        item = self.get_object()
        quantity = request.data.get('quantity')
        
        if not quantity or float(quantity) <= 0:
            return Response(
                {'error': 'Invalid quantity'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if item.quantity < Decimal(str(quantity)):
            return Response(
                {'error': 'Insufficient stock'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        item.quantity -= Decimal(str(quantity))
        item.save()
        
        serializer = self.get_serializer(item)
        return Response(serializer.data)