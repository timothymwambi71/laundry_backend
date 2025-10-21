from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.utils import timezone


class StaffUser(AbstractUser):
    """Extended User model for staff with role-based access"""
    ROLE_CHOICES = [
        ('ADMIN', 'Admin'),
        ('COUNTER', 'Counter Staff'),
        ('DRIVER', 'Driver'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='COUNTER')
    phone = models.CharField(max_length=15, blank=True)
    is_active_staff = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'staff_users'
        verbose_name = 'Staff User'
        verbose_name_plural = 'Staff Users'
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"


class Client(models.Model):
    """Customer/Client information"""
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True, null=True, blank=True)
    phone = models.CharField(max_length=15, unique=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'clients'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['phone']),
            models.Index(fields=['email']),
        ]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.phone}"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def total_orders(self):
        return self.orders.count()
    
    @property
    def outstanding_balance(self):
        from django.db.models import Sum, F
        result = self.orders.filter(
            status__in=['PENDING', 'IN_PROGRESS', 'READY']
        ).aggregate(
            total=Sum(F('total_amount') - F('amount_paid'))
        )
        return result['total'] or Decimal('0.00')


class Service(models.Model):
    """Laundry service types and pricing"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    unit = models.CharField(max_length=20, default='piece')  # piece, kg, load
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'services'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} - {self.price} per {self.unit}"


class Order(models.Model):
    """Main order/transaction entity"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('READY', 'Ready for Pickup'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    
    # Financial fields
    total_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    amount_paid = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    
    # Dates
    order_date = models.DateTimeField(auto_now_add=True)
    pickup_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    completed_date = models.DateTimeField(null=True, blank=True)
    
    # Staff tracking
    created_by = models.ForeignKey(
        StaffUser, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='created_orders'
    )
    assigned_driver = models.ForeignKey(
        StaffUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_deliveries',
        limit_choices_to={'role': 'DRIVER'}
    )
    
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'orders'
        ordering = ['-order_date']
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['status', 'order_date']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.order_number:
            # Generate unique order number
            last_order = Order.objects.all().order_by('id').last()
            if last_order:
                last_id = last_order.id
            else:
                last_id = 0
            self.order_number = f"LMS{timezone.now().strftime('%Y%m%d')}{last_id + 1:04d}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.order_number} - {self.client.full_name}"
    
    @property
    def balance_due(self):
        """Calculate outstanding balance"""
        return max(self.total_amount - self.amount_paid, Decimal('0.00'))
    
    @property
    def is_paid(self):
        return self.balance_due == Decimal('0.00')
    
    @property
    def is_overdue(self):
        if self.due_date and not self.is_paid:
            return timezone.now().date() > self.due_date
        return False
    
    def calculate_total(self):
        """Recalculate total from order items"""
        total = self.items.aggregate(
            sum=models.Sum(
                models.F('quantity') * models.F('unit_price'),
                output_field=models.DecimalField()
            )
        )['sum'] or Decimal('0.00')
        self.total_amount = total
        self.save(update_fields=['total_amount'])
        return total


class OrderItem(models.Model):
    """Line items for each order"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    quantity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    notes = models.CharField(max_length=255, blank=True)
    
    class Meta:
        db_table = 'order_items'
        ordering = ['id']
    
    def save(self, *args, **kwargs):
        # Auto-set unit_price from service if not provided
        if not self.unit_price:
            self.unit_price = self.service.price
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.service.name} x {self.quantity}"
    
    @property
    def subtotal(self):
        return self.quantity * self.unit_price


class Payment(models.Model):
    """Payment transactions for orders"""
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Cash'),
        ('CARD', 'Card'),
        ('MOBILE_MONEY', 'Mobile Money'),
        ('BANK_TRANSFER', 'Bank Transfer'),
    ]
    
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_date = models.DateTimeField(auto_now_add=True)
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        StaffUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='received_payments'
    )
    
    class Meta:
        db_table = 'payments'
        ordering = ['-payment_date']
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update order's amount_paid
        self.order.amount_paid = self.order.payments.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        self.order.save(update_fields=['amount_paid'])
    
    def __str__(self):
        return f"Payment {self.amount} for {self.order.order_number}"


class ConsumableInventory(models.Model):
    """Track consumables like detergents, bags, hangers"""
    CATEGORY_CHOICES = [
        ('DETERGENT', 'Detergent'),
        ('SOFTENER', 'Fabric Softener'),
        ('BAG', 'Plastic Bag'),
        ('HANGER', 'Hanger'),
        ('STARCH', 'Starch'),
        ('OTHER', 'Other'),
    ]
    
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    unit = models.CharField(max_length=20, default='pieces')  # pieces, liters, kg
    reorder_level = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('10.00')
    )
    cost_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    last_restocked = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'consumable_inventory'
        ordering = ['category', 'name']
        verbose_name_plural = 'Consumable Inventories'
    
    def __str__(self):
        return f"{self.name} - {self.quantity} {self.unit}"
    
    @property
    def needs_reorder(self):
        return self.quantity <= self.reorder_level
    
    @property
    def total_value(self):
        if self.cost_per_unit:
            return self.quantity * self.cost_per_unit
        return Decimal('0.00')