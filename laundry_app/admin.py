# laundry_app/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    StaffUser, Client, Service, Order, 
    OrderItem, Payment, ConsumableInventory
)


@admin.register(StaffUser)
class StaffUserAdmin(UserAdmin):
    """Custom admin for StaffUser model"""
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'is_active_staff', 'is_staff']
    list_filter = ['role', 'is_active_staff', 'is_staff', 'is_superuser']
    search_fields = ['username', 'first_name', 'last_name', 'email', 'phone']
    ordering = ['-date_joined']
    
    fieldsets = UserAdmin.fieldsets + (
        ('Staff Information', {
            'fields': ('role', 'phone', 'is_active_staff'),
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Staff Information', {
            'fields': ('role', 'phone', 'is_active_staff'),
        }),
    )


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    """Admin configuration for Client model"""
    list_display = ['id', 'full_name', 'phone', 'email', 'total_orders', 'outstanding_balance', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['first_name', 'last_name', 'phone', 'email']
    readonly_fields = ['created_at', 'updated_at', 'total_orders', 'outstanding_balance']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'phone', 'email', 'address')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Statistics', {
            'fields': ('total_orders', 'outstanding_balance'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'Full Name'


class OrderItemInline(admin.TabularInline):
    """Inline admin for OrderItem"""
    model = OrderItem
    extra = 1
    fields = ['service', 'quantity', 'unit_price', 'subtotal', 'notes']
    readonly_fields = ['subtotal']
    
    def subtotal(self, obj):
        if obj.id:
            return f"UGX {obj.subtotal:,.2f}"
        return "UGX 0.00"


class PaymentInline(admin.TabularInline):
    """Inline admin for Payment"""
    model = Payment
    extra = 0
    fields = ['amount', 'payment_method', 'payment_date', 'reference_number', 'received_by']
    readonly_fields = ['payment_date', 'received_by']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin configuration for Order model"""
    list_display = [
        'order_number', 'client', 'status', 'total_amount', 
        'amount_paid', 'balance_due', 'is_paid', 'order_date', 'due_date'
    ]
    list_filter = ['status', 'order_date', 'due_date', 'created_by']
    search_fields = ['order_number', 'client__first_name', 'client__last_name', 'client__phone']
    readonly_fields = [
        'order_number', 'order_date', 'updated_at', 'balance_due', 
        'is_paid', 'is_overdue', 'total_amount', 'amount_paid'
    ]
    ordering = ['-order_date']
    date_hierarchy = 'order_date'
    inlines = [OrderItemInline, PaymentInline]
    
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'client', 'status', 'order_date')
        }),
        ('Financial Details', {
            'fields': ('total_amount', 'amount_paid', 'balance_due', 'is_paid', 'is_overdue')
        }),
        ('Schedule', {
            'fields': ('pickup_date', 'due_date', 'completed_date')
        }),
        ('Staff Assignment', {
            'fields': ('created_by', 'assigned_driver')
        }),
        ('Additional Information', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new order
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    def balance_due(self, obj):
        return f"UGX {obj.balance_due:,.2f}"
    balance_due.short_description = 'Balance Due'
    
    actions = ['mark_as_ready', 'mark_as_completed', 'recalculate_totals']
    
    def mark_as_ready(self, request, queryset):
        updated = queryset.update(status='READY')
        self.message_user(request, f'{updated} order(s) marked as Ready for Pickup.')
    mark_as_ready.short_description = 'Mark selected orders as Ready'
    
    def mark_as_completed(self, request, queryset):
        from django.utils import timezone
        updated = 0
        for order in queryset:
            order.status = 'COMPLETED'
            order.completed_date = timezone.now()
            order.save()
            updated += 1
        self.message_user(request, f'{updated} order(s) marked as Completed.')
    mark_as_completed.short_description = 'Mark selected orders as Completed'
    
    def recalculate_totals(self, request, queryset):
        for order in queryset:
            order.calculate_total()
        self.message_user(request, f'{queryset.count()} order(s) totals recalculated.')
    recalculate_totals.short_description = 'Recalculate order totals'


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """Admin configuration for OrderItem model"""
    list_display = ['id', 'order', 'service', 'quantity', 'unit_price', 'subtotal']
    list_filter = ['service', 'order__status']
    search_fields = ['order__order_number', 'service__name']
    readonly_fields = ['subtotal']
    
    def subtotal(self, obj):
        return f"UGX {obj.subtotal:,.2f}"
    subtotal.short_description = 'Subtotal'


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """Admin configuration for Service model"""
    list_display = ['name', 'price', 'unit', 'is_active', 'created_at']
    list_filter = ['is_active', 'unit', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['name']
    
    fieldsets = (
        ('Service Information', {
            'fields': ('name', 'description', 'price', 'unit')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Admin configuration for Payment model"""
    list_display = [
        'id', 'order', 'amount', 'payment_method', 
        'payment_date', 'reference_number', 'received_by'
    ]
    list_filter = ['payment_method', 'payment_date', 'received_by']
    search_fields = ['order__order_number', 'reference_number']
    readonly_fields = ['payment_date', 'received_by']
    ordering = ['-payment_date']
    date_hierarchy = 'payment_date'
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('order', 'amount', 'payment_method', 'reference_number')
        }),
        ('Details', {
            'fields': ('notes',)
        }),
        ('Tracking', {
            'fields': ('payment_date', 'received_by'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new payment
            obj.received_by = request.user
        super().save_model(request, obj, form, change)
    
    def amount(self, obj):
        return f"UGX {obj.amount:,.2f}"
    amount.short_description = 'Amount'


class LowStockFilter(admin.SimpleListFilter):
    """Custom filter for low stock items"""
    title = 'stock status'
    parameter_name = 'stock_status'
    
    def lookups(self, request, model_admin):
        return (
            ('low', 'Low Stock'),
            ('ok', 'In Stock'),
        )
    
    def queryset(self, request, queryset):
        from django.db.models import F
        if self.value() == 'low':
            return queryset.filter(quantity__lte=F('reorder_level'))
        if self.value() == 'ok':
            return queryset.filter(quantity__gt=F('reorder_level'))
        return queryset


@admin.register(ConsumableInventory)
class ConsumableInventoryAdmin(admin.ModelAdmin):
    """Admin configuration for ConsumableInventory model"""
    list_display = [
        'name', 'category', 'quantity', 'unit', 
        'reorder_level', 'needs_reorder', 'total_value', 
        'last_restocked'
    ]
    list_filter = ['category', LowStockFilter, 'last_restocked']
    search_fields = ['name']
    ordering = ['category', 'name']
    readonly_fields = ['needs_reorder', 'total_value', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Item Information', {
            'fields': ('name', 'category', 'unit')
        }),
        ('Stock Levels', {
            'fields': ('quantity', 'reorder_level', 'needs_reorder')
        }),
        ('Pricing', {
            'fields': ('cost_per_unit', 'total_value')
        }),
        ('Tracking', {
            'fields': ('last_restocked', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def total_value(self, obj):
        return f"UGX {obj.total_value:,.2f}"
    total_value.short_description = 'Total Value'
    
    actions = ['mark_as_restocked']
    
    def mark_as_restocked(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(last_restocked=timezone.now())
        self.message_user(request, f'{updated} item(s) marked as restocked.')
    mark_as_restocked.short_description = 'Mark as restocked today'


# Customize Admin Site Headers
admin.site.site_header = 'Laundry Management System Admin'
admin.site.site_title = 'Laundry MS Admin'
admin.site.index_title = 'Welcome to Laundry Management System Administration'