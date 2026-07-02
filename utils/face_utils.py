import base64
import os
import uuid
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
REFERENCE_DIR = os.path.join("uploads", "student_photos")
SELFIE_DIR = os.path.join("uploads", "selfies")


def _extension(filename):
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def _validate_image_bytes(raw):
    if not raw:
        raise ValueError("Please upload a student photo.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Photo must be smaller than 5 MB.")

    try:
        image = Image.open(BytesIO(raw))
        image.verify()
    except (UnidentifiedImageError, OSError):
        raise ValueError("Please upload a valid image file.")


def _normalise_image(raw):
    image = Image.open(BytesIO(raw))
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((900, 900))
    return image


def save_student_reference_photo(file_storage, user_id, upload_root):
    filename = secure_filename(file_storage.filename or "") if file_storage else ""
    ext = _extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Student photo must be JPG, PNG, or WebP.")

    raw = file_storage.read()
    _validate_image_bytes(raw)

    image = _normalise_image(raw)
    relative_dir = REFERENCE_DIR
    absolute_dir = os.path.join(upload_root, relative_dir)
    os.makedirs(absolute_dir, exist_ok=True)

    stored_name = f"{user_id}.{ext if ext != 'jpeg' else 'jpg'}"
    relative_path = os.path.join(relative_dir, stored_name).replace("\\", "/")
    absolute_path = os.path.join(upload_root, relative_path)
    image.save(absolute_path, quality=90)
    return relative_path


def save_selfie_from_data_url(data_url, user_id, upload_root):
    if not data_url or "," not in data_url:
        raise ValueError("Please capture a selfie first.")

    header, encoded = data_url.split(",", 1)
    if "image/" not in header:
        raise ValueError("Selfie must be an image.")

    try:
        raw = base64.b64decode(encoded)
    except (ValueError, TypeError):
        raise ValueError("Selfie image could not be read.")

    _validate_image_bytes(raw)
    image = _normalise_image(raw)

    relative_dir = SELFIE_DIR
    absolute_dir = os.path.join(upload_root, relative_dir)
    os.makedirs(absolute_dir, exist_ok=True)

    stored_name = f"{user_id}_{uuid.uuid4().hex}.jpg"
    relative_path = os.path.join(relative_dir, stored_name).replace("\\", "/")
    absolute_path = os.path.join(upload_root, relative_path)
    image.save(absolute_path, quality=88)
    return relative_path


def _center_square(image):
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))


def _difference_hash(image, size=16):
    image = _center_square(image)
    image = ImageOps.grayscale(image).resize((size + 1, size), Image.Resampling.LANCZOS)
    pixels = list(image.getdata())
    bits = []
    for row in range(size):
        row_start = row * (size + 1)
        for col in range(size):
            bits.append(pixels[row_start + col] > pixels[row_start + col + 1])
    return bits


def compare_student_faces(reference_path, selfie_path, upload_root):
    reference_image = Image.open(os.path.join(upload_root, reference_path))
    selfie_image = Image.open(os.path.join(upload_root, selfie_path))

    reference_hash = _difference_hash(ImageOps.exif_transpose(reference_image).convert("RGB"))
    selfie_hash = _difference_hash(ImageOps.exif_transpose(selfie_image).convert("RGB"))
    difference = sum(1 for a, b in zip(reference_hash, selfie_hash) if a != b)
    score = difference / len(reference_hash)

    return score <= 0.32, score
