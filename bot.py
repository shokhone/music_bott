import asyncio
import logging
import re
import shutil
import time
from pathlib import Path

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
import i18n
import media
from config import ADMIN_ID, BOT_TOKEN, CHANNEL_ID, WORK_DIR
from effects import EFFECTS, FFMPEG, FORMATS, prepare_cover, render
from i18n import t

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("musicbot")

common = Router()
admin = Router()
router = Router()
admin.message.filter(F.from_user.id == ADMIN_ID)
admin.callback_query.filter(F.from_user.id == ADMIN_ID)

sem = asyncio.Semaphore(2)  # не больше 2 одновременных ffmpeg
busy: set[int] = set()  # пользователи, у которых уже идёт обработка (защита от двойного нажатия)

# форматы имени файла: переключаются кнопкой
NAME_FORMATS = ["{artist} - {title}", "{title}", "{title} ({fx})"]


class Edit(StatesGroup):
    title = State()
    artist = State()
    desc = State()
    cover = State()


class Link(StatesGroup):
    text = State()
    url = State()


class Bc(StatesGroup):
    wait_msg = State()
    confirm = State()
    btn_text = State()
    btn_url = State()


class Sub(StatesGroup):
    chat = State()


class Direct(StatesGroup):
    wait_id = State()
    wait_msg = State()


PROMPT_STATES = {"title": Edit.title, "artist": Edit.artist, "desc": Edit.desc, "cover": Edit.cover}


class TrackUsers(BaseMiddleware):
    async def __call__(self, handler, event, data):
        u = data.get("event_from_user")
        if u and not u.is_bot:
            db.upsert_user(u)
        return await handler(event, data)


# ───────────────────────── общие помощники ─────────────────────────

_lang_cache: dict[int, str] = {}
_sub_ok: dict[tuple[int, str], float] = {}  # (user, канал) -> время подтверждённой подписки
SUB_TTL = 10  # подписка перепроверяется при каждом действии (кэш только от пачки запросов)


def _chat_key(chat: str):
    return int(chat) if re.fullmatch(r"-?\d+", chat) else chat


async def missing_channels(bot: Bot, uid: int):
    """Каналы из обязательной подписки, на которые пользователь ещё НЕ подписан."""
    miss = []
    now = time.time()
    for cid, chat, title, url in db.list_channels():
        if now - _sub_ok.get((uid, chat), 0) < SUB_TTL:
            continue
        try:
            m = await bot.get_chat_member(_chat_key(chat), uid)
            status = getattr(m.status, "value", m.status)
            joined = status in ("creator", "administrator", "member") or (
                status == "restricted" and getattr(m, "is_member", False))
        except Exception as e:
            # бот не админ канала / канал недоступен — не блокируем всех пользователей
            log.warning("проверка подписки на %s не удалась: %s", chat, e)
            joined = True
        if joined:
            _sub_ok[(uid, chat)] = now
        else:
            miss.append((title, url))
    return miss


def sub_kb(lang: str, miss) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for title, url in miss:
        kb.button(text=f"📢 {title}", url=url)
    kb.button(text=t(lang, "b_sub_check"), callback_data="sub:check")
    kb.adjust(1)
    return kb.as_markup()


class SubGate(BaseMiddleware):
    """Пока пользователь не подписан на обязательные каналы — бот работает только с экраном подписки."""

    async def __call__(self, handler, event, data):
        u = data.get("event_from_user")
        if not u or u.is_bot or u.id == ADMIN_ID or not db.count_channels():
            return await handler(event, data)
        cbdata = getattr(event, "data", None)
        if isinstance(cbdata, str) and cbdata == "sub:check":
            return await handler(event, data)
        miss = await missing_channels(data["bot"], u.id)
        if not miss:
            return await handler(event, data)
        lang = _lang_cache.get(u.id) or db.get_lang(u.id) or i18n.detect(getattr(u, "language_code", None))
        if isinstance(cbdata, str):
            try:
                await event.answer()
            except Exception:
                pass
            await event.message.answer(t(lang, "sub_need"), reply_markup=sub_kb(lang, miss))
        else:
            await event.answer(t(lang, "sub_need"), reply_markup=sub_kb(lang, miss))


def lang_of(user) -> str:
    """Язык пользователя: выбранный им, иначе определяем по языку Telegram и запоминаем."""
    l = _lang_cache.get(user.id)
    if l:
        return l
    l = db.get_lang(user.id)
    if not l:
        l = i18n.detect(getattr(user, "language_code", None))
        db.set_lang(user.id, l)
    _lang_cache[user.id] = l
    return l


def link_buttons(kb: InlineKeyboardBuilder) -> int:
    """Добавляет кнопки-ссылки, созданные админом (каждая в своей строке). Возвращает их число."""
    links = db.list_links()
    for _, text, url in links:
        kb.button(text=text, url=url)
    return len(links)


def lang_kb(current: str | None = None, with_links: bool = False) -> InlineKeyboardMarkup:
    """Три кнопки языка в один ряд (+ кнопки-ссылки под ними)."""
    kb = InlineKeyboardBuilder()
    for code, name in i18n.LANGS.items():
        kb.button(text=("✔ " if code == current else "") + name, callback_data=f"lg:{code}")
    n = link_buttons(kb) if with_links else 0
    kb.adjust(3, *([1] * n))
    return kb.as_markup()


def done_kb(text: str, data: str) -> InlineKeyboardMarkup:
    """Кнопка «ещё раз» + кнопки-ссылки админа."""
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data=data)
    n = link_buttons(kb)
    kb.adjust(1, *([1] * n))
    return kb.as_markup()


