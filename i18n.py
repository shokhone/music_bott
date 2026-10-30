"""Тексты бота на трёх языках: узбекский (uz), русский (ru), английский (en)."""

LANGS = {"uz": "🇺🇿 O'zbekcha", "ru": "🇷🇺 Русский", "en": "🇬🇧 English"}
CHOOSE = "🌐 Tilni tanlang / Выберите язык / Choose a language"

# языки, у которых по умолчанию ставим русский (если Telegram сообщает такой language_code)
_RU_LIKE = ("ru", "uk", "be", "kk", "ky", "tg", "hy", "az", "ka", "mo")


def detect(code: str | None) -> str:
    c = (code or "").lower()
    if c.startswith("uz"):
        return "uz"
    if c.startswith(_RU_LIKE):
        return "ru"
    return "en"


TEXT = {
    # ───────────────────────────── Русский ─────────────────────────────
    "ru": {
        "start": (
            "👋 Привет! Я редактор музыки.\n\n"
            "Отправь мне аудио-файл (mp3, m4a, flac, ogg…) — и я смогу:\n"
            "• изменить название, исполнителя и описание\n"
            "• поставить свою обложку\n"
            "• наложить эффект: 8D, концертный зал, бас-буст, slowed+reverb, nightcore, lo-fi и другие\n"
            "• выбрать формат файла (MP3, M4A, MP4, OGG, FLAC, WAV, голосовое, кружок) и формат имени\n\n"
            "🎞 Пришли видео — конвертирую в MP4/MKV/WEBM/AVI/MOV/GIF, сделаю кружок "
            "или вытащу музыку в редактор.\n\n"
            "🌐 Язык: /lang"
        ),
        "channel_notice": "ℹ️ Готовые треки и присланные обложки копируются в канал бота.",
        "lang_set": "✅ Язык: Русский",
        "none": "нет", "yes": "есть",
        "menu_head": "🎵 Редактор трека",
        "l_title": "Название", "l_artist": "Исполнитель", "l_desc": "Описание", "l_cover": "Обложка",
        "l_fx": "Эффект", "l_ext": "Формат файла", "l_fmt": "Формат имени файла",
        "menu_choose": "Выбери, что изменить:",
        "b_title": "✏️ Название", "b_artist": "👤 Исполнитель", "b_desc": "📝 Описание",
        "b_cover": "🖼 Обложка", "b_fx": "🎛 Эффекты", "b_ext": "Формат файла",
        "b_fmt": "🔤 Формат имени", "b_run": "✅ Готово — получить трек",
        "b_back": "⬅️ Назад", "b_again": "🔁 Изменить ещё раз", "b_nofx": "🚫 Без эффекта",
        "b_vid_again": "🔁 Конвертировать ещё раз",
        "p_title": "Отправь новое название трека.",
        "p_artist": "Отправь имя исполнителя.",
        "p_desc": "Отправь текст описания (до 1000 символов).",
        "p_cover": "Отправь картинку для обложки (фото).",
        "fx_title": "🎛 Выбери эффект:",
        "ext_title": (
            "🎚 Выбери формат результата.\n"
            "MP4 — видео: обложка (или чёрный фон) + звук.\n"
            "Кружок — круглое видео до 60 секунд, обложка крутится."
        ),
        "fx_set": "Эффект выбран", "fx_unset": "Эффект убран", "fmt_set": "Формат выбран",
        "too_big_audio": "Файл больше 20 МБ — Telegram не даёт ботам скачивать такие файлы.",
        "too_big_video": "Видео больше 20 МБ — Telegram не даёт ботам скачивать такие файлы.",
        "send_first": "Сначала отправь аудио-файл",
        "send_video_first": "Сначала отправь видео",
        "expired": "Файл уже удалён (хранится около часа). Отправь его заново.",
        "busy": "⏳ Уже обрабатываю — подожди немного",
        "processing": "⏳ Обрабатываю трек, подожди немного…",
        "processing_video": "⏳ Обрабатываю видео…",
        "done_again": "✅ Готово! Можно изменить этот трек ещё раз или отправить новый файл.",
        "done_video_again": "✅ Готово! Можно сделать ещё одну конвертацию этого видео или отправить новый файл.",
        "err_proc": "❌ Ошибка обработки:\n{e}",
        "cover_err": "Не получилось обработать картинку:\n{e}",
        "need_text": "Нужен текст.",
        "need_photo": "Нужна картинка (фото).",
        "fallback": "Отправь аудио-файл или видео 🎧",
        "cancelled": "Отменено. Отправь аудио-файл, чтобы начать.",
        "vid_q": "🎞 Что сделать с видео?",
        "vid_music": "🎧 Музыка из видео (MP3 + редактор)",
        "vid_circle": "⭕ Кружок",
        "too_big_result": "Результат больше 50 МБ — Telegram не принимает такие файлы от бота. Попробуй видео покороче.",
        "note_trim": "ℹ️ В кружок вошли первые 60 секунд.",
    },
    # ───────────────────────────── English ─────────────────────────────
    "en": {
        "start": (
            "👋 Hi! I'm a music editor bot.\n\n"
            "Send me an audio file (mp3, m4a, flac, ogg…) and I can:\n"
            "• change the title, artist and description\n"
            "• set your own cover art\n"
            "• add an effect: 8D, concert hall, bass boost, slowed+reverb, nightcore, lo-fi and more\n"
            "• choose the file format (MP3, M4A, MP4, OGG, FLAC, WAV, voice, video note) and the file name format\n\n"
            "🎞 Send a video — I'll convert it to MP4/MKV/WEBM/AVI/MOV/GIF, make a round video note "
            "or extract the music into the editor.\n\n"
            "🌐 Language: /lang"
        ),
        "channel_notice": "ℹ️ Finished tracks and the cover pictures you send are copied to the bot's channel.",
        "lang_set": "✅ Language: English",
        "none": "none", "yes": "yes",
        "menu_head": "🎵 Track editor",
        "l_title": "Title", "l_artist": "Artist", "l_desc": "Description", "l_cover": "Cover",
        "l_fx": "Effect", "l_ext": "File format", "l_fmt": "File name format",
        "menu_choose": "Choose what to change:",
        "b_title": "✏️ Title", "b_artist": "👤 Artist", "b_desc": "📝 Description",
        "b_cover": "🖼 Cover", "b_fx": "🎛 Effects", "b_ext": "File format",
        "b_fmt": "🔤 Name format", "b_run": "✅ Done — get the track",
        "b_back": "⬅️ Back", "b_again": "🔁 Edit again", "b_nofx": "🚫 No effect",
        "b_vid_again": "🔁 Convert again",
        "p_title": "Send the new track title.",
        "p_artist": "Send the artist name.",
        "p_desc": "Send the description text (up to 1000 characters).",
        "p_cover": "Send a picture for the cover (photo).",
        "fx_title": "🎛 Choose an effect:",
        "ext_title": (
            "🎚 Choose the output format.\n"
            "MP4 — video: cover (or black background) + audio.\n"
            "Video note — round video up to 60 seconds, the cover spins."
        ),
        "fx_set": "Effect selected", "fx_unset": "Effect removed", "fmt_set": "Format selected",
        "too_big_audio": "The file is larger than 20 MB — Telegram doesn't let bots download such files.",
        "too_big_video": "The video is larger than 20 MB — Telegram doesn't let bots download such files.",
        "send_first": "Send an audio file first",
        "send_video_first": "Send a video first",
        "expired": "The file has been deleted (it is kept for about an hour). Please send it again.",
        "busy": "⏳ Already processing — please wait",
        "processing": "⏳ Processing your track, please wait…",
        "processing_video": "⏳ Processing the video…",
        "done_again": "✅ Done! You can edit this track again or send a new file.",
        "done_video_again": "✅ Done! You can convert this video again or send a new file.",
        "err_proc": "❌ Processing error:\n{e}",
        "cover_err": "Couldn't process the picture:\n{e}",
        "need_text": "Text is required.",
        "need_photo": "A picture (photo) is required.",
        "fallback": "Send an audio file or a video 🎧",
        "cancelled": "Cancelled. Send an audio file to start.",
        "vid_q": "🎞 What would you like to do with the video?",
        "vid_music": "🎧 Music from video (MP3 + editor)",
        "vid_circle": "⭕ Video note",
        "too_big_result": "The result is larger than 50 MB — Telegram doesn't accept such files from a bot. Try a shorter video.",
        "note_trim": "ℹ️ Only the first 60 seconds fit into the video note.",
    },
    # ───────────────────────────── O'zbekcha ─────────────────────────────
    "uz": {
        "start": (
            "👋 Salom! Men musiqa muharriri botman.\n\n"
            "Menga audio fayl yuboring (mp3, m4a, flac, ogg…) — men quyidagilarni qila olaman:\n"
            "• nom, ijrochi va tavsifni o'zgartirish\n"
            "• o'zingizning muqovangizni qo'yish\n"
            "• effekt qo'shish: 8D, konsert zali, bass-boost, slowed+reverb, nightcore, lo-fi va boshqalar\n"
            "• fayl formatini (MP3, M4A, MP4, OGG, FLAC, WAV, ovozli xabar, dumaloq video) "
            "va fayl nomi formatini tanlash\n\n"
            "🎞 Video yuboring — uni MP4/MKV/WEBM/AVI/MOV/GIF ga o'tkazaman, dumaloq video yasayman "
            "yoki musiqasini muharrirga ajratib beraman.\n\n"
            "🌐 Til: /lang"
        ),
        "channel_notice": "ℹ️ Tayyor treklar va siz yuborgan muqova rasmlari botning kanaliga nusxalanadi.",
        "lang_set": "✅ Til: O'zbekcha",
        "none": "yo'q", "yes": "bor",
        "menu_head": "🎵 Trek muharriri",
        "l_title": "Nomi", "l_artist": "Ijrochi", "l_desc": "Tavsif", "l_cover": "Muqova",
        "l_fx": "Effekt", "l_ext": "Fayl formati", "l_fmt": "Fayl nomi formati",
        "menu_choose": "Nimani o'zgartirishni tanlang:",
        "b_title": "✏️ Nomi", "b_artist": "👤 Ijrochi", "b_desc": "📝 Tavsif",
        "b_cover": "🖼 Muqova", "b_fx": "🎛 Effektlar", "b_ext": "Fayl formati",
        "b_fmt": "🔤 Nom formati", "b_run": "✅ Tayyor — trekni olish",
        "b_back": "⬅️ Orqaga", "b_again": "🔁 Yana o'zgartirish", "b_nofx": "🚫 Effektsiz",
        "b_vid_again": "🔁 Yana o'tkazish",
        "p_title": "Trekning yangi nomini yuboring.",
        "p_artist": "Ijrochi nomini yuboring.",
        "p_desc": "Tavsif matnini yuboring (1000 belgigacha).",
        "p_cover": "Muqova uchun rasm yuboring (foto).",
        "fx_title": "🎛 Effektni tanlang:",
        "ext_title": (
            "🎚 Natija formatini tanlang.\n"
            "MP4 — video: muqova (yoki qora fon) + ovoz.\n"
            "Dumaloq video — 60 soniyagacha, muqova aylanadi."
        ),
        "fx_set": "Effekt tanlandi", "fx_unset": "Effekt olib tashlandi", "fmt_set": "Format tanlandi",
        "too_big_audio": "Fayl 20 MB dan katta — Telegram botlarga bunday fayllarni yuklab olishga ruxsat bermaydi.",
        "too_big_video": "Video 20 MB dan katta — Telegram botlarga bunday fayllarni yuklab olishga ruxsat bermaydi.",
        "send_first": "Avval audio fayl yuboring",
        "send_video_first": "Avval video yuboring",
        "expired": "Fayl o'chirib tashlangan (taxminan bir soat saqlanadi). Uni qaytadan yuboring.",
        "busy": "⏳ Allaqachon ishlayapman — biroz kuting",
        "processing": "⏳ Trek qayta ishlanmoqda, biroz kuting…",
        "processing_video": "⏳ Video qayta ishlanmoqda…",
        "done_again": "✅ Tayyor! Bu trekni yana o'zgartirishingiz yoki yangi fayl yuborishingiz mumkin.",
        "done_video_again": "✅ Tayyor! Bu videoni yana o'tkazishingiz yoki yangi fayl yuborishingiz mumkin.",
        "err_proc": "❌ Qayta ishlashda xatolik:\n{e}",
        "cover_err": "Rasmni qayta ishlab bo'lmadi:\n{e}",
        "need_text": "Matn kerak.",
        "need_photo": "Rasm (foto) kerak.",
        "fallback": "Audio fayl yoki video yuboring 🎧",
        "cancelled": "Bekor qilindi. Boshlash uchun audio fayl yuboring.",
        "vid_q": "🎞 Videoni nima qilamiz?",
        "vid_music": "🎧 Videodan musiqa (MP3 + muharrir)",
        "vid_circle": "⭕ Dumaloq video",
        "too_big_result": "Natija 50 MB dan katta — Telegram botdan bunday fayllarni qabul qilmaydi. Qisqaroq video sinab ko'ring.",
        "note_trim": "ℹ️ Dumaloq videoga dastlabki 60 soniya sig'di.",
    },
}

