def get_appsecret_proof(access_token, app_secret):
    """Generate appsecret_proof for Facebook API requests."""
    return hmac.new(app_secret.encode('utf-8'), access_token.encode('utf-8'), hashlib.sha256).hexdigest()


import os
import json
import traceback
import time
import threading
import requests
import hmac
import hashlib
import json
from django.conf import settings
from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Product, ProductImage

"""Signals: auto-post new products to Facebook and Instagram with debug logging.

This file verifies image URLs and logs full API responses to help debug failures.
"""


def _verify_image_url(image_url, timeout=5):
    """Verify image URL is reachable and looks like an image.

    Returns (ok: bool, info: dict).
    """
    info = {
        'status_code': None,
        'content_type': None,
        'content_length': None,
        'final_url': image_url,
        'error': None,
    }
    try:
        head = requests.head(image_url, allow_redirects=True, timeout=timeout)
        info['status_code'] = head.status_code
        info['final_url'] = head.url
        info['content_type'] = head.headers.get('Content-Type')
        info['content_length'] = head.headers.get('Content-Length')
        if head.status_code >= 400 or not info['content_type']:
            get = requests.get(image_url, stream=True, timeout=timeout)
            info['status_code'] = get.status_code
            info['final_url'] = get.url
            info['content_type'] = get.headers.get('Content-Type')
            info['content_length'] = get.headers.get('Content-Length')
            get.close()
        ok = 200 <= int(info['status_code']) < 400 and (info['content_type'] or '').startswith('image')
        return ok, info
    except Exception as e:
        info['error'] = str(e)
        return False, info


# Log environment detection once at import so Render logs show what env vars are available
try:
    _site = os.environ.get('SITE_URL')
    _render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME') or getattr(settings, 'RENDER_EXTERNAL_HOSTNAME', None)
    _cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
    _cloud_key = bool(os.environ.get('CLOUDINARY_API_KEY'))
    _cloud_secret = bool(os.environ.get('CLOUDINARY_API_SECRET'))
    print(f"[signals env] SITE_URL={_site!r}, RENDER_EXTERNAL_HOSTNAME={_render_host!r}, CLOUDINARY_CLOUD_NAME={_cloud_name!r}, CLOUD_KEY_SET={_cloud_key}, CLOUD_SECRET_SET={_cloud_secret}")
except Exception:
    pass


def _build_full_image_url(image_field):
    """Return an absolute URL for an ImageField. Prefers already-absolute URLs.

    Falls back to using SITE_URL env var or RENDER_EXTERNAL_HOSTNAME to
    prefix relative `image_field.url` values.
    """
    if not image_field:
        return None
    try:
        url = image_field.url
    except Exception:
        return None
    if url.startswith('http://') or url.startswith('https://'):
        return url

    # Try SITE_URL env var first, then Render hostname, then settings
    site_url = os.environ.get('SITE_URL') or os.environ.get('RENDER_EXTERNAL_HOSTNAME') or getattr(settings, 'RENDER_EXTERNAL_HOSTNAME', None)
    if site_url:
        if not site_url.startswith('http'):
            site_url = 'https://' + site_url
        return site_url.rstrip('/') + url

    # No way to build absolute URL; return relative URL so caller can decide
    return url


def _upload_image_to_cloudinary(image_field):
    """Upload a local ImageField to Cloudinary and return the secure URL, or None."""
    try:
        import cloudinary.uploader
    except Exception as e:
        print(f"[Cloudinary] cloudinary package not available: {e}")
        return None

    try:
        path = getattr(image_field, 'path', None)
        if path:
            result = cloudinary.uploader.upload(path, folder="sidestep_products", resource_type="image")
        else:
            f = image_field.open('rb')
            try:
                result = cloudinary.uploader.upload(f, folder="sidestep_products", resource_type="image")
            finally:
                try:
                    f.close()
                except Exception:
                    pass
        secure = result.get('secure_url') if isinstance(result, dict) else None
        print(f"[Cloudinary] upload result secure_url: {secure}")
        return secure
    except Exception as e:
        print(f"[Cloudinary] upload failed: {e}")
        print(traceback.format_exc())
        return None


