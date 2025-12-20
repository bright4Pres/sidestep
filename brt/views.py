from django.shortcuts import render, redirect
from django.db import models
from .models import Order, OrderItem, Product, ProductSize
from django.db.models import Min, Max
import uuid

def index(request):
    return render(request, 'landingpage.html')

def shop(request):
    products = Product.objects.prefetch_related('images', 'sizes').all()
    
    # Get all unique brands for filter
    all_brands = Product.objects.values_list('brand', flat=True).distinct().order_by('brand')
    all_brands = [b for b in all_brands if b]  # Remove empty brands
    
    # Get all available sizes for filter
    all_sizes = ProductSize.SIZE_CHOICES
    
    # Get all categories for filter
    all_categories = Product.CATEGORY_CHOICES
    
    # Get price range for filter
    price_range = Product.objects.aggregate(min_price=Min('price'), max_price=Max('price'))
    
    # Filter by category (from landing page links)
    category = request.GET.get('category')
    if category:
        if category == 'new':
            # New arrivals - products from last 30 days or marked as new
            from django.utils import timezone
            from datetime import timedelta
            thirty_days_ago = timezone.now() - timedelta(days=30)
            products = products.filter(
                models.Q(created_at__gte=thirty_days_ago) | models.Q(category='new')
            )
        elif category == 'sale':
            products = products.filter(is_on_sale=True)
        elif category == 'trending':
            products = products.filter(is_trending=True)
        else:
            products = products.filter(category=category)
    
    # Filter by brand(s) if provided
    selected_brands = request.GET.getlist('brand')
    if selected_brands:
        products = products.filter(brand__in=selected_brands)
    
    # Filter by size(s) if provided
    selected_sizes = request.GET.getlist('size')
    if selected_sizes:
        products = products.filter(sizes__size__in=selected_sizes, sizes__stock__gt=0).distinct()
    
    # Filter by price range
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    if min_price:
        products = products.filter(price__gte=min_price)
    if max_price:
        products = products.filter(price__lte=max_price)
    
    # Filter by search query
    search = request.GET.get('q')
    if search:
        products = products.filter(name__icontains=search)
    
    # Sort products
    sort = request.GET.get('sort', 'newest')
    if sort == 'price_low':
        products = products.order_by('price')
    elif sort == 'price_high':
        products = products.order_by('-price')
    elif sort == 'name':
        products = products.order_by('name')
    else:  # newest
        products = products.order_by('-created_at')
    
    context = {
        'products': products,
        'all_brands': all_brands,
        'all_sizes': all_sizes,
        'all_categories': all_categories,
        'selected_brands': selected_brands,
        'selected_sizes': selected_sizes,
        'selected_category': category or '',
        'min_price': min_price or '',
        'max_price': max_price or '',
        'price_range': price_range,
        'current_sort': sort,
        'search_query': search or '',
    }
    
    return render(request, 'shop.html', context)

def checkout(request):
    """Handle checkout form submission"""
    if request.method == 'POST':
        # Get form data
        customer_name = request.POST.get('customer_name')
        customer_email = request.POST.get('customer_email')
        customer_phone = request.POST.get('customer_phone')
        customer_address = request.POST.get('customer_address')
        payment_method = request.POST.get('payment_method')
        notes = request.POST.get('notes', '')
        
        # Get cart from session (you can implement this)
        # For now, assume a simple order
        total_amount = float(request.POST.get('total_amount', 0)) or 99.00
        
        # Create order
        order = Order.objects.create(
            order_id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            customer_address=customer_address,
            total_amount=total_amount,
            payment_method=payment_method,
            notes=notes,
            status='pending'
        )
        
        # Add sample item (replace with actual cart items)
        OrderItem.objects.create(
            order=order,
            product_name='Sneaker',
            price=99.00,
            quantity=1
        )
        
        return redirect('order_confirmation', order_id=order.id)
    
    return render(request, 'checkout.html')


def order_confirmation(request, order_id):
    """Display order confirmation"""
    order = Order.objects.get(id=order_id)
    return render(request, 'order_confirmation.html', {'order': order})


def track_order(request):
    """Track order by order ID"""
    order_id = request.GET.get('id')
    try:
        order = Order.objects.get(order_id=order_id)
        return render(request, 'track_order.html', {'order': order})
    except Order.DoesNotExist:
        return render(request, 'track_order.html', {'error': 'Order not found'})
