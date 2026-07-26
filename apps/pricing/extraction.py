"""Deterministic text extraction: model, storage, item type, defects.

Pure functions over normalized text; no ORM and no network.
"""

import re
import unicodedata

from apps.pricing.constants import MODEL_REGISTRY

_WORD_CHAR = "0-9a-zа-яёіїєґ"
_BOUNDARY_BEFORE = rf"(?<![{_WORD_CHAR}])"
_BOUNDARY_AFTER = rf"(?![{_WORD_CHAR}])"

_DASHES = re.compile(r"[‐‑‒–—―−-]")
_SPACES = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = text.replace("ё", "е")
    text = _DASHES.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    return text


def _alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias).replace(r"\ ", r"\s+")
    return re.compile(_BOUNDARY_BEFORE + escaped + _BOUNDARY_AFTER)


# Prebuilt alias patterns sorted by alias length (longest first).
_ALIAS_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = sorted(
    (
        (model_key, alias, _alias_pattern(alias))
        for model_key, meta in MODEL_REGISTRY.items()
        for alias in meta["aliases"]
    ),
    key=lambda item: len(item[1]),
    reverse=True,
)


def extract_model(text: str) -> tuple[str | None, bool]:
    """Return (model_key, ambiguous). Longest alias wins; overlaps resolved."""
    normalized = normalize_text(text)
    if not normalized:
        return None, False
    taken_spans: list[tuple[int, int]] = []
    found_keys: set[str] = set()
    for model_key, _alias, pattern in _ALIAS_PATTERNS:
        for match in pattern.finditer(normalized):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in taken_spans):
                continue  # overlapped by a longer alias already matched
            taken_spans.append(span)
            found_keys.add(model_key)
    if not found_keys:
        return None, False
    if len(found_keys) > 1:
        return None, True
    return found_keys.pop(), False


_TB_PATTERN = re.compile(_BOUNDARY_BEFORE + r"1\s*(tb|тб)" + _BOUNDARY_AFTER)
_GB_PATTERN = re.compile(
    _BOUNDARY_BEFORE + r"(1024|512|256|128|64)\s*(gb|гб|g|гиг|гигов|ґб)" + _BOUNDARY_AFTER
)


def extract_storage(text: str) -> int | None:
    normalized = normalize_text(text)
    if not normalized:
        return None
    values: set[int] = set()
    if _TB_PATTERN.search(normalized):
        values.add(1024)
    for match in _GB_PATTERN.finditer(normalized):
        values.add(int(match.group(1)))
    if len(values) == 1:
        return values.pop()
    return None  # zero or conflicting values -> unknown


def _keyword_regex(words: tuple[str, ...]) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(word).replace(r"\ ", r"\s+") for word in words)
    return re.compile(_BOUNDARY_BEFORE + f"(?:{alternatives})" + _BOUNDARY_AFTER)


_COPY_RE = _keyword_regex(
    ("копия", "копія", "реплика", "репліка", "replica", "fake", "подделка", "підробка", "клон")
)
_DUMMY_RE = _keyword_regex(("муляж", "макет", "dummy", "mockup", "мокап"))
_ACCESSORY_RE = _keyword_regex(
    (
        "чехол",
        "чохол",
        "кейс",
        "case",
        "бампер",
        "накладка",
        "захисне скло",
        "защитное стекло",
        "зарядка для",
        "кабель",
        "airpods",
        "наушники",
        "навушники",
        "ремешок",
        "ремінець",
    )
)
_PARTS_RE = _keyword_regex(
    (
        "запчастини",
        "запчасти",
        "на запчастини",
        "на запчасти",
        "разбор",
        "розбор",
        "розбірка",
        "по частям",
        "parts",
    )
)
_DONOR_RE = _keyword_regex(("донор",))
_MOTHERBOARD_RE = _keyword_regex(("плата", "материнська плата", "материнская плата", "motherboard"))
_ICLOUD_RE = _keyword_regex(("icloud", "айклауд"))
_LOCK_RE = _keyword_regex(
    ("заблокирован", "заблокований", "заблоковано", "залочен", "лочен", "lock", "locked")
)
_MDM_RE = _keyword_regex(("mdm",))

_BATTERY_RE = re.compile(
    _BOUNDARY_BEFORE
    + r"(?:акб|аккумулятор|акумулятор|батарея|battery|емкость|ємність)\D{0,20}?(\d{2,3})\s*%?"
)