def post_to_facebook_page(message, image_url=None):
    page_id = getattr(settings, 'FACEBOOK_PAGE_ID', None)
    access_token = getattr(settings, 'FACEBOOK_PAGE_ACCESS_TOKEN', None)
    app_secret = getattr(settings, 'FACEBOOK_APP_SECRET', None)
    if not page_id or not access_token or not app_secret:
        print('FACEBOOK_PAGE_ID, FACEBOOK_PAGE_ACCESS_TOKEN, or FACEBOOK_APP_SECRET not set')
        return

    appsecret_proof = get_appsecret_proof(access_token, app_secret)

    if image_url:
        print(f"[Facebook] Using image_url: {image_url}")
        ok, info = _verify_image_url(image_url)
        print('[Facebook] image verification:', info)
        if not ok:
            print('[Facebook] Image URL failed verification; aborting Facebook photo post')
            return
        url = f'https://graph.facebook.com/{page_id}/photos'
        data = {
            'caption': message,
            'url': image_url,
            'access_token': access_token,
            'appsecret_proof': appsecret_proof
        }
    else:
        url = f'https://graph.facebook.com/{page_id}/feed'
        data = {
            'message': message,
            'access_token': access_token,
            'appsecret_proof': appsecret_proof
        }

    try:
        response = requests.post(url, data=data, timeout=10)
        print('[Facebook] post HTTP status:', response.status_code)
        try:
            resp_json = response.json()
        except Exception:
            print('[Facebook] response text:', response.text)
            resp_json = {'error': 'invalid_json', 'text': response.text}
        print('[Facebook] post response json:', resp_json)
        if 'error' in resp_json:
            print('[Facebook] post error details:', resp_json.get('error'))
        else:
            print('[Facebook] post success:', resp_json)
    except Exception as e:
        print('[Facebook] Error posting:', e)
        print(traceback.format_exc())