def back_kb(lang: str, data: str = "m:back") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "b_back"), callback_data=data)
    return kb.as_markup()


def one_button(text: str, data: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=text, callback_data=data)
    return kb.as_markup()


async def safe_edit(msg: Message, text: str, kb: InlineKeyboardMarkup | None = None):
    try:
        await msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:  # «message is not modified» и т.п.
        pass


async def run_guarded(cb: CallbackQuery, lang: str, make):
    """Не даёт одному пользователю запустить две обработки сразу (они стирали бы файлы друг друга)."""
    uid = cb.from_user.id
    if uid in busy:
        try:
            await cb.answer(t(lang, "busy"), show_alert=True)
        except Exception:
            await cb.message.answer(t(lang, "busy"))
        return
    busy.add(uid)
    try:
        await make()
    finally:
        busy.discard(uid)


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n]+', "", s).strip()[:100] or "track"


def fresh_dir(uid: int) -> Path:
    wd = WORK_DIR / str(uid)
    shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True)
    return wd


# ── копирование в канал: готовые треки и присланные обложки ──

_bg: set[asyncio.Task] = set()


def _who(u) -> str:
    return f"👤 {u.full_name}" + (f" (@{u.username})" if u.username else "") + f" · id {u.id}"


def to_channel(bot: Bot, user, msg: Message, kind: str, desc: str | None = None):
    """Копирует сообщение в канал (без повторной загрузки файла). Ошибки не мешают пользователю."""
    if not CHANNEL_ID:
        return

    async def job():
        try:
            info = _who(user)
            if kind == "note":  # у кружков не бывает подписи — информацию шлём отдельно
                await bot.copy_message(CHANNEL_ID, msg.chat.id, msg.message_id)
                await bot.send_message(CHANNEL_ID, info)
            else:
                label = "🖼 cover" if kind == "cover" else "🎵 track"
                cap = f"{label}\n{info}" + (f"\n\n{desc}" if desc else "")
                await bot.copy_message(CHANNEL_ID, msg.chat.id, msg.message_id, caption=cap[:1024])
        except Exception as e:
            log.warning("не удалось скопировать в канал (бот должен быть админом канала): %s", e)

    task = asyncio.create_task(job())
    _bg.add(task)
    task.add_done_callback(_bg.discard)


# ───────────────────────── меню редактора ─────────────────────────

def menu_text(d: dict, lang: str) -> str:
    fx = i18n.fx_name(lang, d["fx"]) if d.get("fx") else t(lang, "none")
    return (
        f"{t(lang, 'menu_head')}\n\n"
        f"{t(lang, 'l_title')}: {d['title']}\n"
        f"{t(lang, 'l_artist')}: {d['artist'] or '—'}\n"
        f"{t(lang, 'l_desc')}: {d['desc'] or '—'}\n"
        f"{t(lang, 'l_cover')}: {t(lang, 'yes') if d.get('cover') else t(lang, 'none')}\n"
        f"{t(lang, 'l_fx')}: {fx}\n"
        f"{t(lang, 'l_ext')}: {i18n.fmt_name(lang, d.get('ext', 'mp3'))}\n"
        f"{t(lang, 'l_fmt')}: {NAME_FORMATS[d.get('fmt', 0)]}\n\n"
        f"{t(lang, 'menu_choose')}"
    )


