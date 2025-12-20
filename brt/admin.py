from django.contrib import admin
from .models import Product, ProductImage, ProductSize, Order, OrderItem


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1  # Show 1 empty form by default
    max_num = 5  # Maximum 5 images
    min_num = 1  # At least 1 image required
    fields = ['image', 'is_primary', 'order']


class ProductSizeInline(admin.TabularInline):
    model = ProductSize
    extra = 5  # Show 5 empty size forms
    fields = ['size', 'stock']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'brand', 'price', 'in_stock', 'created_at']
    list_filter = ['brand', 'created_at']
    search_fields = ['name', 'brand', 'description']
    inlines = [ProductImageInline, ProductSizeInline]
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'brand', 'price')
        }),
        ('Description', {
            'fields': ('description',)
        }),
    )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product_name', 'size', 'price', 'quantity', 'subtotal']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_id', 'customer_name', 'total_amount', 'status', 'payment_method', 'created_at']
    list_filter = ['status', 'payment_method', 'created_at']
    search_fields = ['order_id', 'customer_name', 'customer_email', 'customer_phone']
    readonly_fields = ['order_id', 'created_at', 'updated_at']
    inlines = [OrderItemInline]
    
    fieldsets = (
        ('Order Info', {
            'fields': ('order_id', 'status', 'payment_method')
        }),
        ('Customer', {
            'fields': ('customer_name', 'customer_email', 'customer_phone', 'customer_address')
        }),
        ('Payment', {
            'fields': ('total_amount', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