def post_to_instagram(message, image_url=None):
    ig_account_id = getattr(settings, 'INSTAGRAM_BUSINESS_ACCOUNT_ID', None)
    access_token = getattr(settings, 'FACEBOOK_PAGE_ACCESS_TOKEN', None)
    app_secret = getattr(settings, 'FACEBOOK_APP_SECRET', None)
    if not ig_account_id or not access_token or not app_secret:
        print('INSTAGRAM_BUSINESS_ACCOUNT_ID, FACEBOOK_PAGE_ACCESS_TOKEN, or FACEBOOK_APP_SECRET not set')
        return

    appsecret_proof = get_appsecret_proof(access_token, app_secret)
    if not image_url:
        print('Image URL required for Instagram post')
        return


    print(f"[Instagram] Using image_url: {image_url}")
    ok, info = _verify_image_url(image_url)
    print('[Instagram] image verification:', info)
    if not ok:
        print('[Instagram] Image URL failed verification; aborting Instagram post')
        return

    # Validate aspect ratio for Instagram (must be between 0.8 and 1.91)
    try:
        from PIL import Image
        from io import BytesIO
        img_resp = requests.get(image_url, timeout=10)
        img_resp.raise_for_status()
        img = Image.open(BytesIO(img_resp.content))
        width, height = img.size
        aspect_ratio = width / height if height else 0
        print(f"[Instagram] Image size: {width}x{height}, aspect ratio: {aspect_ratio:.2f}")
        # If aspect ratio is invalid, auto-resize and upload to Cloudinary
        if aspect_ratio < 0.8 or aspect_ratio > 1.91:
            print(f"[Instagram] Image aspect ratio {aspect_ratio:.2f} is invalid. Auto-resizing...")
            # Calculate new size to fit within 0.8–1.91
            min_ratio, max_ratio = 0.8, 1.91
            new_width, new_height = width, height
            if aspect_ratio < min_ratio:
                # Too tall, pad/crop height
                new_height = int(width / min_ratio)
            elif aspect_ratio > max_ratio:
                # Too wide, pad/crop width
                new_width = int(height * max_ratio)
            # Center crop
            left = max((width - new_width) // 2, 0)
            top = max((height - new_height) // 2, 0)
            right = left + new_width
            bottom = top + new_height
            img = img.crop((left, top, right, bottom))
            # Save to buffer
            buf = BytesIO()
            img.save(buf, format='JPEG')
            buf.seek(0)
            # Upload to Cloudinary (requires cloudinary package and config)
            try:
                import cloudinary.uploader
                upload_result = cloudinary.uploader.upload(buf, folder="instagram_resized", resource_type="image")
                image_url = upload_result['secure_url']
                print(f"[Instagram] Uploaded resized image to Cloudinary: {image_url}")
            except Exception as e:
                print(f"[Instagram] Cloudinary upload failed: {e}. Skipping post.")
                return
    except Exception as e:
        print(f"[Instagram] Could not validate or resize image aspect ratio: {e}. Skipping post.")
        return

    media_url = f'https://graph.facebook.com/v19.0/{ig_account_id}/media'
    media_data = {
        'image_url': image_url,
        'caption': message,
        'access_token': access_token,
        'appsecret_proof': appsecret_proof
    }

    try:
        media_resp = requests.post(media_url, data=media_data, timeout=10)
        print('[Instagram] media HTTP status:', media_resp.status_code)
        try:
            media_result = media_resp.json()
        except Exception:
            print('[Instagram] media response text:', media_resp.text)
            media_result = {'error': 'invalid_json', 'text': media_resp.text}
        print('[Instagram] media response json:', media_result)
        if 'error' in media_result:
            print('[Instagram] media error details:', media_result.get('error'))
            return

        creation_id = media_result.get('id')
        if not creation_id:
            print('[Instagram] Failed to get creation id from media response')
            return

        # Poll for status until media is ready
        status_url = f'https://graph.facebook.com/v19.0/{creation_id}?fields=status_code&access_token={access_token}&appsecret_proof={appsecret_proof}'
        max_attempts = 10
        for attempt in range(max_attempts):
            try:
                status_resp = requests.get(status_url, timeout=10)
                status_json = status_resp.json()
                status_code = status_json.get('status_code')
                print(f'[Instagram] Media status attempt {attempt+1}: {status_code}')
                if status_code == 'FINISHED':
                    break
                elif status_code == 'ERROR':
                    print(f'[Instagram] Media processing error: {status_json}')
                    return
            except Exception as e:
                print(f'[Instagram] Error polling media status: {e}')
                return
            time.sleep(2)
        else:
            print('[Instagram] Media was not ready after polling. Skipping publish.')
            return

        publish_url = f'https://graph.facebook.com/v19.0/{ig_account_id}/media_publish'
        publish_data = {
            'creation_id': creation_id,
            'access_token': access_token,
            'appsecret_proof': appsecret_proof
        }
        publish_resp = requests.post(publish_url, data=publish_data, timeout=10)
        print('[Instagram] publish HTTP status:', publish_resp.status_code)
        try:
            publish_result = publish_resp.json()
        except Exception:
            print('[Instagram] publish response text:', publish_resp.text)
            publish_result = {'error': 'invalid_json', 'text': publish_resp.text}
        print('[Instagram] publish response json:', publish_result)
        if 'error' in publish_result:
            print('[Instagram] publish error details:', publish_result.get('error'))
            return
        print('[Instagram] successfully requested publish, response:', publish_result)

    except Exception as e:
        print('[Instagram] Error posting:', e)
        print(traceback.format_exc())


def post_multiple_to_facebook(message, image_urls):
    """Post multiple images to Facebook as a single feed post using unpublished photos."""
    page_id = getattr(settings, 'FACEBOOK_PAGE_ID', None)
    access_token = getattr(settings, 'FACEBOOK_PAGE_ACCESS_TOKEN', None)
    app_secret = getattr(settings, 'FACEBOOK_APP_SECRET', None)
    if not page_id or not access_token or not app_secret:
        print('FACEBOOK_PAGE_ID, FACEBOOK_PAGE_ACCESS_TOKEN, or FACEBOOK_APP_SECRET not set')
        return

    appsecret_proof = get_appsecret_proof(access_token, app_secret)
    uploaded_ids = []
    for img in image_urls:
        try:
            ok, info = _verify_image_url(img)
            print('[Facebook multi] image verification:', info)
            if not ok:
                print(f'[Facebook multi] skipping image (failed verification): {img}')
                continue
            url = f'https://graph.facebook.com/{page_id}/photos'
            data = {
                'url': img,
                'published': 'false',
                'access_token': access_token,
                'appsecret_proof': appsecret_proof,
            }
            resp = requests.post(url, data=data, timeout=10)
            try:
                rj = resp.json()
            except Exception:
                print('[Facebook multi] invalid json response:', resp.text)
                continue
            if 'id' in rj:
                uploaded_ids.append(rj['id'])
            else:
                print('[Facebook multi] upload photo failed:', rj)
        except Exception as e:
            print('[Facebook multi] error uploading photo:', e)
            print(traceback.format_exc())

    if not uploaded_ids:
        print('[Facebook multi] no photos uploaded, aborting multi-photo post')
        return

    try:
        feed_url = f'https://graph.facebook.com/{page_id}/feed'
        attached = [{'media_fbid': fid} for fid in uploaded_ids]
        data = {
            'message': message,
            'attached_media': json.dumps(attached),
            'access_token': access_token,
            'appsecret_proof': appsecret_proof,
        }
        resp = requests.post(feed_url, data=data, timeout=10)
        try:
            rj = resp.json()
        except Exception:
            print('[Facebook multi] feed response invalid json:', resp.text)
            return
        print('[Facebook multi] feed response:', rj)
    except Exception as e:
        print('[Facebook multi] error creating feed post:', e)
        print(traceback.format_exc())


def post_instagram_carousel(message, image_urls):
    """Create an Instagram carousel post from a list of image URLs.

    Steps: create child media objects with is_carousel_item=true, then create
    parent container with children and publish.
    """
    ig_account_id = getattr(settings, 'INSTAGRAM_BUSINESS_ACCOUNT_ID', None)
    access_token = getattr(settings, 'FACEBOOK_PAGE_ACCESS_TOKEN', None)
    app_secret = getattr(settings, 'FACEBOOK_APP_SECRET', None)
    if not ig_account_id or not access_token or not app_secret:
        print('INSTAGRAM_BUSINESS_ACCOUNT_ID, FACEBOOK_PAGE_ACCESS_TOKEN, or FACEBOOK_APP_SECRET not set')
        return

    appsecret_proof = get_appsecret_proof(access_token, app_secret)
    child_ids = []
    for img in image_urls[:10]:
        try:
            ok, info = _verify_image_url(img)
            print('[Instagram carousel] image verification:', info)
            if not ok:
                print(f'[Instagram carousel] skipping image (failed verification): {img}')
                continue
            # Validate and auto-fix aspect ratio before creating child media
            try:
                from PIL import Image as PILImage
                from io import BytesIO
                img_resp = requests.get(img, timeout=5)
                img_resp.raise_for_status()
                pil_img = PILImage.open(BytesIO(img_resp.content))
                width, height = pil_img.size
                aspect_ratio = width / height if height else 0
                print(f'[Instagram carousel] Image aspect ratio: {aspect_ratio:.2f} ({width}x{height})')
                
                # Instagram carousel requires 0.8 to 1.91 aspect ratio
                if aspect_ratio < 0.8 or aspect_ratio > 1.91:
                    print(f'[Instagram carousel] Auto-resizing image (aspect ratio {aspect_ratio:.2f}): {img}')
                    # Calculate new size to fit within 0.8–1.91
                    min_ratio, max_ratio = 0.8, 1.91
                    new_width, new_height = width, height
                    if aspect_ratio < min_ratio:
                        # Too tall, crop height
                        new_height = int(width / min_ratio)
                    elif aspect_ratio > max_ratio:
                        # Too wide, crop width
                        new_width = int(height * max_ratio)
                    # Center crop
                    left = max((width - new_width) // 2, 0)
                    top = max((height - new_height) // 2, 0)
                    right = left + new_width
                    bottom = top + new_height
                    pil_img = pil_img.crop((left, top, right, bottom))
                    # Upload resized to Cloudinary
                    buf = BytesIO()
                    pil_img.save(buf, format='JPEG', quality=95)
                    buf.seek(0)
                    try:
                        import cloudinary.uploader
                        print(f'[Instagram carousel] Uploading resized image to Cloudinary...')
                        upload_result = cloudinary.uploader.upload(
                            buf, 
                            folder="instagram_carousel_resized", 
                            resource_type="image",
                            timeout=30
                        )
                        img = upload_result.get('secure_url')
                        if not img:
                            print(f'[Instagram carousel] No secure_url in upload result: {upload_result}, skipping image')
                            continue
                        print(f'[Instagram carousel] Uploaded resized image to Cloudinary: {img}')
                    except Exception as e:
                        print(f'[Instagram carousel] Cloudinary upload failed: {e}')
                        print(f'[Instagram carousel] Traceback: {traceback.format_exc()}')
                        print(f'[Instagram carousel] Skipping image')
                        continue
            except Exception as e:
                print(f'[Instagram carousel] Could not process image {img}: {e}')
                continue
            
            media_url = f'https://graph.facebook.com/v19.0/{ig_account_id}/media'
            data = {
                'image_url': img,
                'is_carousel_item': 'true',
                'access_token': access_token,
                'appsecret_proof': appsecret_proof,
            }
            resp = requests.post(media_url, data=data, timeout=10)
            try:
                rj = resp.json()
            except Exception:
                print('[Instagram carousel] invalid json response:', resp.text)
                continue
            cid = rj.get('id')
            if cid:
                child_ids.append(cid)
            else:
                print('[Instagram carousel] child media creation failed:', rj)
        except Exception as e:
            print('[Instagram carousel] error creating child media:', e)
            print(traceback.format_exc())

    if len(child_ids) < 2:
        print(f'[Instagram carousel] Only {len(child_ids)} valid child media (need at least 2), aborting carousel')
        return

    try:
        parent_url = f'https://graph.facebook.com/v19.0/{ig_account_id}/media'
        data = {
            'children': json.dumps(child_ids),
            'caption': message,
            'access_token': access_token,
            'appsecret_proof': appsecret_proof,
        }
        resp = requests.post(parent_url, data=data, timeout=10)
        try:
            rj = resp.json()
        except Exception:
            print('[Instagram carousel] parent media invalid json:', resp.text)
            return
        creation_id = rj.get('id')
        if not creation_id:
            print('[Instagram carousel] failed to create parent container:', rj)
            return

        publish_url = f'https://graph.facebook.com/v19.0/{ig_account_id}/media_publish'
        publish_data = {
            'creation_id': creation_id,
            'access_token': access_token,
            'appsecret_proof': appsecret_proof,
        }
        pub_resp = requests.post(publish_url, data=publish_data, timeout=10)
        try:
            pub_rj = pub_resp.json()
        except Exception:
            print('[Instagram carousel] publish invalid json:', pub_resp.text)
            return
        print('[Instagram carousel] publish response:', pub_rj)
    except Exception as e:
        print('[Instagram carousel] error publishing carousel:', e)
        print(traceback.format_exc())

@receiver(post_save, sender=ProductImage)
def announce_product_image(sender, instance, created, **kwargs):
    """When a ProductImage is saved, post ALL product images as a carousel to FB and IG.
    
    This creates a single multi-image post instead of individual posts per image.
    Uses cache-based deduplication to avoid multiple posts when saving multiple images.
    """
    try:
        product = instance.product
        # Only act when the image file exists on the instance
        if not getattr(instance, 'image', None):
            return
        
        # Deduplication: only post once per product within 60 seconds
        cache_key = f'product_posted_{product.id}'
        if cache.get(cache_key):
            print(f'[ProductImage signal] Skipping post for product {product.id} (already posted recently)')
            return
        # Set cache lock for 60 seconds
        cache.set(cache_key, True, 60)
        
        from django.db import transaction
        def do_post():
            try:
                product = instance.product
                
                # Collect ALL image URLs for this product
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
                        uploaded = _upload_image_to_cloudinary(img.image)
                        if uploaded:
                            img_url = uploaded
                        else:
                            print(f"[ProductImage signal] Unable to upload to Cloudinary for image: {img}")
                            # Skip this image if upload failed and it's relative
                            if img_url.startswith('/'):
                                continue
                    
                    image_urls.append(img_url)
                
                if not image_urls:
                    print(f"[ProductImage signal] No valid images to post for product {product.id}")
                    return
                
                # Build sizes/stock/price string
                size_lines = []
                for size_obj in product.sizes.all():
                    price = size_obj.price if size_obj.price != 0 else product.base_price
                    size_str = f"{size_obj.size} ({size_obj.stock}) - ₱{price}"
                    size_lines.append(size_str)
                sizes_info = "\n".join(size_lines)
                
                message = (
                    f"🚨 New Photos Just In! 🚨\n"
                    f"Check out the {product.brand} {product.name}—now with more angles!\n\n"
                    f"Sizes & Stock:\n{sizes_info}\n\n"
                    f"See all the details: https://www.sidestep.studio/product/{product.id}/\n"
                    f"Got questions or want to reserve? Slide into our DMs! #sidestep #sneakerupdate"
                )
                
                print(f"[ProductImage signal] Posting {len(image_urls)} images as carousel for product {product.id}")
                # Post as multi-image carousel
                post_multiple_to_facebook(message, image_urls)
                post_instagram_carousel(message, image_urls)
                
                # Mark product as published after successful posting
                if not product.is_published:
                    from django.utils import timezone
                    product.is_published = True
                    product.published_at = timezone.now()
                    product.save(update_fields=['is_published', 'published_at'])
                    print(f"[ProductImage signal] Marked product {product.id} as published")
            except Exception as e:
                print('[ProductImage signal] Error handling product image post:', e)
                print(traceback.format_exc())
        
        # Run the external-posting work in a background thread so the DB
        # transaction/worker isn't blocked by network calls (prevents timeouts).
        transaction.on_commit(lambda: threading.Thread(target=do_post, daemon=True).start())
    except Exception as e:
        print('[ProductImage signal] Error in announce_product_image:', e)
        print(traceback.format_exc())
