from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
import uuid
from decimal import Decimal

class Product(models.Model):
    CATEGORY_CHOICES = [
        ('new', 'New Arrivals'),
        ('basketball', 'Basketball'),
        ('running', 'Running'),
        ('trending', 'Trending'),
        ('sale', 'Sale'),
        ('casual', 'Casual'),
        ('lifestyle', 'Lifestyle'),
    ]
    
    name = models.CharField(max_length=255)
    description = models.TextField()
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=67420, help_text="Starting price for display")
    brand = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='new')
    is_on_sale = models.BooleanField(default=False)  # For sale items
    is_trending = models.BooleanField(default=False)  # For trending items
    created_at = models.DateTimeField(auto_now_add=True)
    # Publishing status for admin manual publish control
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return self.name
    
    def in_stock(self):
        return self.sizes.filter(stock__gt=0).exists()
    
    def min_price(self):
        """Get the lowest price from available sizes"""
        min_p = self.sizes.filter(stock__gt=0).order_by('price').first()
        return min_p.price if min_p else self.base_price
    
    def max_price(self):
        """Get the highest price from available sizes"""
        max_p = self.sizes.filter(stock__gt=0).order_by('-price').first()
        return max_p.price if max_p else self.base_price
    
    def price_range(self):
        """Return price range string for display"""
        min_p = self.min_price()
        max_p = self.max_price()
        if min_p == max_p:
            return f"₱{min_p}"
        return f"₱{min_p} - ₱{max_p}"
    
    def primary_image(self):
        """Get the primary image or first image"""
        img = self.images.filter(is_primary=True).first()
        if not img:
            img = self.images.first()
        return img


def product_image_path(instance, filename):
    """
    Upload images to: products/brand/shoe_name/filename
    Example: products/nike/air_jordan_1/image1.jpg
    """
    import re
    # Clean brand name (lowercase, replace spaces with underscores, remove special chars)
    brand = instance.product.brand.lower() if instance.product.brand else 'unknown_brand'
    brand = re.sub(r'[^a-z0-9]+', '_', brand).strip('_')
    
    # Clean product name
    product_name = instance.product.name.lower()
    product_name = re.sub(r'[^a-z0-9]+', '_', product_name).strip('_')
    
    return f'products/{brand}/{product_name}/{filename}'


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to=product_image_path)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order', '-is_primary']
    
    def __str__(self):
        return f"{self.product.name} - Image {self.order}"
    
    def save(self, *args, **kwargs):
        # Limit to 5 images per product
        if not self.pk:  # New image
            existing_count = ProductImage.objects.filter(product=self.product).count()
            if existing_count >= 5:
                raise ValueError("Maximum 5 images per product")
        
        # If this is set as primary, unset all others for this product
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        
        # Auto-set order if not provided
        if self.order == 0 and not self.pk:
            max_order = ProductImage.objects.filter(product=self.product).aggregate(models.Max('order'))['order__max']
            self.order = (max_order or 0) + 1
        
        super().save(*args, **kwargs)
        
        # If no primary image exists for this product, make this one primary
        if not ProductImage.objects.filter(product=self.product, is_primary=True).exists():
            self.is_primary = True
            super().save(update_fields=['is_primary'])


class ProductSize(models.Model):
    SIZE_CHOICES = [
        ('US 4', 'US 4'),
        ('US 4.5', 'US 4.5'),
        ('US 5', 'US 5'),
        ('US 5.5', 'US 5.5'),
        ('US 6', 'US 6'),
        ('US 6.5', 'US 6.5'),
        ('US 7', 'US 7'),
        ('US 7.5', 'US 7.5'),
        ('US 8', 'US 8'),
        ('US 8.5', 'US 8.5'),
        ('US 9', 'US 9'),
        ('US 9.5', 'US 9.5'),
        ('US 10', 'US 10'),
        ('US 10.5', 'US 10.5'),
        ('US 11', 'US 11'),
        ('US 11.5', 'US 11.5'),
        ('US 12', 'US 12'),
        ('US 13', 'US 13'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sizes')
    size = models.CharField(max_length=10, choices=SIZE_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Leave at 0 to use base price")
    stock = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ('product', 'size')
        ordering = ['size']
    
    def __str__(self):
        return f"{self.product.name} - {self.size} ({self.stock} in stock)"
    
    def save(self, *args, **kwargs):
        # If price is 0 (default), use the product's base_price
        if self.price == 0:
            self.price = self.product.base_price
        super().save(*args, **kwargs)


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('paid', 'Paid'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    order_id = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20)
    customer_address = models.TextField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Order {self.order_id}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=255)
    size = models.CharField(max_length=10)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField()
    
    def subtotal(self):
        # Guard against incomplete inline forms where price or quantity may be None
        if self.price is None or self.quantity is None:
            return Decimal('0.00')
        try:
            return self.price * self.quantity
        except Exception:
            return Decimal('0.00')
    
    def __str__(self):
        return f"{self.product_name} ({self.size}) x{self.quantity}"
