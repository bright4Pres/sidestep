
import os
from django.conf import settings
import requests
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Product

def post_to_instagram(message, image_url=None):
    ig_account_id = getattr(settings, 'INSTAGRAM_BUSINESS_ACCOUNT_ID', None)
    access_token = getattr(settings, 'FACEBOOK_PAGE_ACCESS_TOKEN', None)
    if not ig_account_id or not access_token:
        print('INSTAGRAM_BUSINESS_ACCOUNT_ID or FACEBOOK_PAGE_ACCESS_TOKEN not set')
        return
    if not image_url:
        print('Image URL required for Instagram post')
        return
    # Step 1: Create media object
    media_url = f'https://graph.facebook.com/v19.0/{ig_account_id}/media'
    media_data = {
        'image_url': image_url,
        'caption': message,
        'access_token': access_token
    }
    try:
        media_resp = requests.post(media_url, data=media_data)
        media_result = media_resp.json()
        print('Instagram media response:', media_result)
        creation_id = media_result.get('id')
        if not creation_id:
            print('Failed to create Instagram media object')
            return
        # Step 2: Publish media object
        publish_url = f'https://graph.facebook.com/v19.0/{ig_account_id}/media_publish'
        publish_data = {
            'creation_id': creation_id,
            'access_token': access_token
        }
        publish_resp = requests.post(publish_url, data=publish_data)
        print('Instagram publish response:', publish_resp.json())
    except Exception as e:
        print('Error posting to Instagram:', e)

def post_to_facebook_page(message, image_url=None):
    page_id = getattr(settings, 'FACEBOOK_PAGE_ID', None)
    access_token = getattr(settings, 'FACEBOOK_PAGE_ACCESS_TOKEN', None)
    if not page_id or not access_token:
        print('FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN not set')
        return
    if image_url:
        url = f'https://graph.facebook.com/{page_id}/photos'
        data = {
            'caption': message,
            'url': image_url,
            'access_token': access_token
        }
    else:
        url = f'https://graph.facebook.com/{page_id}/feed'
        data = {
            'message': message,
            'access_token': access_token
        }
    try:
        response = requests.post(url, data=data)
        print('Facebook post response:', response.json())
    except Exception as e:
        print('Error posting to Facebook:', e)

@receiver(post_save, sender=Product)
def announce_new_shoe(sender, instance, created, **kwargs):
    if created:
        # Get the first image URL from Cloudinary
        image_url = None
        first_image = instance.images.first()
        if first_image and first_image.image:
            image_url = first_image.image.url
        message = f"A new shoe is now available! {instance.brand} {instance.name}! Check it out on: https://sidestep.studio/product/{instance.id}/. For inquiries, DM us on Facebook or Instagram!"
        post_to_facebook_page(message, image_url)
        if image_url:
            post_to_instagram(message, image_url)