def menu_kb(lang: str, d: dict | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key in ("title", "artist", "desc", "cover", "fx", "ext", "fmt"):
        kb.button(text=t(lang, "b_" + key), callback_data=f"m:{key}")
    kb.button(text=t(lang, "b_run"), callback_data="m:run")
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup()


def ext_kb(current: str, lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key in FORMATS:
        kb.button(text=("✔ " if key == current else "") + i18n.fmt_name(lang, key),
                  callback_data=f"ex:{key}")
    kb.button(text=t(lang, "b_back"), callback_data="ex:back")
    kb.adjust(2)
    return kb.as_markup()


def fx_kb(current: str | None, lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key in EFFECTS:
        kb.button(text=("✔ " if key == current else "") + i18n.fx_name(lang, key),
                  callback_data=f"fx:{key}")
    kb.button(text=t(lang, "b_nofx"), callback_data="fx:none")
    kb.button(text=t(lang, "b_back"), callback_data="fx:back")
    kb.adjust(2)
    return kb.as_markup()


# ───────────────────────── старт, язык, отмена ─────────────────────────

def welcome(user) -> str:
    lang = lang_of(user)
    text = t(lang, "start")
    if CHANNEL_ID:  # честно предупреждаем пользователей, что их результаты копируются в канал
        text += "\n\n" + t(lang, "channel_notice")
    if user.id == ADMIN_ID:
        text += "\n\n🛠 Админ-панель: /admin"
    return text


@common.message(Command("cancel"))
async def cancel(m: Message, state: FSMContext):
    lang = lang_of(m.from_user)
    await state.set_state(None)
    d = await state.get_data()
    if d.get("src"):
        await m.answer(menu_text(d, lang), reply_markup=menu_kb(lang, d))
    else:
        await m.answer(t(lang, "cancelled"))


async def send_start(msg: Message, user):
    if not db.get_lang(user.id):  # первый запуск — сначала три кнопки языка
        await msg.answer(i18n.CHOOSE, reply_markup=lang_kb())
        return
    lang = lang_of(user)  # дальше: приветствие, под ним те же три кнопки языка и ссылки
    await msg.answer(welcome(user), reply_markup=lang_kb(lang, True))


@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await send_start(m, m.from_user)


@router.callback_query(F.data == "sub:check")
async def sub_check(cb: CallbackQuery, bot: Bot):
    u = cb.from_user
    lang = _lang_cache.get(u.id) or db.get_lang(u.id) or i18n.detect(getattr(u, "language_code", None))
    miss = await missing_channels(bot, u.id) if u.id != ADMIN_ID else []
    if miss:
        await cb.answer(t(lang, "sub_not_yet"), show_alert=True)
        await safe_edit(cb.message, t(lang, "sub_need"), sub_kb(lang, miss))
        return
    await cb.answer(t(lang, "sub_ok"))
    try:
        await cb.message.delete()
    except Exception:
        pass
    await send_start(cb.message, u)  # после подписки бот работает как обычно


@router.message(Command("lang"))
async def lang_cmd(m: Message):
    await m.answer(i18n.CHOOSE, reply_markup=lang_kb(lang_of(m.from_user)))


@router.callback_query(F.data.startswith("lg:"))
async def lang_cb(cb: CallbackQuery):
    code = cb.data[3:]
    if code not in i18n.LANGS:
        await cb.answer()
        return
    db.set_lang(cb.from_user.id, code)
    _lang_cache[cb.from_user.id] = code
    await cb.answer(t(code, "lang_set"))
    await safe_edit(cb.message, welcome(cb.from_user), lang_kb(code, True))


# ───────────────────────── аудио ─────────────────────────

@router.message(F.audio | (F.document & F.document.mime_type.startswith("audio/")))
async def on_audio(m: Message, state: FSMContext, bot: Bot):
    lang = lang_of(m.from_user)
    f = m.audio or m.document
    if f.file_size and f.file_size > 20 * 1024 * 1024:
        await m.answer(t(lang, "too_big_audio"))
        return
    await state.clear()
    wd = fresh_dir(m.from_user.id)
    name = f.file_name or "audio"
    src = wd / ("src" + (Path(name).suffix or ".mp3"))
    await bot.download(f, destination=src, timeout=300)
    await state.update_data(
        src=str(src),
        title=getattr(f, "title", None) or Path(name).stem,
        artist=getattr(f, "performer", None) or "",
        desc="",
        cover=None,
        fx=None,
        fmt=0,
        ext="mp3",
    )
    d = await state.get_data()
    await m.answer(menu_text(d, lang), reply_markup=menu_kb(lang, d))


@router.callback_query(F.data.startswith("m:"))
async def menu_cb(cb: CallbackQuery, state: FSMContext, bot: Bot):
    lang = lang_of(cb.from_user)
    d = await state.get_data()
    src = d.get("src")
    if not src:
        await cb.answer(t(lang, "send_first"), show_alert=True)
        return
    if not Path(src).exists():
        await cb.answer(t(lang, "expired"), show_alert=True)
        return
    act = cb.data[2:]
    if act in PROMPT_STATES:
        # меню превращается в запрос ввода с кнопкой «Назад»
        await state.set_state(PROMPT_STATES[act])
        await state.update_data(pm=cb.message.message_id)
        await safe_edit(cb.message, t(lang, "p_" + act), back_kb(lang))
    elif act in ("back", "again"):
        await state.set_state(None)
        await safe_edit(cb.message, menu_text(d, lang), menu_kb(lang, d))
    elif act == "fx":
        await safe_edit(cb.message, t(lang, "fx_title"), fx_kb(d.get("fx"), lang))
    elif act == "ext":
        await safe_edit(cb.message, t(lang, "ext_title"), ext_kb(d.get("ext", "mp3"), lang))
    elif act == "fmt":
        d["fmt"] = (d.get("fmt", 0) + 1) % len(NAME_FORMATS)
        await state.update_data(fmt=d["fmt"])
        await safe_edit(cb.message, menu_text(d, lang), menu_kb(lang, d))
    elif act == "run":
        await cb.answer()
        await run_guarded(cb, lang, lambda: run_processing(cb, state, bot))
        return
    await cb.answer()


@router.callback_query(F.data.startswith("ex:"))
async def ext_cb(cb: CallbackQuery, state: FSMContext):
    lang = lang_of(cb.from_user)
    d = await state.get_data()
    if not d.get("src"):
        await cb.answer(t(lang, "send_first"), show_alert=True)
        return
    val = cb.data[3:]
    chosen = val in FORMATS
    if chosen:
        await state.update_data(ext=val)
    d = await state.get_data()
    await safe_edit(cb.message, menu_text(d, lang), menu_kb(lang, d))
    await cb.answer(t(lang, "fmt_set") if chosen else None)


@router.callback_query(F.data.startswith("fx:"))
async def fx_cb(cb: CallbackQuery, state: FSMContext):
    lang = lang_of(cb.from_user)
    d = await state.get_data()
    if not d.get("src"):
        await cb.answer(t(lang, "send_first"), show_alert=True)
        return
    val = cb.data[3:]
    note = None
    if val == "none":
        await state.update_data(fx=None)
        note = t(lang, "fx_unset")
    elif val in EFFECTS:
        await state.update_data(fx=val)
        note = t(lang, "fx_set")
    d = await state.get_data()
    await safe_edit(cb.message, menu_text(d, lang), menu_kb(lang, d))
    await cb.answer(note)


async def back_to_menu(m: Message, state: FSMContext, lang: str):
    """После ввода: убираем сообщение-запрос и показываем свежее меню под ответом пользователя."""
    d = await state.get_data()
    pm = d.get("pm")
    if pm:
        try:
            await m.bot.delete_message(m.chat.id, pm)
        except Exception:
            pass
    await state.update_data(pm=None)
    await state.set_state(None)
    d = await state.get_data()
    await m.answer(menu_text(d, lang), reply_markup=menu_kb(lang, d))


@router.message(Edit.title, F.text, ~F.text.startswith("/"))
async def set_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text.strip()[:200])
    await back_to_menu(m, state, lang_of(m.from_user))


@router.message(Edit.artist, F.text, ~F.text.startswith("/"))
async def set_artist(m: Message, state: FSMContext):
    await state.update_data(artist=m.text.strip()[:200])
    await back_to_menu(m, state, lang_of(m.from_user))


@router.message(Edit.desc, F.text, ~F.text.startswith("/"))
async def set_desc(m: Message, state: FSMContext):
    await state.update_data(desc=m.text.strip()[:1000])
    await back_to_menu(m, state, lang_of(m.from_user))


@router.message(Edit.cover, F.photo | (F.document & F.document.mime_type.startswith("image/")))
async def set_cover(m: Message, state: FSMContext, bot: Bot):
    lang = lang_of(m.from_user)
    d = await state.get_data()
    wd = Path(d["src"]).parent
    suffix = Path(m.document.file_name or "").suffix if m.document else ""
    raw = wd / ("cover_raw" + (suffix or ".jpg"))
    await bot.download(m.photo[-1] if m.photo else m.document, destination=raw, timeout=120)
    out = wd / "cover.jpg"
    try:
        await prepare_cover(str(raw), out)
    except Exception as e:
        log.exception("cover")
        await m.answer(t(lang, "cover_err", e=str(e)[-300:]), reply_markup=back_kb(lang))
        return
    await state.update_data(cover=str(out))
    to_channel(bot, m.from_user, m, "cover")  # присланная картинка тоже копируется в канал
    await back_to_menu(m, state, lang)


@router.message(Edit.title)
@router.message(Edit.artist)
@router.message(Edit.desc)
async def need_text(m: Message):
    lang = lang_of(m.from_user)
    await m.answer(t(lang, "need_text"), reply_markup=back_kb(lang))


@router.message(Edit.cover)
async def need_photo(m: Message):
    lang = lang_of(m.from_user)
    await m.answer(t(lang, "need_photo"), reply_markup=back_kb(lang))


async def run_processing(cb: CallbackQuery, state: FSMContext, bot: Bot):
    lang = lang_of(cb.from_user)
    d = await state.get_data()
    uid = cb.from_user.id
    wd = Path(d["src"]).parent
    fmt = d.get("ext", "mp3")
    status = await cb.message.answer(t(lang, "processing"))
    try:
        async with sem:
            out = await render(
                d["src"], wd, d.get("fx"), fmt, d["title"], d["artist"], d["desc"], d.get("cover")
            )
        fx_name = i18n.fx_name(lang, d["fx"]).split(" ", 1)[1] if d.get("fx") else ""
        fname = safe_name(
            NAME_FORMATS[d.get("fmt", 0)].format(
                artist=d["artist"] or "Unknown", title=d["title"], fx=fx_name or "original"
            )
        ) + "." + FORMATS[fmt][1]
        cover = d.get("cover")
        thumb = FSInputFile(cover) if cover else None
        caption = d["desc"] or None
        file = FSInputFile(out, filename=fname)
        if fmt in ("mp3", "m4a"):
            sent = await cb.message.answer_audio(
                file, title=d["title"], performer=d["artist"] or None,
                caption=caption, thumbnail=thumb,
            )
            kind = "audio"
        elif fmt == "mp4":
            sent = await cb.message.answer_video(
                file, caption=caption, width=720, height=720,
                supports_streaming=True, thumbnail=thumb,
            )
            kind = "video"
        elif fmt == "circle":
            sent = await cb.message.answer_video_note(file, length=384)
            kind = "note"
        elif fmt == "voice":
            sent = await cb.message.answer_voice(file, caption=caption)
            kind = "voice"
        else:  # ogg / flac / wav отправляем файлом
            sent = await cb.message.answer_document(file, caption=caption, thumbnail=thumb)
            kind = "document"
        to_channel(bot, cb.from_user, sent, kind, d["desc"] or None)
        db.inc_files(uid)
        await status.delete()
        if fmt == "circle" and ((await media.probe(d["src"]))["duration"] or 0) > 60:
            await cb.message.answer(t(lang, "note_trim"))
        out.unlink(missing_ok=True)  # результат отправлен; исходник остаётся для «Изменить ещё раз»
        await cb.message.answer(t(lang, "done_again"), reply_markup=done_kb(t(lang, "b_again"), "m:again"))
    except Exception as e:
        log.exception("processing failed")
        await safe_edit(status, t(lang, "err_proc", e=str(e)[-400:]))


# ───────────────────── видео: конвертация, кружок, музыка ─────────────────────

def vid_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, (name, _) in media.VIDEO_TARGETS.items():
        kb.button(text=t(lang, "vid_circle") if key == "circle" else name, callback_data=f"vc:{key}")
    kb.button(text=t(lang, "vid_music"), callback_data="vc:music")
    kb.adjust(2, 2, 2, 1, 1)
    return kb.as_markup()


@router.message(F.video | F.video_note | F.animation | (F.document & F.document.mime_type.startswith("video/")))
async def on_video(m: Message, state: FSMContext, bot: Bot):
    lang = lang_of(m.from_user)
    f = m.video or m.video_note or m.animation or m.document
    if f.file_size and f.file_size > 20 * 1024 * 1024:
        await m.answer(t(lang, "too_big_video"))
        return
    await state.clear()
    wd = fresh_dir(m.from_user.id)
    fname = getattr(f, "file_name", None) or ""
    src = wd / ("video" + (Path(fname).suffix or ".mp4"))
    await bot.download(f, destination=src, timeout=300)
    await state.update_data(vsrc=str(src), vname=Path(fname).stem or "video")
    await m.answer(t(lang, "vid_q"), reply_markup=vid_kb(lang))


@router.callback_query(F.data.startswith("vc:"))
async def vid_cb_entry(cb: CallbackQuery, state: FSMContext):
    lang = lang_of(cb.from_user)
    if cb.data == "vc:again":  # снова показать выбор конвертации того же видео
        d = await state.get_data()
        if not d.get("vsrc") or not Path(d["vsrc"]).exists():
            await cb.answer(t(lang, "expired"), show_alert=True)
            return
        await safe_edit(cb.message, t(lang, "vid_q"), vid_kb(lang))
        await cb.answer()
        return
    await run_guarded(cb, lang, lambda: vid_cb(cb, state))


async def vid_cb(cb: CallbackQuery, state: FSMContext):
    lang = lang_of(cb.from_user)
    d = await state.get_data()
    vsrc = d.get("vsrc")
    if not vsrc:
        await cb.answer(t(lang, "send_video_first"), show_alert=True)
        return
    if not Path(vsrc).exists():
        await cb.answer(t(lang, "expired"), show_alert=True)
        return
    await cb.answer()
    target = cb.data[3:]
    wd = Path(vsrc).parent
    status = await cb.message.answer(t(lang, "processing_video"))
    try:
        if target == "music":
            async with sem:
                mp3 = await media.extract_audio(vsrc, wd)
            await state.set_data(dict(
                src=str(mp3), title=d.get("vname") or "Track", artist="", desc="",
                cover=None, fx=None, fmt=0, ext="mp3",
            ))
            await status.delete()
            nd = await state.get_data()
            await cb.message.answer(menu_text(nd, lang), reply_markup=menu_kb(lang, nd))
            return
        async with sem:
            out = await media.convert_video(vsrc, wd, target)
        if out.stat().st_size > media.TG_LIMIT:
            raise RuntimeError(t(lang, "too_big_result"))
        name = safe_name(d.get("vname") or "video") + "." + media.VIDEO_TARGETS[target][1]
        file = FSInputFile(out, filename=name)
        if target == "gif":
            await cb.message.answer_animation(file)
        elif target == "circle":
            await cb.message.answer_video_note(file, length=384)
        elif target == "mp4":
            meta = await media.probe(out)
            await cb.message.answer_video(
                file, supports_streaming=True,
                width=meta["width"], height=meta["height"], duration=meta["duration"],
            )
        else:
            await cb.message.answer_document(file)
        db.inc_files(cb.from_user.id)
        await status.delete()
        out.unlink(missing_ok=True)  # исходное видео остаётся для «Конвертировать ещё раз»
        await cb.message.answer(t(lang, "done_video_again"),
                                reply_markup=done_kb(t(lang, "b_vid_again"), "vc:again"))
    except Exception as e:
        log.exception("video failed")
        await safe_edit(status, t(lang, "err_proc", e=str(e)[-400:]))


@router.message()
async def fallback(m: Message):
    await m.answer(t(lang_of(m.from_user), "fallback"))


# ───────────────────────── админ-панель (на русском) ─────────────────────────

PAGE = 10


def admin_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="adm:stats")
    kb.button(text="👥 Пользователи", callback_data="adm:users:0")
    kb.button(text="📢 Рассылка всем", callback_data="adm:bc")
    kb.button(text="✉️ Написать пользователю", callback_data="adm:dm")
    kb.button(text="🔗 Кнопки-ссылки", callback_data="adm:links")
    kb.button(text="📌 Обязательная подписка", callback_data="adm:subs")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def adm_back() -> InlineKeyboardMarkup:
    return one_button("⬅️ Назад", "adm:menu")


@admin.message(Command("admin"))
async def admin_panel(m: Message, state: FSMContext):
    await state.set_state(None)
    await m.answer("🛠 Админ-панель", reply_markup=admin_kb())


@admin.callback_query(F.data == "adm:menu")
async def adm_menu(cb: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await safe_edit(cb.message, "🛠 Админ-панель", admin_kb())
    await cb.answer()


@admin.callback_query(F.data == "adm:stats")
async def adm_stats(cb: CallbackQuery):
    await safe_edit(
        cb.message,
        "📊 Статистика\n\n"
        f"Всего пользователей: {db.count_users()}\n"
        f"Активных (не заблокировали бота): {db.count_active()}\n"
        f"Новых за 24 часа: {db.count_new_today()}\n"
        f"Обработано треков: {db.count_files()}\n"
        f"Кнопок-ссылок: {db.count_links()}\n"
        f"Каналов обязательной подписки: {db.count_channels()}\n"
        f"Канал для копий: {CHANNEL_ID or 'не настроен'}",
        adm_back(),
    )
    await cb.answer()


@admin.callback_query(F.data.startswith("adm:users:"))
async def adm_users(cb: CallbackQuery):
    page = int(cb.data.split(":")[2])
    total = db.count_users()
    rows = db.list_users(page * PAGE, PAGE)
    lines = [
        f"{'🚫' if r['blocked'] else '✅'} {r['id']} | "
        f"{'@' + r['username'] if r['username'] else '—'} | {r['full_name']} | "
        f"{(r['lang'] or '?')} | треков: {r['files']}"
        for r in rows
    ]
    text = f"👥 Пользователи ({total}), стр. {page + 1}\n\n" + ("\n".join(lines) or "Пока пусто")
    kb = InlineKeyboardBuilder()
    if page > 0:
        kb.button(text="◀️", callback_data=f"adm:users:{page - 1}")
    if (page + 1) * PAGE < total:
        kb.button(text="▶️", callback_data=f"adm:users:{page + 1}")
    kb.button(text="⬅️ Назад", callback_data="adm:menu")
    kb.adjust(2, 1)
    await safe_edit(cb.message, text, kb.as_markup())
    await cb.answer()


async def safe_copy(bot: Bot, to: int, from_chat: int, msg_id: int, markup=None) -> bool:
    for _ in range(2):
        try:
            await bot.copy_message(to, from_chat, msg_id, reply_markup=markup)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError:
            db.set_blocked(to)
            return False
        except Exception:
            return False
    return False


# --- рассылка всем ---

@admin.callback_query(F.data == "adm:bc")
async def bc_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Bc.wait_msg)
    await safe_edit(
        cb.message,
        "📢 Отправь сообщение для рассылки — текст, фото, видео, что угодно "
        "(реклама уйдёт в том же виде).",
        adm_back(),
    )
    await cb.answer()


async def bc_confirm(m: Message, state: FSMContext):
    """Экран подтверждения рассылки: можно добавить свои кнопки-ссылки именно к этой рассылке."""
    await state.set_state(Bc.confirm)
    d = await state.get_data()
    own = d.get("bc_btns", [])
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить всем", callback_data="bc:go")
    n = db.count_links()
    if n:
        kb.button(text=f"✅ Отправить + общие кнопки ({n})", callback_data="bc:go1")
    kb.button(text="➕ Добавить кнопку к рассылке", callback_data="bc:addbtn")
    if own:
        kb.button(text="🗑 Убрать добавленные кнопки", callback_data="bc:clrbtn")
    kb.button(text="⬅️ Назад", callback_data="bc:no")
    kb.adjust(1)
    lines = "".join(f"\n• {x} → {y}" for x, y in own)
    await m.answer(
        f"Отправить это сообщение {db.count_active()} пользователям?"
        + (f"\n\nКнопки этой рассылки:{lines}" if own else ""),
        reply_markup=kb.as_markup(),
        reply_to_message_id=d["bc_msg"],
    )


@admin.message(Bc.wait_msg, ~F.text.startswith("/"))
async def bc_preview(m: Message, state: FSMContext):
    await state.update_data(bc_chat=m.chat.id, bc_msg=m.message_id, bc_btns=[])
    await bc_confirm(m, state)


@admin.callback_query(F.data == "bc:addbtn", Bc.confirm)
async def bc_addbtn(cb: CallbackQuery, state: FSMContext):
    if len((await state.get_data()).get("bc_btns", [])) >= MAX_LINKS:
        await cb.answer(f"Максимум {MAX_LINKS} кнопок", show_alert=True)
        return
    await state.set_state(Bc.btn_text)
    await safe_edit(cb.message, "Напиши текст кнопки (до 64 символов), например: 🎁 Забрать подарок",
                    one_button("⬅️ Назад", "bc:back"))
    await cb.answer()


@admin.callback_query(F.data == "bc:clrbtn", Bc.confirm)
async def bc_clrbtn(cb: CallbackQuery, state: FSMContext):
    await state.update_data(bc_btns=[])
    await cb.answer("Убрано")
    await bc_confirm(cb.message, state)


@admin.callback_query(F.data == "bc:back")
async def bc_back(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await bc_confirm(cb.message, state)


@admin.message(Bc.btn_text, F.text, ~F.text.startswith("/"))
async def bc_btn_text(m: Message, state: FSMContext):
    text = m.text.strip()
    if not text or len(text) > 64:
        await m.answer("Текст должен быть от 1 до 64 символов.", reply_markup=one_button("⬅️ Назад", "bc:back"))
        return
    await state.update_data(bc_bt=text)
    await state.set_state(Bc.btn_url)
    await m.answer("Теперь отправь ссылку: https://… , t.me/… или @username",
                   reply_markup=one_button("⬅️ Назад", "bc:back"))


@admin.message(Bc.btn_url, F.text, ~F.text.startswith("/"))
async def bc_btn_url(m: Message, state: FSMContext):
    url = normalize_url(m.text)
    if not url:
        await m.answer("Не похоже на ссылку. Пример: https://t.me/mychannel или @mychannel",
                       reply_markup=one_button("⬅️ Назад", "bc:back"))
        return
    d = await state.get_data()
    await state.update_data(bc_btns=d.get("bc_btns", []) + [(d["bc_bt"], url)])
    await bc_confirm(m, state)


@admin.message(Bc.btn_text)
@admin.message(Bc.btn_url)
async def bc_need_text(m: Message):
    await m.answer("Нужен текст сообщением.", reply_markup=one_button("⬅️ Назад", "bc:back"))


@admin.callback_query(F.data == "bc:no")
async def bc_no(cb: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await safe_edit(cb.message, "🛠 Админ-панель", admin_kb())
    await cb.answer()


@admin.callback_query(F.data.in_({"bc:go", "bc:go1"}), Bc.confirm)
async def bc_go(cb: CallbackQuery, state: FSMContext, bot: Bot):
    d = await state.get_data()
    await state.set_state(None)
    kbl = InlineKeyboardBuilder()
    n = 0
    for text, url in d.get("bc_btns", []):  # кнопки, добавленные именно к этой рассылке
        kbl.button(text=text, url=url)
        n += 1
    if cb.data == "bc:go1":  # плюс общие кнопки-ссылки из админки
        n += link_buttons(kbl)
    kbl.adjust(*([1] * n))
    markup = kbl.as_markup() if n else None
    ids = db.active_ids()
    status = await cb.message.edit_text(f"📤 Рассылка: 0/{len(ids)}")
    ok = fail = 0
    for i, uid in enumerate(ids, 1):
        if await safe_copy(bot, uid, d["bc_chat"], d["bc_msg"], markup):
            ok += 1
        else:
            fail += 1
        await asyncio.sleep(0.05)  # лимит Telegram ~30 сообщений/сек
        if i % 25 == 0:
            await safe_edit(status, f"📤 Рассылка: {i}/{len(ids)}")
    await safe_edit(status, f"✅ Рассылка завершена\nДоставлено: {ok}\nНе доставлено: {fail}", adm_back())
    await cb.answer()


# --- личное сообщение ---

@admin.callback_query(F.data == "adm:dm")
async def dm_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Direct.wait_id)
    await safe_edit(
        cb.message,
        "✉️ Отправь ID пользователя (его можно взять в списке пользователей).",
        adm_back(),
    )
    await cb.answer()


@admin.message(Direct.wait_id, F.text, ~F.text.startswith("/"))
async def dm_id(m: Message, state: FSMContext):
    if not m.text.strip().isdigit():
        await m.answer("ID — это число. Попробуй ещё раз.", reply_markup=adm_back())
        return
    uid = int(m.text.strip())
    u = db.get_user(uid)
    if not u:
        await m.answer("Такого пользователя нет в базе. Проверь ID.", reply_markup=adm_back())
        return
    await state.update_data(dm_to=uid)
    await state.set_state(Direct.wait_msg)
    await m.answer(f"Кому: {u['full_name']} ({uid}). Теперь отправь сообщение (любой тип).",
                   reply_markup=adm_back())


@admin.message(Direct.wait_msg, ~F.text.startswith("/"))
async def dm_send(m: Message, state: FSMContext, bot: Bot):
    d = await state.get_data()
    await state.set_state(None)
    ok = await safe_copy(bot, d["dm_to"], m.chat.id, m.message_id)
    await m.answer("✅ Отправлено" if ok else "❌ Не удалось отправить (пользователь заблокировал бота?)",
                   reply_markup=adm_back())


# --- кнопки-ссылки ---

MAX_LINKS = 8


def normalize_url(raw: str) -> str | None:
    u = raw.strip()
    if not u or " " in u or len(u) > 512:
        return None
    if u.startswith("@") and re.fullmatch(r"@[A-Za-z0-9_]{4,32}", u):
        return "https://t.me/" + u[1:]
    if re.match(r"(?i)^(https?://|tg://)\S+$", u):
        return u
    if re.match(r"(?i)^(t\.me/|www\.)\S+$", u) or re.fullmatch(r"(?i)[a-z0-9-]+(\.[a-z0-9-]+)+(/\S*)?", u):
        return "https://" + u
    return None


async def show_links(msg: Message):
    links = db.list_links()
    kb = InlineKeyboardBuilder()
    for lid, text, url in links:
        kb.button(text=f"🗑 {text}", callback_data=f"adm:ldel:{lid}")
    if len(links) < MAX_LINKS:
        kb.button(text="➕ Добавить", callback_data="adm:ladd")
    kb.button(text="⬅️ Назад", callback_data="adm:menu")
    kb.adjust(1)
    body = "\n".join(f"{i}. {text} → {url}" for i, (_, text, url) in enumerate(links, 1)) or "Пока нет ни одной."
    await safe_edit(
        msg,
        "🔗 Кнопки-ссылки\n\nОни показываются в приветствии и под сообщением «готово», "
        f"а при рассылке — по выбору.\n\n{body}\n\nНажми на кнопку, чтобы удалить её (максимум {MAX_LINKS}).",
        kb.as_markup(),
    )


@admin.callback_query(F.data == "adm:links")
async def adm_links(cb: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await show_links(cb.message)
    await cb.answer()


@admin.callback_query(F.data.startswith("adm:ldel:"))
async def adm_ldel(cb: CallbackQuery):
    db.del_link(int(cb.data.split(":")[2]))
    await show_links(cb.message)
    await cb.answer("Удалено")


@admin.callback_query(F.data == "adm:ladd")
async def adm_ladd(cb: CallbackQuery, state: FSMContext):
    if db.count_links() >= MAX_LINKS:
        await cb.answer(f"Максимум {MAX_LINKS} кнопок", show_alert=True)
        return
    await state.set_state(Link.text)
    await safe_edit(cb.message, "Напиши текст кнопки (до 64 символов), например: 📢 Наш канал",
                    one_button("⬅️ Назад", "adm:links"))
    await cb.answer()


@admin.message(Link.text, F.text, ~F.text.startswith("/"))
async def link_text(m: Message, state: FSMContext):
    text = m.text.strip()
    if not text or len(text) > 64:
        await m.answer("Текст должен быть от 1 до 64 символов.", reply_markup=one_button("⬅️ Назад", "adm:links"))
        return
    await state.update_data(link_text=text)
    await state.set_state(Link.url)
    await m.answer("Теперь отправь ссылку: https://… , t.me/… или @username",
                   reply_markup=one_button("⬅️ Назад", "adm:links"))


@admin.message(Link.url, F.text, ~F.text.startswith("/"))
async def link_url(m: Message, state: FSMContext):
    url = normalize_url(m.text)
    if not url:
        await m.answer("Не похоже на ссылку. Пример: https://t.me/mychannel или @mychannel",
                       reply_markup=one_button("⬅️ Назад", "adm:links"))
        return
    d = await state.get_data()
    await state.set_state(None)
    db.add_link(d["link_text"], url)
    await m.answer(f"✅ Кнопка добавлена: {d['link_text']} → {url}",
                   reply_markup=one_button("🔗 К списку кнопок", "adm:links"))


@admin.message(Link.text)
@admin.message(Link.url)
async def link_need_text(m: Message):
    await m.answer("Нужен текст сообщением.", reply_markup=one_button("⬅️ Назад", "adm:links"))


# --- обязательная подписка ---

MAX_CHANNELS = 5


async def show_subs(msg: Message):
    chans = db.list_channels()
    kb = InlineKeyboardBuilder()
    for cid, _, title, _ in chans:
        kb.button(text=f"🗑 {title}", callback_data=f"adm:sdel:{cid}")
    if len(chans) < MAX_CHANNELS:
        kb.button(text="➕ Добавить канал", callback_data="adm:sadd")
    kb.button(text="⬅️ Назад", callback_data="adm:menu")
    kb.adjust(1)
    body = "\n".join(f"{i}. {title} ({chat})" for i, (_, chat, title, _) in enumerate(chans, 1)) or "Пока нет каналов — подписка не требуется."
    await safe_edit(
        msg,
        "📌 Обязательная подписка\n\nПользователи не смогут пользоваться ботом, пока не подпишутся на все "
        "каналы из списка. После подписки они нажимают «Я подписался» и бот продолжает работать как обычно.\n\n"
        f"{body}\n\nБот должен быть администратором канала — иначе он не сможет проверять подписку. "
        "Нажми на кнопку, чтобы удалить канал.",
        kb.as_markup(),
    )


@admin.callback_query(F.data == "adm:subs")
async def adm_subs(cb: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await show_subs(cb.message)
    await cb.answer()


@admin.callback_query(F.data.startswith("adm:sdel:"))
async def adm_sdel(cb: CallbackQuery):
    db.del_channel(int(cb.data.split(":")[2]))
    _sub_ok.clear()
    await show_subs(cb.message)
    await cb.answer("Удалено")


@admin.callback_query(F.data == "adm:sadd")
async def adm_sadd(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Sub.chat)
    await safe_edit(
        cb.message,
        "Отправь @username канала (например @mychannel) или его числовой ID (-100…).\n"
        "Сначала добавь бота в канал администратором.",
        one_button("⬅️ Назад", "adm:subs"),
    )
    await cb.answer()


@admin.message(Sub.chat, F.text, ~F.text.startswith("/"))
async def sub_chat(m: Message, state: FSMContext, bot: Bot):
    raw = m.text.strip()
    raw = re.sub(r"(?i)^(https?://)?t\.me/", "@", raw) if re.match(r"(?i)^(https?://)?t\.me/[A-Za-z0-9_]{4,}$", raw) else raw
    if not (re.fullmatch(r"@[A-Za-z0-9_]{4,32}", raw) or re.fullmatch(r"-?\d{5,}", raw)):
        await m.answer("Нужен @username или числовой ID канала.", reply_markup=one_button("⬅️ Назад", "adm:subs"))
        return
    back = one_button("⬅️ Назад", "adm:subs")
    try:
        chat = await bot.get_chat(_chat_key(raw))
        me = await bot.get_chat_member(chat.id, bot.id)
    except Exception as e:
        await m.answer(f"❌ Не удалось найти канал или бот там не состоит: {str(e)[-200:]}", reply_markup=back)
        return
    if getattr(me.status, "value", me.status) not in ("administrator", "creator"):
        await m.answer("❌ Бот не администратор этого канала. Сделай его админом и отправь канал снова.",
                       reply_markup=back)
        return
    url = f"https://t.me/{chat.username}" if getattr(chat, "username", None) else None
    if not url:
        try:
            url = await bot.export_chat_invite_link(chat.id)
        except Exception:
            await m.answer("❌ У канала нет @username, а создать пригласительную ссылку не получилось "
                           "(дай боту право «Приглашать пользователей»).", reply_markup=back)
            return
    db.add_channel(str(chat.id), chat.title or raw, url)
    await state.set_state(None)
    await m.answer(f"✅ Канал добавлен: {chat.title or raw}. Теперь подписка на него обязательна.",
                   reply_markup=one_button("📌 К списку каналов", "adm:subs"))


@admin.message(Sub.chat)
async def sub_need_text(m: Message):
    await m.answer("Нужен текст: @username или ID канала.", reply_markup=one_button("⬅️ Назад", "adm:subs"))


async def cleanup_loop():
    """Чистит брошенные временные папки (старше 1 часа)."""
    while True:
        now = time.time()
        for p in WORK_DIR.iterdir():
            try:
                if now - p.stat().st_mtime > 3600:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
        await asyncio.sleep(600)


async def main():
    shutil.rmtree(WORK_DIR, ignore_errors=True)  # остатки после прошлого запуска
    WORK_DIR.mkdir(exist_ok=True)
    asyncio.create_task(cleanup_loop())
    # таймаут по умолчанию (60 с) слишком мал для отправки видео
    bot = Bot(BOT_TOKEN, session=AiohttpSession(timeout=900))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(TrackUsers())
    dp.callback_query.outer_middleware(TrackUsers())
    dp.message.outer_middleware(SubGate())
    dp.callback_query.outer_middleware(SubGate())
    dp.include_routers(common, admin, router)
    await bot.delete_webhook(drop_pending_updates=True)
    if FFMPEG:
        log.info("ffmpeg: %s", FFMPEG)
    else:
        log.error("ffmpeg НЕ НАЙДЕН! Выполни: pip install imageio-ffmpeg (или установи ffmpeg)")
    if CHANNEL_ID:
        log.info("Копии треков и обложек идут в канал %s (бот должен быть админом канала)", CHANNEL_ID)
    log.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
