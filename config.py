import os
import re
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Канал, куда бот копирует готовые треки и присланные обложки (пусто = выключено).
# Укажи ID вида -1001234567890 или @username канала; бот должен быть админом канала.
_ch = os.getenv("CHANNEL_ID", "").strip()
CHANNEL_ID = (int(_ch) if re.fullmatch(r"-?\d+", _ch) else _ch) if _ch else None

# Временные файлы лежат в системной temp-папке, а не в папке проекта
WORK_DIR = Path(tempfile.gettempdir()) / "musicbot_tmp"
WORK_DIR.mkdir(exist_ok=True)

if not BOT_TOKEN or not ADMIN_ID:
    raise SystemExit("Заполни BOT_TOKEN и ADMIN_ID в файле .env")
