from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
import uuid

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
    price = models.DecimalField(max_digits=10, decimal_places=2)
    brand = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='new')
    is_on_sale = models.BooleanField(default=False)  # For sale items
    is_trending = models.BooleanField(default=False)  # For trending items
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    def in_stock(self):
        return self.sizes.filter(stock__gt=0).exists()
    
    def primary_image(self):
        """Get the primary image or first image"""
        img = self.images.filter(is_primary=True).first()
        if not img:
            img = self.images.first()
        return img


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/')
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
        # If this is set as primary, unset others
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)


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
    stock = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ('product', 'size')
        ordering = ['size']
    
    def __str__(self):
        return f"{self.product.name} - {self.size} ({self.stock} in stock)"


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
        return self.price * self.quantity
    
    def __str__(self):
        return f"{self.product_name} ({self.size}) x{self.quantity}"