_DEFECT_PATTERNS: dict[str, re.Pattern[str]] = {
    "FRONT_GLASS_CRACK": _keyword_regex(
        (
            "трещина на экране",
            "тріщина на екрані",
            "треснут экран",
            "тріснутий екран",
            "разбит экран",
            "розбитий екран",
            "трещина стекла",
            "тріщина скла",
            "cracked screen",
            "трещина на стекле",
            "битий екран",
        )
    ),
    "BACK_GLASS_CRACK": _keyword_regex(
        (
            "трещина сзади",
            "тріщина ззаду",
            "разбита задняя крышка",
            "розбита задня кришка",
            "трещина задней крышки",
            "тріщина задньої кришки",
            "back glass crack",
        )
    ),
    "DISPLAY_REPLACED": _keyword_regex(
        (
            "дисплей менялся",
            "дисплей заменен",
            "дисплей замінений",
            "менялся экран",
            "замена дисплея",
            "заміна дисплея",
            "экран менялся",
            "екран мінявся",
            "не родной дисплей",
            "не рідний дисплей",
            "копия дисплей",
        )
    ),
    "FACE_ID_BROKEN": _keyword_regex(
        (
            "face id не работает",
            "face id не працює",
            "не работает face id",
            "не працює face id",
            "faceid не работает",
            "без face id",
        )
    ),
    "TRUE_TONE_MISSING": _keyword_regex(
        (
            "true tone не работает",
            "true tone не працює",
            "без true tone",
            "нет true tone",
            "немає true tone",
        )
    ),
    "CAMERA_DEFECT": _keyword_regex(
        (
            "камера не работает",
            "камера не працює",
            "не работает камера",
            "не працює камера",
            "дефект камеры",
            "дефект камери",
            "пятно на камере",
            "пляма на камері",
        )
    ),
    "CHARGING_PORT_DEFECT": _keyword_regex(
        (
            "не заряжается",
            "не заряджається",
            "разъем зарядки",
            "роз'єм зарядки",
            "порт зарядки",
        )
    ),
    "SPEAKER_MIC_DEFECT": _keyword_regex(
        (
            "динамик не работает",
            "динамік не працює",
            "не работает динамик",
            "не працює динамік",
            "микрофон не работает",
            "мікрофон не працює",
            "хрипит динамик",
        )
    ),
    "BUTTON_DEFECT": _keyword_regex(
        (
            "кнопка не работает",
            "кнопка не працює",
            "не работает кнопка",
            "не працює кнопка",
            "залипает кнопка",
        )
    ),
    "FRAME_DAMAGE": _keyword_regex(
        (
            "вмятина",
            "вм'ятина",
            "погнут корпус",
            "погнутий корпус",
            "деформация корпуса",
            "деформація корпусу",
            "сильные сколы",
        )
    ),
    "WATER_DAMAGE": _keyword_regex(
        (
            "попадала вода",
            "потрапляла вода",
            "после воды",
            "після води",
            "утопленник",
            "втоплений",
            "контакт с водой",
            "контакт з водою",
        )
    ),
    "UNKNOWN_REPAIR_HISTORY": _keyword_regex(
        (
            "ремонтировался",
            "ремонтувався",
            "был в ремонте",
            "був у ремонті",
            "после ремонта",
            "після ремонту",
        )
    ),
    "ESIM_ONLY": _keyword_regex(("esim only", "только esim", "тільки esim", "esim версия")),
}


def extract_battery_percent(text: str) -> int | None:
    normalized = normalize_text(text)
    match = _BATTERY_RE.search(normalized)
    if not match:
        return None
    value = int(match.group(1))
    if 40 <= value <= 100:
        return value
    return None


def battery_defect_code(percent: int | None) -> str | None:
    if percent is None:
        return None
    if percent < 80:
        return "BATTERY_LT_80"
    if percent <= 84:
        return "BATTERY_80_84"
    if percent <= 89:
        return "BATTERY_85_89"
    return None


def detect_defects(text: str) -> tuple[str, ...]:
    normalized = normalize_text(text)
    if not normalized:
        return ()
    found = [code for code, pattern in _DEFECT_PATTERNS.items() if pattern.search(normalized)]
    battery_code = battery_defect_code(extract_battery_percent(text))
    if battery_code:
        found.append(battery_code)
    return tuple(sorted(set(found)))


def classify_item_type(text: str) -> tuple[str, tuple[str, ...]]:
    """Return (item_type, hard_stop_codes) from normalized text."""
    normalized = normalize_text(text)
    codes: list[str] = []
    item_type = "PHONE"
    if _COPY_RE.search(normalized):
        item_type = "COPY"
        codes.append("ITEM_COPY")
    if _DUMMY_RE.search(normalized):
        item_type = "COPY"
        codes.append("ITEM_DUMMY")
    if _PARTS_RE.search(normalized):
        item_type = "PARTS"
        codes.append("ITEM_PARTS")
    if _DONOR_RE.search(normalized):
        item_type = "PARTS"
        codes.append("ITEM_DONOR")
    if _MOTHERBOARD_RE.search(normalized):
        item_type = "PARTS"
        codes.append("MOTHERBOARD_ONLY")
    accessory_match = _ACCESSORY_RE.search(normalized)
    if accessory_match:
        # An accessory keyword marks the whole item as accessory only when it
        # dominates the title (e.g. "Чехол для iPhone 13"): keyword within the
        # first 30 characters.
        if normalized.find(accessory_match.group(0)) <= 30:
            item_type = "ACCESSORY"
            codes.append("ITEM_ACCESSORY")
    return item_type, tuple(codes)


def detect_lock_flags(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (hard_stop_codes, manual_codes) for iCloud/MDM mentions."""
    normalized = normalize_text(text)
    hard: list[str] = []
    manual: list[str] = []
    if _ICLOUD_RE.search(normalized) and _LOCK_RE.search(normalized):
        hard.append("ICLOUD_LOCK")
    if _MDM_RE.search(normalized):
        manual.append("LOCK_STATUS_UNKNOWN")
    return tuple(hard), tuple(manual)
