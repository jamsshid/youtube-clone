from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Video, VideoLike
from .forms import VideoUploadForm
from .imagekit_client import (
    upload_thumbnail,
    delete_video as delete_video_from_imagekit,
)
import os


def imagekit_auth(request):
    from .imagekit_client import get_imagekit_client
    import hashlib
    import hmac
    import time
    import os

    private_key = os.environ.get("IMAGEKIT_PRIVATE_KEY", "")
    token = os.urandom(16).hex()
    expire = int(time.time()) + 3600

    signature = hmac.new(
        private_key.encode(), f"{token}{expire}".encode(), hashlib.sha1
    ).hexdigest()

    return JsonResponse(
        {
            "token": token,
            "expire": expire,
            "signature": signature,
        }
    )


def video_detail(request, video_id):
    video = get_object_or_404(Video.objects.select_related("user"), id=video_id)
    video.views += 1
    video.save(update_fields=["views"])

    user_vote = None
    if request.user.is_authenticated:
        like = VideoLike.objects.filter(video=video, user=request.user).first()
        if like:
            user_vote = like.value
    return render(
        request, "videos/detail.html", {"video": video, "user_vote": user_vote}
    )


def video_list(request):
    videos = Video.objects.all().order_by("-created_at")
    return render(request, "videos/list.html", {"videos": videos})


def channel_videos(request, username):
    videos = Video.objects.filter(user__username=username).order_by("-created_at")
    return render(
        request, "videos/channel.html", {"videos": videos, "channel_name": username}
    )


@login_required()
@require_POST
def video_upload(request):
    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    file_id = request.POST.get("file_id", "")
    video_url = request.POST.get("video_url", "")
    custom_thumbnail = request.POST.get("thumbnail_data", "")

    if not title or not file_id or not video_url:
        return JsonResponse({"success": False, "error": "Missing required fields"})

    try:
        thumbnail_url = ""
        if custom_thumbnail and custom_thumbnail.startswith("data:image"):
            try:
                thumb_result = upload_thumbnail(
                    file_data=custom_thumbnail,
                    file_name=file_id + "_thumb.jpg",
                )
                thumbnail_url = thumb_result["url"]
            except Exception:
                pass

        video = Video.objects.create(
            user=request.user,
            title=title,
            description=description,
            file_id=file_id,
            video_url=video_url,
            thumbnail_url=thumbnail_url,
        )

        return JsonResponse(
            {
                "success": True,
                "video_id": video.id,
                "message": "Video uploaded successfully",
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@login_required()
def video_upload_page(request):
    return render(
        request,
        "videos/upload.html",
        {
            "form": VideoUploadForm(),
            "imagekit_public_key": os.environ.get("IMAGEKIT_PUBLIC_KEY", ""),
            "imagekit_url_endpoint": os.environ.get("IMAGEKIT_URL_ENDPOINT", ""),
        },
    )


@login_required()
@require_POST
def delete_video(request, video_id):
    video = get_object_or_404(Video, id=video_id, user=request.user)
    try:
        delete_video_from_imagekit(video.file_id)
    except Exception as e:
        print(e)
        pass
    video.delete()
    return JsonResponse({"success": True, "message": "Video deleted successfully"})


@login_required()
@require_POST
def video_vote(request, video_id):
    video = get_object_or_404(Video, id=video_id)
    vote_type = request.POST.get("vote")

    if vote_type not in ["like", "dislike"]:
        return JsonResponse(
            {"success": False, "error": "Invalid vote type"}, status=400
        )

    value = VideoLike.LIKE if vote_type == "like" else VideoLike.DISLIKE
    existing_vote = VideoLike.objects.filter(video=video, user=request.user).first()

    if existing_vote:
        if existing_vote.value == value:
            if value == VideoLike.LIKE:
                video.likes -= 1
            else:
                video.dislikes -= 1
            existing_vote.delete()
            user_vote = None
        else:
            if value == VideoLike.LIKE:
                video.likes += 1
                video.dislikes -= 1
            else:
                video.likes -= 1
                video.dislikes += 1
            existing_vote.value = value
            existing_vote.save()
            user_vote = value
    else:
        VideoLike.objects.create(user=request.user, video=video, value=value)
        if value == VideoLike.LIKE:
            video.likes += 1
        else:
            video.dislikes += 1
        user_vote = value

    video.save(update_fields=["likes", "dislikes"])
    return JsonResponse(
        {
            "likes": video.likes,
            "dislikes": video.dislikes,
            "user_vote": user_vote,
        }
    )
