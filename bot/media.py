# bot/media.py
# Показ фото профиля: превращает сохранённый токен в вложение MAX.
# Фото пользователь присылает в анкете, мы храним его token (db/models.py: Profile.photo)
# и здесь собираем из него готовое вложение для отправки в карточке.

from maxapi.enums.upload_type import UploadType
from maxapi.types.attachments.upload import AttachmentPayload, AttachmentUpload


def photo_attachment(profile: dict):
    """Вложение-фото по сохранённому токену. None, если фото нет или собрать не удалось."""
    token = (profile or {}).get("photo")
    if not token:
        return None
    try:
        return AttachmentUpload(type=UploadType.IMAGE, payload=AttachmentPayload(token=token))
    except Exception:
        return None


def with_photo(profile: dict, keyboard) -> list:
    """attachments = фото профиля (если есть) + переданная клавиатура."""
    photo = photo_attachment(profile)
    return ([photo] if photo else []) + list(keyboard or [])
