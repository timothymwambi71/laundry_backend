from rest_framework import serializers
from .models import (
    StaffUser, Client, Service, Order, 
    OrderItem, Payment, ConsumableInventory
)
from decimal import Decimal


class StaffUserSerializer(serializers.ModelSerializer):
    """Serializer for staff users"""
    class Meta:
        model = StaffUser
        fields = [
            'id', 'username', 'email', 'first_name', 
            'last_name', 'role', 'phone', 'is_active_staff'
        ]
        read_only_fields = ['id']


class ClientSerializer(serializers.ModelSerializer):
    """Serializer for clients with computed fields"""
    full_name = serializers.ReadOnlyField()
    total_orders = serializers.ReadOnlyField()
    outstanding_balance = serializers.ReadOnlyField()
    
    class Meta:
        model = Client
        fields = [
            'id', 'first_name', 'last_name', 'full_name',
            'email', 'phone', 'address', 'is_active',
            'total_orders', 'outstanding_balance',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ServiceSerializer(serializers.ModelSerializer):
    """Serializer for laundry services"""
    class Meta:
        model = Service
        fields = [
            'id', 'name', 'description', 'price', 
            'unit', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class OrderItemSerializer(serializers.ModelSerializer):
    """Serializer for order line items with service details"""
    service_name = serializers.CharField(source='service.name', read_only=True)
    service_unit = serializers.CharField(source='service.unit', read_only=True)
    subtotal = serializers.ReadOnlyField()
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'service', 'service_name', 'service_unit',
            'quantity', 'unit_price', 'subtotal', 'notes'
        ]
        read_only_fields = ['id', 'subtotal']
    
    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for payment records"""
    received_by_name = serializers.CharField(
        source='received_by.get_full_name', 
        read_only=True
    )
    
    class Meta:
        model = Payment
        fields = [
            'id', 'order', 'amount', 'payment_method',
            'payment_date', 'reference_number', 'notes',
            'received_by', 'received_by_name'
        ]
        read_only_fields = ['id', 'payment_date']
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Payment amount must be greater than zero.")
        return value


class OrderListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for order lists"""
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    client_phone = serializers.CharField(source='client.phone', read_only=True)
    balance_due = serializers.ReadOnlyField()
    is_paid = serializers.ReadOnlyField()
    is_overdue = serializers.ReadOnlyField()
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'client', 'client_name', 'client_phone',
            'status', 'total_amount', 'amount_paid', 'balance_due',
            'is_paid', 'is_overdue', 'order_date', 'due_date', 'pickup_date'
        ]


class OrderDetailSerializer(serializers.ModelSerializer):
    """Comprehensive order serializer with nested relationships"""
    client = ClientSerializer(read_only=True)
    client_id = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(),
        source='client',
        write_only=True
    )
    items = OrderItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    
    created_by_name = serializers.CharField(
        source='created_by.get_full_name',
        read_only=True
    )
    assigned_driver_name = serializers.CharField(
        source='assigned_driver.get_full_name',
        read_only=True,
        allow_null=True
    )
    
    balance_due = serializers.ReadOnlyField()
    is_paid = serializers.ReadOnlyField()
    is_overdue = serializers.ReadOnlyField()
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'client', 'client_id', 'status',
            'total_amount', 'amount_paid', 'balance_due', 'is_paid', 'is_overdue',
            'order_date', 'pickup_date', 'due_date', 'completed_date',
            'created_by', 'created_by_name', 'assigned_driver', 'assigned_driver_name',
            'notes', 'updated_at', 'items', 'payments'
        ]
        read_only_fields = [
            'id', 'order_number', 'order_date', 'updated_at', 
            'total_amount', 'amount_paid'
        ]


class OrderCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating orders with items"""
    items = OrderItemSerializer(many=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'client', 'status', 'pickup_date', 'due_date',
            'assigned_driver', 'notes', 'items'
        ]
        read_only_fields = ['id']
    
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        
        # Get the current user from context
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['created_by'] = request.user
        
        order = Order.objects.create(**validated_data)
        
        # Create order items
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        
        # Calculate and update total
        order.calculate_total()
        
        return order
    
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        
        # Update order fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update items if provided
        if items_data is not None:
            # Delete existing items
            instance.items.all().delete()
            
            # Create new items
            for item_data in items_data:
                OrderItem.objects.create(order=instance, **item_data)
            
            # Recalculate total
            instance.calculate_total()
        
        return instance


class ConsumableInventorySerializer(serializers.ModelSerializer):
    """Serializer for consumable inventory management"""
    needs_reorder = serializers.ReadOnlyField()
    total_value = serializers.ReadOnlyField()
    
    class Meta:
        model = ConsumableInventory
        fields = [
            'id', 'name', 'category', 'quantity', 'unit',
            'reorder_level', 'cost_per_unit', 'needs_reorder',
            'total_value', 'last_restocked', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class OutstandingDemandSerializer(serializers.Serializer):
    """Serializer for outstanding demands report"""
    order_number = serializers.CharField()
    client_name = serializers.CharField()
    client_phone = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2)
    balance_due = serializers.DecimalField(max_digits=10, decimal_places=2)
    due_date = serializers.DateField()
    is_overdue = serializers.BooleanField()
    order_date = serializers.DateTimeField()


class SalesReportSerializer(serializers.Serializer):
    """Serializer for sales report data"""
    period = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_orders = serializers.IntegerField()
    completed_orders = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_payments = serializers.DecimalField(max_digits=12, decimal_places=2)
    outstanding_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    average_order_value = serializers.DecimalField(max_digits=10, decimal_places=2)