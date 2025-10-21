# laundry_app/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from .models import Order
from django.db.models import F
from datetime import date


@shared_task
def send_order_ready_notification(order_id):
    """
    Task 1: Send SMS/Email notification when order is ready for pickup.
    Integrates with Twilio, Africa's Talking, or similar SMS service.
    """
    try:
        order = Order.objects.select_related('client').get(id=order_id)
        client = order.client
        
        # Prepare message
        message = (
            f"Hello {client.first_name}, your laundry order {order.order_number} "
            f"is ready for pickup! Balance: UGX {order.balance_due}. "
            f"Thank you for choosing our service."
        )
        
        # Send SMS via Africa's Talking / Twilio (placeholder)
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
    """
    Task 2: Send reminder for overdue payments.
    This task should be scheduled to run daily via Celery Beat.
    """
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
    """
    Periodic task to check all overdue orders and send reminders.
    Configure in Celery Beat to run daily.
    """
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
    """
    Helper function to send SMS via Africa's Talking or Twilio.
    Replace with your actual SMS provider implementation.
    """
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
    
    print(f"SMS to {phone_number}: {message}")  # Placeholder for development
