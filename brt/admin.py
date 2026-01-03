from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.urls import reverse, path
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.contrib import messages
from django.http import HttpResponseRedirect
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
    list_display = ['name', 'brand', 'category', 'base_price', 'is_on_sale', 'is_trending', 'in_stock', 'is_published', 'created_at', 'publish_button']
    list_filter = ['brand', 'category', 'is_on_sale', 'is_trending', 'is_published', 'created_at']
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

    actions = ['publish_selected']

    def publish_selected(self, request, queryset):
        """Admin action to publish all selected products (always posts, even if already published)."""
        count = 0
        for product in queryset:
            # Always mark as published and update timestamp
            product.is_published = True
            product.published_at = timezone.now()
            product.save(update_fields=['is_published', 'published_at'])
            # Call posting helpers (if available)
            try:
                from .signals import post_multiple_to_facebook, post_instagram_carousel, _build_full_image_url, _upload_image_to_cloudinary
                import os
                from django.conf import settings
                
                # Collect and process image URLs (upload local images to Cloudinary)
                image_urls = []
                for img in product.images.all().order_by('order'):
                    if not getattr(img, 'image', None):
                        continue
                    
                    img_url = _build_full_image_url(img.image)
                    if not img_url:
                        continue
                    
                    # If URL is relative or self-hosted, upload to Cloudinary
                    site_url = os.environ.get('SITE_URL') or os.environ.get('RENDER_EXTERNAL_HOSTNAME') or getattr(settings, 'RENDER_EXTERNAL_HOSTNAME', None)
                    normalized_site = None
                    if site_url:
                        if not site_url.startswith('http'):
                            site_url = 'https://' + site_url
                        normalized_site = site_url.rstrip('/')
                    
                    should_upload = False
                    if img_url.startswith('/'):
                        should_upload = True
                    elif normalized_site and img_url.startswith(normalized_site):
                        should_upload = True
                    
                    if should_upload:
                        cloudinary_url = _upload_image_to_cloudinary(img.image)
                        if cloudinary_url:
                            img_url = cloudinary_url
                    
                    image_urls.append(img_url)
                
                # Build sizes/stock/price string
                size_lines = []
                for size_obj in product.sizes.all():
                    size_str = f"{size_obj.size} ({size_obj.stock}) - ₱{size_obj.price}"
                    size_lines.append(size_str)
                sizes_info = "\n".join(size_lines)
                message = (
                    f"🔥 Fresh Drop Alert! 🔥\n"
                    f"Step up your game with the new {product.brand} {product.name}!\n\n"
                    f"Sizes & Stock:\n{sizes_info}\n\n"
                    f"Tap the link to see more photos and details: https://www.sidestep.studio/product/{product.id}/\n"
                    f"DM us to reserve your pair or ask questions! #sidestep #sneakerhead #newdrop"
                )
                if image_urls:
                    post_multiple_to_facebook(message, image_urls)
                    post_instagram_carousel(message, image_urls)
            except Exception:
                # don't block the admin action on posting errors
                pass
            count += 1
        self.message_user(request, f"Published {count} products.")
    publish_selected.short_description = 'Publish selected products (post to FB/IG)'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:product_id>/publish/', self.admin_site.admin_view(self.publish_product_view), name='brt_product_publish'),
        ]
        return custom + urls

    def publish_button(self, obj):
        if getattr(obj, 'is_published', False):
            return mark_safe('<span style="color:green">Published</span>')
        url = reverse('admin:brt_product_publish', args=[obj.pk])
        return format_html('<a class="button" href="{}">Publish</a>', url)
    publish_button.short_description = 'Publish'

    def publish_product_view(self, request, product_id, *args, **kwargs):
        """Admin view to publish a single product and post to FB/IG."""
        product = Product.objects.filter(pk=product_id).first()
        if not product:
            self.message_user(request, 'Product not found', level=messages.ERROR)
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))
        # Mark published
        product.is_published = True
        product.published_at = timezone.now()
        product.save(update_fields=['is_published', 'published_at'])
        # Post to FB/IG
        try:
            from .signals import post_multiple_to_facebook, post_instagram_carousel, _build_full_image_url, _upload_image_to_cloudinary
            import os
            from django.conf import settings
            
            # Collect and process image URLs (upload local images to Cloudinary)
            image_urls = []
            for img in product.images.all().order_by('order'):
                if not getattr(img, 'image', None):
                    continue
                
                img_url = _build_full_image_url(img.image)
                if not img_url:
                    continue
                
                # If URL is relative or self-hosted, upload to Cloudinary
                site_url = os.environ.get('SITE_URL') or os.environ.get('RENDER_EXTERNAL_HOSTNAME') or getattr(settings, 'RENDER_EXTERNAL_HOSTNAME', None)
                normalized_site = None
                if site_url:
                    if not site_url.startswith('http'):
                        site_url = 'https://' + site_url
                    normalized_site = site_url.rstrip('/')
                
                should_upload = False
                if img_url.startswith('/'):
                    should_upload = True
                elif normalized_site and img_url.startswith(normalized_site):
                    should_upload = True
                
                if should_upload:
                    cloudinary_url = _upload_image_to_cloudinary(img.image)
                    if cloudinary_url:
                        img_url = cloudinary_url
                
                image_urls.append(img_url)
            
            # Build sizes/stock/price string
            size_lines = []
            for size_obj in product.sizes.all():
                size_str = f"{size_obj.size} ({size_obj.stock}) - ₱{size_obj.price}"
                size_lines.append(size_str)
            sizes_info = "\n".join(size_lines)
            message = (
                f"🔥 Fresh Drop Alert! 🔥\n"
                f"Step up your game with the new {product.brand} {product.name}!\n\n"
                f"Sizes & Stock:\n{sizes_info}\n\n"
                f"Tap the link to see more photos and details: https://www.sidestep.studio/product/{product.id}/\n"
                f"DM us to reserve your pair or ask questions! #sidestep #sneakerhead #newdrop"
            )
            if image_urls:
                post_multiple_to_facebook(message, image_urls)
                post_instagram_carousel(message, image_urls)
            self.message_user(request, 'Product published and posted to social media')
        except Exception as e:
            self.message_user(request, f'Published but failed to post: {e}', level=messages.WARNING)
        # Redirect back to product change list
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/admin/'))


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
