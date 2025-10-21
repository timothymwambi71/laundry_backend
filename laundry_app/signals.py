from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Order
from .tasks import send_order_ready_notification, send_overdue_payment_reminder


@receiver(pre_save, sender=Order)
def detect_status_change(sender, instance, **kwargs):
    """
    Detect when order status changes to 'READY' and trigger notification.
    This runs before the order is saved.
    """
    if instance.pk:  # Only for existing orders (updates)
        try:
            old_instance = Order.objects.get(pk=instance.pk)
            
            # Check if status changed to READY
            if old_instance.status != 'READY' and instance.status == 'READY':
                # Set a flag to send notification after save
                instance._send_ready_notification = True
            
        except Order.DoesNotExist:
            pass


@receiver(post_save, sender=Order)
def send_status_notifications(sender, instance, created, **kwargs):
    """
    Send notifications after order is saved.
    Task 1: Notify client when order status changes to 'READY'
    """
    if hasattr(instance, '_send_ready_notification'):
        # Trigger async task to send notification
        send_order_ready_notification.delay(instance.id)
        
        # Clean up the flag
        delattr(instance, '_send_ready_notification')


# Celery Tasks (conceptual structure)
# tasks.py
"""
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from .models import Order, Client
import requests  # For SMS API integration

@shared_task
def send_order_ready_notification(order_id):
    '''
    Task 1: Send SMS/Email notification when order is ready for pickup.
    Integrates with Twilio, Africa's Talking, or similar SMS service.
    '''
    try:
        order = Order.objects.select_related('client').get(id=order_id)
        client = order.client
        
        # Prepare message
        message = (
            f"Hello {client.first_name}, your laundry order {order.order_number} "
            f"is ready for pickup! Balance: UGX {order.balance_due}. "
            f"Thank you for choosing our service."
        )
        
        # Send SMS via Africa's Talking / Twilio
        if client.phone:
            send_sms(client.phone, message)
        
        # Send Email
        if client.email:
            send_mail(
                subject=f'Order {order.order_number} Ready for Pickup',
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[client.email],
                fail_silently=True,
            )
        
        return f"Notification sent for order {order.order_number}"
    
    except Order.DoesNotExist:
        return f"Order {order_id} not found"


@shared_task
def send_overdue_payment_reminder(order_id):
    '''
    Task 2: Send reminder for overdue payments.
    This task should be scheduled to run daily via Celery Beat.
    '''
    try:
        order = Order.objects.select_related('client').get(id=order_id)
        
        # Check if order is actually overdue and has balance
        if not order.is_overdue or order.balance_due <= 0:
            return f"Order {order.order_number} is not overdue"
        
        client = order.client
        
        # Prepare reminder message
        message = (
            f"Dear {client.first_name}, this is a reminder that payment for "
            f"order {order.order_number} is overdue. Outstanding balance: "
            f"UGX {order.balance_due}. Due date was {order.due_date}. "
            f"Please settle your account. Thank you."
        )
        
        # Send SMS
        if client.phone:
            send_sms(client.phone, message)
        
        # Send Email
        if client.email:
            send_mail(
                subject=f'Payment Reminder - Order {order.order_number}',
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[client.email],
                fail_silently=True,
            )
        
        return f"Overdue reminder sent for order {order.order_number}"
    
    except Order.DoesNotExist:
        return f"Order {order_id} not found"


@shared_task
def check_all_overdue_orders():
    '''
    Periodic task to check all overdue orders and send reminders.
    Configure in Celery Beat to run daily.
    '''
    from django.db.models import F
    from datetime import date
    
    overdue_orders = Order.objects.filter(
        due_date__lt=date.today(),
        total_amount__gt=F('amount_paid')
    ).exclude(status__in=['COMPLETED', 'CANCELLED'])
    
    count = 0
    for order in overdue_orders:
        send_overdue_payment_reminder.delay(order.id)
        count += 1
    
    return f"Sent {count} overdue payment reminders"


def send_sms(phone_number, message):
    '''
    Helper function to send SMS via Africa's Talking or Twilio.
    Replace with your actual SMS provider implementation.
    '''
    # Africa's Talking Example:
    # import africastalking
    # africastalking.initialize(username='YOUR_USERNAME', api_key='YOUR_API_KEY')
    # sms = africastalking.SMS
    # response = sms.send(message, [phone_number])
    
    # Twilio Example:
    # from twilio.rest import Client
    # client = Client(account_sid, auth_token)
    # message = client.messages.create(
    #     body=message,
    #     from_='+1234567890',
    #     to=phone_number
    # )
    
    pass  # Placeholder for SMS integration


# Celery Beat Schedule Configuration (celery.py)
from celery.schedules import crontab

app.conf.beat_schedule = {
    'check-overdue-orders-daily': {
        'task': 'laundry_app.tasks.check_all_overdue_orders',
        'schedule': crontab(hour=9, minute=0),  # Run daily at 9 AM
    },
}
"""