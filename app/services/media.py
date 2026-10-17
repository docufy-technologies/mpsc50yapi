import io
from typing import BinaryIO
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.settings import settings


async def validate_image_upload(upload_file: UploadFile) -> bytes:
    """Validate uploaded file content-type and payload size before loading into PIL."""
    _upload_cap = settings.image_upload_size_cap_bytes
    if (
        not upload_file.content_type
        or upload_file.content_type.lower() not in settings.allowed_image_mime_types
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format. Allowed formats: JPEG, PNG, WEBP, BMP, TIFF.",
        )

    # Read up to MAX_UPLOAD_SIZE + 1 bytes to prevent huge files buffering in memory
    content = await upload_file.read(_upload_cap + 1)
    if len(content) > _upload_cap:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image size exceeds the maximum limit of {settings.image_upload_size_cap_bytes / (1024 * 1024)} MB.",
        )

    return content


def _process_img(image_file: BinaryIO) -> io.BytesIO:
    """Resize image to within settings.img_max_dimension and compress to WEBP."""
    _max_dimension = settings.max_allowed_dimension
    _target_byte_size: int = settings.max_allowed_image_size_bytes
    try:
        img = Image.open(image_file)
        # Verify image integrity (catches corrupted/truncated images and malicious payloads)
        img.verify()

        # reopen after verify since verify leaves the file pointer in an undefined state
        image_file.seek(0)
        img = Image.open(image_file)

        # Convert RGBA/palette/grayscale to RGB or keep RGBA if transparency is present
        if img.mode in ("RGBA", "LA") or (
            img.mode == "P" and "transparency" in img.info
        ):
            # RGBA is supported by WEBP
            img = img.convert("RGBA")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        original_width, original_height = img.size

        # Only resize if the longest side > max_dim
        if max(original_width, original_height) > _max_dimension:
            if original_width > original_height:
                new_width = _max_dimension
                new_height = int(original_height * (new_width / original_width))
            else:
                new_height = _max_dimension
                new_width = int(original_width * (new_height / original_height))

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Iteratively compress to fit within target size
        quality = 85
        min_quality = 10
        best_buffer: io.BytesIO | None = None

        while quality >= min_quality:
            img_buffer = io.BytesIO()
            img.save(img_buffer, "WEBP", quality=quality, method=4)
            size = img_buffer.tell()

            if size <= _target_byte_size:
                img_buffer.seek(0)
                return img_buffer

            best_buffer = img_buffer
            quality -= 10

        # If even at min_quality it exceeds target_size_bytes, return best compressed version
        if best_buffer:
            best_buffer.seek(0)
            return best_buffer

        img_buffer = io.BytesIO()
        img.save(img_buffer, "WEBP", quality=min_quality)
        img_buffer.seek(0)
        return img_buffer

    except (UnidentifiedImageError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image data: {e}",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process image: {e}",
        ) from e
    finally:
        image_file.close()


def save_alumni_profile_picture(processed_buffer: io.BytesIO) -> str:
    """Save processed image buffer to disk with a uuid4 filename and return filename."""
    filename = f"{uuid4().hex}.webp"
    file_path = settings.form_alumni_pfp_file_path(filename)

    with open(file_path, "wb") as f:
        f.write(processed_buffer.getbuffer())

    return filename


def delete_alumni_profile_picture(filename: str) -> None:
    """Delete profile picture from disk if it exists."""
    if not filename:
        return

    file_path = settings.form_alumni_pfp_file_path(filename)
    if file_path.is_file():
        try:
            file_path.unlink()
        except OSError:
            pass
