"""Мини-приложение Тиммейт: HTTP API + статика фронтенда.

Работает поверх того же ядра (core/) и той же базы (db/), что и бот в MAX.
Один и тот же фронтенд открывается и в Telegram, и в MAX — площадку клиент
сообщает в заголовке X-Platform, а сервер проверяет подпись initData токеном этой площадки.

Запуск: uvicorn webapp.main:app --host 0.0.0.0 --port 8080
"""

import asyncio
import contextlib
import secrets
import logging
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from bot import keyboards as kb
from bot import media as bot_media
from bot import texts
from config import LAW_152_URL, settings
from core.interactions import incoming_likes, is_match, matches_for
from core.recommendations import build_feed, explain
from db import repo
from db.session import init_db
from messengers import ids, notify
from webapp import profiles
from webapp.auth import AuthError, WebAppUser, dev_user, validate

log = logging.getLogger("webapp")

STATIC_DIR = Path(__file__).resolve().parent / "static"
MEDIA_DIR = Path(settings.media_dir).resolve()
MAX_PHOTO_BYTES = 5 * 1024 * 1024
FEED_PAGE = 10

_background: set[asyncio.Task] = set()

LIKED_NUDGE_TG = "Кто-то оценил твою анкету 👀 Загляни в ленту — вдруг взаимно!"


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    # Тестовые анкеты загружает бот; если бот не запущен (локально) — загрузим сами.
    for attempt in range(5):
        try:
            await init_db(seed=not settings.bot_token)
            break
        except Exception as exc:  # бот и мини-апп стартуют одновременно и могут столкнуться на create_all
            log.warning("init_db (попытка %s): %s", attempt + 1, exc)
            await asyncio.sleep(2)
    # Telegram опрашивает отдельный сервис tgbot (диалог в чате + кнопка мини-приложения).
    yield


