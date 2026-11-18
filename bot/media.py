from maxapi.enums.upload_type import UploadType
from maxapi.types.attachments.upload import AttachmentPayload, AttachmentUpload


def photo_attachment(profile: dict):
    """Вложение-фото по сохранённому токену. None, если фото нет или собрать не удалось."""
    token = (profile or {}).get("photo")
    # Фото из мини-приложения (web:<файл>) и из Telegram (tgfile:<id>) — не токены MAX,
    # в чат бота MAX их не прикрепляем.
    if not token or token.startswith(("web:", "tgfile:")):
        return None
    try:
        return AttachmentUpload(type=UploadType.IMAGE, payload=AttachmentPayload(token=token))
    except Exception:
        return None


def with_photo(profile: dict, keyboard) -> list:
    """attachments = фото профиля (если есть) + переданная клавиатура."""
    photo = photo_attachment(profile)
    return ([photo] if photo else []) + list(keyboard or [])
