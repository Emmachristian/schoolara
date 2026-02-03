# accounts/ajax_views.py

from .models import UserProfile
import json
import base64
import os
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
import logging

logger = logging.getLogger(__name__)

@login_required
@require_http_methods(["POST"])
def update_profile_picture(request):
    """Update user profile picture via AJAX"""
    try:
        # Parse the JSON body
        data = json.loads(request.body)
        image_data = data.get("image")

        if not image_data:
            return JsonResponse(
                {"success": False, "message": "No image data provided."},
                status=400
            )
        
        # Ensure user has a profile
        if not hasattr(request.user, 'profile'):
            UserProfile.objects.create(user=request.user)
        
        user_profile = request.user.profile
        extension = None

        # Handle base64 prefix and determine extension
        if image_data.startswith("data:image/jpeg;base64,"):
            image_data = image_data[len("data:image/jpeg;base64,"):]
            extension = ".jpg"
        elif image_data.startswith("data:image/png;base64,"):
            image_data = image_data[len("data:image/png;base64,"):]
            extension = ".png"
        elif image_data.startswith("data:image/gif;base64,"):
            image_data = image_data[len("data:image/gif;base64,"):]
            extension = ".gif"
        else:
            return JsonResponse(
                {"success": False, "message": "Unsupported image format. Only JPG, PNG, and GIF are allowed."},
                status=400
            )
        
        # Decode base64 string
        try:
            image_data_decoded = base64.b64decode(image_data)
        except Exception:
            return JsonResponse(
                {"success": False, "message": "Invalid image data."},
                status=400
            )
        
        # Generate the file name
        file_name = f"{request.user.username}_profile{extension}"

        # Delete old photo file if exists
        if user_profile.photo:
            old_file_path = user_profile.photo.path
            if os.path.exists(old_file_path):
                try:
                    os.remove(old_file_path)
                except Exception as e:
                    # Log the error but continue
                    logger.warning(f"Could not delete old profile photo: {e}")

        # Wrap decoded bytes in ContentFile and save to ImageField
        from django.core.files.base import ContentFile
        profile_picture = ContentFile(image_data_decoded)
        user_profile.photo.save(file_name, profile_picture, save=True)

        logger.info(f"Profile picture updated for user: {request.user.username}")

        return JsonResponse({
            "success": True,
            "message": "Profile picture updated successfully!",
            "image_url": user_profile.photo.url
        })
    
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."},
            status=400
        )
    
    except Exception as e:
        logger.error(f"Error updating profile picture: {str(e)}")
        return JsonResponse(
            {"success": False, "message": f"Server error: {str(e)}"},
            status=500
        )