app = FastAPI(title="Тиммейт — мини-приложение", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.exception_handler(AuthError)
async def _auth_error(_: Request, exc: AuthError):
    return JSONResponse(status_code=401, content={"detail": str(exc)})


# Авторизация

async def current_user(
    authorization: str = Header(default=""),
    x_platform: str = Header(default=""),
) -> WebAppUser:
    """Authorization: tma <initData>, X-Platform: tg | max."""
    scheme, _, payload = authorization.partition(" ")
    if scheme == "dev" and settings.dev_auth:
        user = dev_user(payload)
    elif scheme != "tma" or not payload:
        raise AuthError("Открой приложение из Telegram или MAX")
    else:
        user = validate(x_platform, payload)
    # Аккаунт может быть подключён к анкете из другого мессенджера — дальше работаем с id анкеты.
    return replace(user, profile_id=await repo.resolve_id(user.user_id))


async def my_profile_or_404(user: WebAppUser) -> dict:
    profile = await repo.get_profile(user.profile_id)
    if profile is None:
        raise HTTPException(404, "Сначала заполни анкету")
    return profile


# Профиль

@app.get("/api/me")
async def me(user: WebAppUser = Depends(current_user)):
    profile = await repo.get_profile(user.profile_id)
    data = {
        "user": {
            "platform": user.platform,
            "first_name": user.first_name,
            "username": user.username,
            "start_param": user.start_param,
        },
        "profile": None,
        "options": profiles.options(),
        "search_mode": await repo.get_search_mode(user.profile_id),
        "event_id": await repo.get_target_event(user.profile_id),
        "stats": {"incoming_likes": 0, "matches": 0},
        "report_email": settings.support_email,
        "legal": {
            "consent_url": "/legal/consent",
            "privacy_url": "/legal/privacy",
            "law_url": LAW_152_URL,
            "consent_version": settings.consent_version,
        },
        "linked": [],
    }
    if profile:
        data["profile"] = {**profiles.card(profile, contact=True), "is_active": profile["is_active"]}
        data["linked"] = sorted(await repo.profile_platforms(user.profile_id))
        likes = await repo.get_likes_involving(user.profile_id)
        swiped = await repo.get_swiped_ids(user.profile_id)
        data["stats"] = {
            "incoming_likes": len(incoming_likes(likes, user.profile_id, swiped)),
            "matches": len(matches_for(likes, user.profile_id)),
        }
    return data


@app.put("/api/profile")
async def save_profile(payload: dict, user: WebAppUser = Depends(current_user)):
    existing = await repo.get_profile(user.profile_id)
    if existing is None and payload.get("consent") is not True:
        raise HTTPException(400, "Нужно согласие на обработку данных")
    clean, errors = profiles.validate_profile(payload)
    if errors:
        return JSONResponse(status_code=422, content={"detail": "Проверь анкету", "errors": errors})
    if existing is None and payload.get("force_new") is not True:
        # Тот же контакт уже есть у анкеты из другого мессенджера — скорее всего, человек уже с нами.
        duplicate = await repo.find_duplicate(user.user_id, clean["username"])
        if duplicate:
            other = "MAX" if ids.platform_of(duplicate["user_id"]) == "max" else "Telegram"
            return JSONResponse(status_code=409, content={
                "detail": f"Похоже, у тебя уже есть анкета в {other}",
                "code": "duplicate",
                "platform": other,
                "contact": duplicate.get("username") or "",
            })
    # Новую анкету создаём от id аккаунта — так в журнал согласий попадает, откуда дано согласие.
    saved = await repo.save_profile(user.user_id if existing is None else user.profile_id, clean)
    return {**profiles.card(saved, contact=True), "is_active": saved["is_active"]}


def _delete_photo_file(profile: dict | None) -> None:
    photo = (profile or {}).get("photo") or ""
    if photo.startswith("web:"):
        with contextlib.suppress(OSError):
            (MEDIA_DIR / Path(photo[4:]).name).unlink()


def _image_ext(head: bytes) -> str | None:
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


@app.post("/api/profile/photo")
async def upload_photo(file: UploadFile = File(...), user: WebAppUser = Depends(current_user)):
    profile = await my_profile_or_404(user)
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Фото больше 5 МБ")
    ext = _image_ext(data[:16])
    if ext is None:
        raise HTTPException(415, "Нужна картинка JPG, PNG или WEBP")
    name = f"{uuid.uuid4().hex}.{ext}"
    (MEDIA_DIR / name).write_bytes(data)
    _delete_photo_file(profile)
    saved = await repo.save_profile(user.profile_id, {"photo": f"web:{name}"})
    return {"photo_url": profiles.photo_url(saved)}


@app.delete("/api/profile/photo")
async def delete_photo(user: WebAppUser = Depends(current_user)):
    profile = await my_profile_or_404(user)
    _delete_photo_file(profile)
    await repo.save_profile(user.profile_id, {"photo": ""})
    return {"ok": True}


@app.post("/api/profile/visibility")
async def set_visibility(payload: dict, user: WebAppUser = Depends(current_user)):
    await my_profile_or_404(user)
    active = bool(payload.get("active"))
    await repo.set_active(user.profile_id, active)
    return {"is_active": active}


@app.delete("/api/profile")
async def delete_profile(user: WebAppUser = Depends(current_user)):
    """Удалить анкету, лайки, мэтчи, настройки, привязки и фото (152-ФЗ, ст. 21) — во всех мессенджерах."""
    _delete_photo_file(await repo.get_profile(user.profile_id))
    await repo.delete_profile(user.profile_id)
    return {"ok": True}


# Настройки поиска

@app.put("/api/settings")
async def update_settings(payload: dict, user: WebAppUser = Depends(current_user)):
    out = {}
    if "search_mode" in payload:
        out["search_mode"] = await repo.set_search_mode(
            user.profile_id, str(payload.get("search_mode") or "all")
        )
    if "event_id" in payload:
        raw = payload.get("event_id")
        out["event_id"] = await repo.set_target_event(user.profile_id, int(raw) if raw else None)
    if not out:
        out["search_mode"] = await repo.get_search_mode(user.profile_id)
    return out


@app.get("/api/events")
async def events(user: WebAppUser = Depends(current_user)):
    """Лента мероприятий. Заполняется руками, поэтому отдаём как есть."""
    return {
        "items": await repo.list_events(),
        "event_id": await repo.get_target_event(user.profile_id),
    }


# Лента

def _filter_pool(me_profile: dict, pool: list, mode: str) -> list:
    """Тот же фильтр, что в боте: только мой вуз / только мой город."""
    field = {"university": "university", "city": "city"}.get(mode)
    if not field:
        return pool
    key = (me_profile.get(field) or "").strip().lower()
    return [p for p in pool if key and (p.get(field) or "").strip().lower() == key]


@app.get("/api/feed")
async def feed(user: WebAppUser = Depends(current_user)):
    me_profile = await my_profile_or_404(user)
    mode = await repo.get_search_mode(user.profile_id)
    pool = _filter_pool(me_profile, await repo.list_active_profiles(), mode)
    # Цель поиска сужает пул до тех, кто идёт на то же мероприятие. Человека
    # без цели в событийный пул не затягиваем: он туда не собирался.
    event_id = await repo.get_target_event(user.profile_id)
    event = await repo.get_event(event_id)
    if event:
        targeting = await repo.ids_targeting(event["id"])
        pool = [p for p in pool if p["user_id"] in targeting]
    items = build_feed(me_profile, pool, await repo.get_swiped_ids(user.profile_id))
    return {
        "search_mode": mode,
        "event": event,
        "items": [
            {
                "profile": profiles.card(item["profile"]),
                "score": item["score"],
                "reasons": item["details"],
                "explain": explain(item["details"]),
            }
            for item in items[:FEED_PAGE]
        ],
        "remaining": max(len(items) - FEED_PAGE, 0),
        "skipped": await repo.count_skips(user.profile_id),
    }


@app.post("/api/feed/reset-skips")
async def reset_skips(user: WebAppUser = Depends(current_user)):
    await repo.reset_skips(user.profile_id)
    return {"ok": True}


async def _notify_partner(me_profile: dict, partner: dict, matched: bool, message: str) -> None:
    if partner.get("is_test"):
        return
    if matched:
        note = "🎉 У тебя новый мэтч!\n\n" + texts.profile_card(me_profile, show_contact=True)
        if message:
            note += f"\n\n💬 Сообщение: {message}"
        await notify.send_to_profile(
            partner["user_id"], note,
            max_attachments=bot_media.with_photo(me_profile, kb.after_match_kb()),
        )
    else:
        await notify.send_to_profile(
            partner["user_id"], "Кто-то оценил твою анкету 👀 Загляни в «Искать сокомандников» — вдруг взаимно!",
            max_attachments=kb.liked_nudge_kb(), tg_text=LIKED_NUDGE_TG,
        )


@app.post("/api/swipe")
async def swipe(payload: dict, user: WebAppUser = Depends(current_user)):
    me_profile = await my_profile_or_404(user)
    target_id = str(payload.get("to_id") or "")
    action = payload.get("action")
    if action not in ("like", "skip") or not target_id or target_id == user.profile_id:
        raise HTTPException(400, "Неверный запрос")
    partner = await repo.get_profile(target_id)
    if partner is None:
        raise HTTPException(404, "Анкета уже удалена")

    if action == "skip":
        await repo.save_swipe(user.profile_id, target_id, liked=False)
        return {"matched": False}

    message, error = profiles.validate_message(str(payload.get("message") or ""))
    if error:
        return JSONResponse(status_code=422, content={"detail": error, "errors": {"message": error}})

    await repo.save_swipe(user.profile_id, target_id, liked=True, message=message)
    if partner.get("is_test"):
        # Тестовые анкеты лайкают в ответ — чтобы сценарий мэтча можно было пройти сразу.
        await repo.save_swipe(target_id, user.profile_id, liked=True)
    likes = await repo.get_likes_involving(user.profile_id)
    matched = is_match(likes, user.profile_id, target_id)

    # Уведомление не задерживает ответ интерфейсу. Ссылку на задачу храним,
    # иначе сборщик мусора может прибить её до отправки.
    task = asyncio.create_task(_notify_partner(me_profile, partner, matched, message))
    _background.add(task)
    task.add_done_callback(_background.discard)
    result: dict = {"matched": matched}
    if matched:
        result["partner"] = profiles.card(partner, contact=True)
    return result


# Мэтчи

@app.get("/api/matches")
async def matches(user: WebAppUser = Depends(current_user)):
    await my_profile_or_404(user)
    me = user.profile_id
    likes = await repo.get_likes_involving(me)
    result = []
    for pid in matches_for(likes, me):
        partner = await repo.get_profile(pid)
        if not partner:
            continue
        their = next((l for l in likes if l["from_id"] == pid and l["to_id"] == me), {})
        mine = next((l for l in likes if l["from_id"] == me and l["to_id"] == pid), {})
        result.append({
            "profile": profiles.card(partner, contact=True),
            "their_message": their.get("message") or "",
            "my_message": mine.get("message") or "",
        })
    return {"items": result}


# Одна анкета на человека: подключение второго мессенджера

def _other_platform_link(platform: str, code: str) -> str:
    """Ссылка, по которой второй мессенджер сразу откроется с кодом."""
    if platform == "max" and settings.telegram_bot_username:
        return f"https://t.me/{settings.telegram_bot_username}?start=link-{code}"
    if platform == "tg" and settings.max_bot_username:
        return f"https://max.ru/{settings.max_bot_username}?startapp=link-{code}"
    return ""


@app.post("/api/link/code")
async def link_code(user: WebAppUser = Depends(current_user)):
    """Выдать одноразовый код (10 минут), чтобы подключить к анкете второй мессенджер."""
    await my_profile_or_404(user)
    code, expires = await repo.create_link_code(user.profile_id)
    return {
        "code": code,
        "expires_at": expires.isoformat(),
        "link": _other_platform_link(user.platform, code),
    }


@app.post("/api/link")
async def link_redeem(payload: dict, user: WebAppUser = Depends(current_user)):
    """Ввести код из другого мессенджера: этот аккаунт начнёт работать с той анкетой."""
    try:
        await repo.redeem_link_code(str(payload.get("code") or ""), user.user_id, replace=payload.get("replace") is True)
    except repo.LinkError as exc:
        status = 409 if exc.code == "has_profile" else 400
        return JSONResponse(status_code=status, content={"detail": exc.message, "code": exc.code})
    return {"ok": True}


# Документы по персональным данным (152-ФЗ)

# Редактор мероприятий: /admin
#
# Включается только непустым ADMIN_TOKEN в .env. Пустой токен — эндпоинты
# отвечают 404, чтобы редактор нельзя было оставить открытым по недосмотру.


def admin_guard(x_admin_token: str = Header(default="")) -> None:
    if not settings.admin_token:
        raise HTTPException(404, "Редактор выключен: задайте ADMIN_TOKEN")
    if not secrets.compare_digest(x_admin_token or "", settings.admin_token):
        raise HTTPException(401, "Неверный токен")


def _clean_event(payload: dict) -> dict:
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(422, "Название обязательно")
    out = {"title": title[:200]}
    limits = {"organizer": 120, "url": 500, "city": 100, "format": 40, "team_size": 20, "about": 4000}
    for field, limit in limits.items():
        if field in payload:
            out[field] = str(payload.get(field) or "").strip()[:limit]
    for field in ("starts_on", "deadline_on"):
        if field in payload:
            raw = str(payload.get(field) or "").strip()
            if raw:
                try:
                    datetime.strptime(raw, "%Y-%m-%d")
                except ValueError:
                    raise HTTPException(422, "Дата должна быть в формате ГГГГ-ММ-ДД")
            out[field] = raw
    if "is_published" in payload:
        out["is_published"] = bool(payload.get("is_published"))
    return out


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/api/admin/events", dependencies=[Depends(admin_guard)])
async def admin_events():
    return {"items": await repo.admin_list_events()}


@app.post("/api/admin/events", dependencies=[Depends(admin_guard)])
async def admin_create_event(payload: dict):
    return await repo.create_event(_clean_event(payload))


@app.put("/api/admin/events/{event_id}", dependencies=[Depends(admin_guard)])
async def admin_update_event(event_id: int, payload: dict):
    out = await repo.update_event(event_id, _clean_event(payload))
    if not out:
        raise HTTPException(404, "Мероприятие не найдено")
    return out


@app.delete("/api/admin/events/{event_id}", dependencies=[Depends(admin_guard)])
async def admin_delete_event(event_id: int):
    if not await repo.delete_event(event_id):
        raise HTTPException(404, "Мероприятие не найдено")
    return {"ok": True}


LEGAL_DIR = STATIC_DIR / "legal"


def _legal_page(name: str) -> HTMLResponse:
    html = (LEGAL_DIR / f"{name}.html").read_text(encoding="utf-8")
    for key, value in {
        "{{CONSENT_VERSION}}": settings.consent_version,
        "{{SUPPORT_EMAIL}}": settings.support_email,
        "{{LAW_URL}}": LAW_152_URL,
    }.items():
        html = html.replace(key, value)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/legal/consent", response_class=HTMLResponse)
async def legal_consent():
    return _legal_page("consent")


@app.get("/legal/privacy", response_class=HTMLResponse)
async def legal_privacy():
    return _legal_page("privacy")


# Статика

@app.get("/media/{name}")
async def media_file(name: str):
    path = MEDIA_DIR / Path(name).name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=604800"})


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/")
async def index():
    # index.html не кэшируем: после выкладки клиенты сразу получают новую версию.
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