# названия эффектов (ключи совпадают с effects.EFFECTS)
FX = {
    "ru": {"8d": "🎧 8D", "concert": "🎤 Концертный зал", "hall": "🏛 Большой зал", "bass": "🔊 Бас-буст",
           "slowed": "🌙 Slowed + Reverb", "nightcore": "⚡ Nightcore", "lofi": "📻 Lo-Fi",
           "underwater": "🌊 Под водой", "phone": "📞 Телефон", "cave": "🕳 Пещера",
           "wide": "🌌 Широкое стерео", "chorus": "🎼 Хорус"},
    "en": {"8d": "🎧 8D", "concert": "🎤 Concert hall", "hall": "🏛 Big hall", "bass": "🔊 Bass boost",
           "slowed": "🌙 Slowed + Reverb", "nightcore": "⚡ Nightcore", "lofi": "📻 Lo-Fi",
           "underwater": "🌊 Underwater", "phone": "📞 Phone", "cave": "🕳 Cave",
           "wide": "🌌 Wide stereo", "chorus": "🎼 Chorus"},
    "uz": {"8d": "🎧 8D", "concert": "🎤 Konsert zali", "hall": "🏛 Katta zal", "bass": "🔊 Bass-boost",
           "slowed": "🌙 Slowed + Reverb", "nightcore": "⚡ Nightcore", "lofi": "📻 Lo-Fi",
           "underwater": "🌊 Suv ostida", "phone": "📞 Telefon", "cave": "🕳 G'or",
           "wide": "🌌 Keng stereo", "chorus": "🎼 Xor"},
}

