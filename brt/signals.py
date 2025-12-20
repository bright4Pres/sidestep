def get_appsecret_proof(access_token, app_secret):
    """Generate appsecret_proof for Facebook API requests."""
    return hmac.new(app_secret.encode('utf-8'), access_token.encode('utf-8'), hashlib.sha256).hexdigest()


import os
import traceback
import time
import requests
import hmac
import hashlib
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Product, ProductImage

"""Signals: auto-post new products to Facebook and Instagram with debug logging.

This file verifies image URLs and logs full API responses to help debug failures.
"""


def _verify_image_url(image_url, timeout=10):
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
        response = requests.post(url, data=data, timeout=20)
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

    media_url = f'https://graph.facebook.com/v19.0/{ig_account_id}/media'
    media_data = {
        'image_url': image_url,
        'caption': message,
        'access_token': access_token,
        'appsecret_proof': appsecret_proof
    }

    try:
        media_resp = requests.post(media_url, data=media_data, timeout=20)
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

        publish_url = f'https://graph.facebook.com/v19.0/{ig_account_id}/media_publish'
        publish_data = {
            'creation_id': creation_id,
            'access_token': access_token,
            'appsecret_proof': appsecret_proof
        }
        publish_resp = requests.post(publish_url, data=publish_data, timeout=20)
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


@receiver(post_save, sender=Product)
def announce_new_shoe(sender, instance, created, **kwargs):
    if created:
        # Try to obtain the image URL — sometimes images are saved shortly after the product
        image_url = None
        attempts = 8
        for i in range(attempts):
            first_image = instance.images.first()
            if first_image and getattr(first_image, 'image', None):
                try:
                    url = first_image.image.url
                except Exception:
                    url = None
                if url:
                    image_url = url
                    break
            time.sleep(1)

        print(f"[Signal] Product image_url after polling: {image_url}")
        message = f"A new shoe is now available! {instance.brand} {instance.name}! Check it out on: https://www.sidestep.studio/product/{instance.id}/. For inquiries, DM us on Facebook or Instagram!"

        # Post to Facebook (with image if available)
        post_to_facebook_page(message, image_url)

        # Post to Instagram only if we have an image (Instagram requires an image)
        if image_url:
            post_to_instagram(message, image_url)
        else:
            print('[Signal] No image available — skipped Instagram post. Consider posting when product image is saved (use ProductImage post_save handler for reliable behavior).')


@receiver(post_save, sender=ProductImage)
def announce_product_image(sender, instance, created, **kwargs):
    """When a ProductImage is saved (especially primary), post the image to FB and IG.

    This handles the case where the Product was created before the image was available.
    """
    try:
        product = instance.product
        # Only act when the image file exists on the instance
        if not getattr(instance, 'image', None):
            return
        try:
            image_url = instance.image.url
        except Exception:
            image_url = None
        if not image_url:
            return

        # Build a message similar to the product announcement
        message = f"A new shoe is now available! {product.brand} {product.name}! Check it out on: https://www.sidestep.studio/product/{product.id}/. For inquiries, DM us on Facebook or Instagram!"

        print(f"[ProductImage signal] Posting image for product {product.id}: {image_url}")
        # Post photo to Facebook (this will create a new post containing the image)
        post_to_facebook_page(message, image_url)

        # Post to Instagram
        post_to_instagram(message, image_url)
    except Exception as e:
        print('[ProductImage signal] Error handling product image post:', e)
        print(traceback.format_exc())
