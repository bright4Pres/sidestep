from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.urls import reverse
from .models import Product, ProductImage, ProductSize, Order, OrderItem


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1  # Show 1 empty form by default
    max_num = 5  # Maximum 5 images
    min_num = 0  # Allow zero images (so delete works)
    can_delete = False  # Hide the default delete checkbox
    fields = ['image_preview', 'image', 'is_primary', 'order', 'delete_button']
    readonly_fields = ['image_preview', 'delete_button']
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 80px; max-width: 80px; object-fit: contain;"/>', obj.image.url)
        return "-"
    image_preview.short_description = "Preview"
    
    def delete_button(self, obj):
        if obj.pk:
            return format_html(
                '<a class="button" style="background: #dc3545; color: white; padding: 5px 15px; '
                'text-decoration: none; border-radius: 3px; font-size: 12px;" '
                'href="{}" onclick="return confirm(\'Delete this image?\');">Delete</a>',
                reverse('admin:brt_productimage_delete', args=[obj.pk])
            )
        return "-"
    delete_button.short_description = "Action"
    
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        return formset


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    """Hidden admin for delete functionality"""
    list_display = ['product', 'is_primary', 'order']
    
    def has_module_permission(self, request):
        return False  # Hide from admin index


class ProductSizeInline(admin.TabularInline):
    model = ProductSize
    extra = 5  # Show 5 empty size forms
    can_delete = False  # Hide the default delete checkbox
    fields = ['size', 'price', 'stock']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'brand', 'category', 'base_price', 'is_on_sale', 'is_trending', 'in_stock', 'created_at']
    list_filter = ['brand', 'category', 'is_on_sale', 'is_trending', 'created_at']
    search_fields = ['name', 'brand', 'description']
    inlines = [ProductImageInline, ProductSizeInline]
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'brand', 'base_price', 'category')
        }),
        ('Flags', {
            'fields': ('is_on_sale', 'is_trending')
        }),
        ('Description', {
            'fields': ('description',)
        }),
    )
    
    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        
        # Handle ProductImage - ensure only one primary
        if formset.model == ProductImage:
            primary_count = 0
            for instance in instances:
                if instance.is_primary:
                    primary_count += 1
            
            # If multiple primaries selected, only keep the last one
            if primary_count > 1:
                for instance in instances[:-1]:
                    if instance.is_primary:
                        instance.is_primary = False
            
            # If no primary selected and there are images, make first one primary
            if primary_count == 0 and instances:
                instances[0].is_primary = True
        
        for instance in instances:
            instance.save()
        formset.save_m2m()


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