# названия форматов файла (ключи совпадают с effects.FORMATS)
FMT = {
    "ru": {"mp3": "🎵 MP3", "m4a": "🍏 M4A (AAC)", "mp4": "🎬 MP4 (видео с обложкой)", "ogg": "🌀 OGG",
           "flac": "💎 FLAC", "wav": "📼 WAV", "voice": "🎙 Голосовое сообщение",
           "circle": "⭕ Кружок (до 60 с)"},
    "en": {"mp3": "🎵 MP3", "m4a": "🍏 M4A (AAC)", "mp4": "🎬 MP4 (video with cover)", "ogg": "🌀 OGG",
           "flac": "💎 FLAC", "wav": "📼 WAV", "voice": "🎙 Voice message",
           "circle": "⭕ Video note (up to 60 s)"},
    "uz": {"mp3": "🎵 MP3", "m4a": "🍏 M4A (AAC)", "mp4": "🎬 MP4 (muqovali video)", "ogg": "🌀 OGG",
           "flac": "💎 FLAC", "wav": "📼 WAV", "voice": "🎙 Ovozli xabar",
           "circle": "⭕ Dumaloq video (60 s gacha)"},
}


def t(lang: str, key: str, **kw) -> str:
    s = TEXT.get(lang, TEXT["ru"]).get(key) or TEXT["ru"][key]
    return s.format(**kw) if kw else s


def fx_name(lang: str, key: str) -> str:
    return FX.get(lang, FX["ru"])[key]


def fmt_name(lang: str, key: str) -> str:
    return FMT.get(lang, FMT["ru"])[key]


# ── flanger, bit crush ──
FX["ru"].update({"flanger": "🌀 Flanger", "bitcrush": "👾 Bit crush"})
FX["en"].update({"flanger": "🌀 Flanger", "bitcrush": "👾 Bit crush"})
FX["uz"].update({"flanger": "🌀 Flanger", "bitcrush": "👾 Bit crush"})

# ── обязательная подписка ──
TEXT["ru"].update({
    "sub_need": "📌 Чтобы пользоваться ботом, подпишись на канал(ы) ниже, затем нажми «Я подписался».",
    "b_sub_check": "✅ Я подписался",
    "sub_not_yet": "Подписка не найдена. Подпишись на все каналы и нажми снова.",
    "sub_ok": "Спасибо! Подписка подтверждена ✅",
})
TEXT["en"].update({
    "sub_need": "📌 To use the bot, subscribe to the channel(s) below, then tap “I subscribed”.",
    "b_sub_check": "✅ I subscribed",
    "sub_not_yet": "Subscription not found. Subscribe to all channels and tap again.",
    "sub_ok": "Thanks! Subscription confirmed ✅",
})
TEXT["uz"].update({
    "sub_need": "📌 Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo'ling, so'ng «Obuna bo'ldim» tugmasini bosing.",
    "b_sub_check": "✅ Obuna bo'ldim",
    "sub_not_yet": "Obuna topilmadi. Barcha kanallarga obuna bo'ling va qayta bosing.",
    "sub_ok": "Rahmat! Obuna tasdiqlandi ✅",
})
