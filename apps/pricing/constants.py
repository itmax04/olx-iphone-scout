"""Canonical registries: iPhone models, storage, defect codes, reason codes.

This module is the single source of truth. Forms, serializers, the parser and
tests must import from here; free-form strings are forbidden.
"""

from types import MappingProxyType

ALLOWED_STORAGE_GB = (64, 128, 256, 512, 1024)

# model_key -> (UI label, allowed storage, aliases after normalization)
MODEL_REGISTRY: MappingProxyType[str, dict] = MappingProxyType(
    {
        "iphone_11": {
            "label": "iPhone 11",
            "storage": (64, 128, 256),
            "aliases": ("iphone 11", "айфон 11", "айфон11"),
        },
        "iphone_11_pro": {
            "label": "iPhone 11 Pro",
            "storage": (64, 256, 512),
            "aliases": ("iphone 11 pro", "айфон 11 про"),
        },
        "iphone_11_pro_max": {
            "label": "iPhone 11 Pro Max",
            "storage": (64, 256, 512),
            "aliases": ("iphone 11 pro max", "айфон 11 про макс"),
        },
        "iphone_12_mini": {
            "label": "iPhone 12 mini",
            "storage": (64, 128, 256),
            "aliases": ("iphone 12 mini", "айфон 12 мини", "айфон 12 міні"),
        },
        "iphone_12": {
            "label": "iPhone 12",
            "storage": (64, 128, 256),
            "aliases": ("iphone 12", "айфон 12", "айфон12"),
        },
        "iphone_12_pro": {
            "label": "iPhone 12 Pro",
            "storage": (128, 256, 512),
            "aliases": ("iphone 12 pro", "айфон 12 про"),
        },
        "iphone_12_pro_max": {
            "label": "iPhone 12 Pro Max",
            "storage": (128, 256, 512),
            "aliases": ("iphone 12 pro max", "айфон 12 про макс"),
        },
        "iphone_13_mini": {
            "label": "iPhone 13 mini",
            "storage": (128, 256, 512),
            "aliases": ("iphone 13 mini", "айфон 13 мини", "айфон 13 міні"),
        },
        "iphone_13": {
            "label": "iPhone 13",
            "storage": (128, 256, 512),
            "aliases": ("iphone 13", "айфон 13", "айфон13"),
        },
        "iphone_13_pro": {
            "label": "iPhone 13 Pro",
            "storage": (128, 256, 512, 1024),
            "aliases": ("iphone 13 pro", "айфон 13 про"),
        },
        "iphone_13_pro_max": {
            "label": "iPhone 13 Pro Max",
            "storage": (128, 256, 512, 1024),
            "aliases": ("iphone 13 pro max", "айфон 13 про макс"),
        },
        "iphone_14": {
            "label": "iPhone 14",
            "storage": (128, 256, 512),
            "aliases": ("iphone 14", "айфон 14", "айфон14"),
        },
        "iphone_14_plus": {
            "label": "iPhone 14 Plus",
            "storage": (128, 256, 512),
            "aliases": ("iphone 14 plus", "айфон 14 плюс"),
        },
        "iphone_14_pro": {
            "label": "iPhone 14 Pro",
            "storage": (128, 256, 512, 1024),
            "aliases": ("iphone 14 pro", "айфон 14 про"),
        },
        "iphone_14_pro_max": {
            "label": "iPhone 14 Pro Max",
            "storage": (128, 256, 512, 1024),
            "aliases": ("iphone 14 pro max", "айфон 14 про макс"),
        },
        "iphone_15": {
            "label": "iPhone 15",
            "storage": (128, 256, 512),
            "aliases": ("iphone 15", "айфон 15", "айфон15"),
        },
        "iphone_15_plus": {
            "label": "iPhone 15 Plus",
            "storage": (128, 256, 512),
            "aliases": ("iphone 15 plus", "айфон 15 плюс"),
        },
        "iphone_15_pro": {
            "label": "iPhone 15 Pro",
            "storage": (128, 256, 512, 1024),
            "aliases": ("iphone 15 pro", "айфон 15 про"),
        },
        "iphone_15_pro_max": {
            "label": "iPhone 15 Pro Max",
            "storage": (256, 512, 1024),
            "aliases": ("iphone 15 pro max", "айфон 15 про макс"),
        },
    }
)

MODEL_CHOICES = tuple((key, value["label"]) for key, value in MODEL_REGISTRY.items())


def model_label(model_key: str) -> str:
    entry = MODEL_REGISTRY.get(model_key)
    return str(entry["label"]) if entry else model_key


# ---------- Defect codes (§6.7.2) ----------

DEFECT_CODES: MappingProxyType[str, dict] = MappingProxyType(
    {
        "BATTERY_LT_80": {"label": "АКБ ниже 80%", "exclusive_group": "BATTERY"},
        "BATTERY_80_84": {"label": "АКБ 80–84%", "exclusive_group": "BATTERY"},
        "BATTERY_85_89": {"label": "АКБ 85–89%", "exclusive_group": "BATTERY"},
        "FRONT_GLASS_CRACK": {"label": "Трещина переднего стекла", "exclusive_group": ""},
        "BACK_GLASS_CRACK": {"label": "Трещина заднего стекла", "exclusive_group": ""},
        "DISPLAY_REPLACED": {"label": "Дисплей заменен", "exclusive_group": ""},
        "FACE_ID_BROKEN": {"label": "Face ID не работает", "exclusive_group": ""},
        "TRUE_TONE_MISSING": {"label": "True Tone отсутствует", "exclusive_group": ""},
        "CAMERA_DEFECT": {"label": "Дефект камеры", "exclusive_group": ""},
        "CHARGING_PORT_DEFECT": {"label": "Дефект порта зарядки", "exclusive_group": ""},
        "SPEAKER_MIC_DEFECT": {"label": "Дефект динамика/микрофона", "exclusive_group": ""},
        "BUTTON_DEFECT": {"label": "Дефект кнопок", "exclusive_group": ""},
        "FRAME_DAMAGE": {"label": "Повреждение рамы", "exclusive_group": ""},
        "WATER_DAMAGE": {"label": "Контакт с водой", "exclusive_group": ""},
        "UNKNOWN_REPAIR_HISTORY": {
            "label": "Неизвестная история ремонта",
            "exclusive_group": "",
        },
        "ESIM_ONLY": {"label": "eSIM-only (ликвидность)", "exclusive_group": ""},
    }
)

DEFECT_CODE_CHOICES = tuple((code, meta["label"]) for code, meta in DEFECT_CODES.items())

# ---------- Reason codes ----------

HARD_STOP_CODES = (
    "ITEM_COPY",
    "ITEM_DUMMY",
    "ITEM_ACCESSORY",
    "ITEM_PARTS",
    "ITEM_DONOR",
    "MOTHERBOARD_ONLY",
    "ICLOUD_LOCK",
    "PRICE_MISSING",
    "CURRENCY_UNSUPPORTED",
    "MODEL_UNSUPPORTED",
)

MANUAL_REVIEW_CODES = (
    "MARKET_PRICE_MISSING",
    "MARKET_PRICE_STALE",
    "MODEL_AMBIGUOUS",
    "STORAGE_UNKNOWN",
    "LOCK_STATUS_UNKNOWN",
    "REPAIR_HISTORY_UNKNOWN",
    "RESERVE_RULE_MISSING",
    "PRICE_BORDERLINE",
    "DELIVERY_UNKNOWN",
)

ECONOMICS_CODES = (
    "PROFIT_THRESHOLD_MET",
    "ROI_THRESHOLD_MET",
    "ABOVE_EFFECTIVE_MAX_PRICE",
    "PROFIT_BELOW_THRESHOLD",
    "ROI_BELOW_THRESHOLD",
)

# Additional deterministic filter codes (documented deviation: the spec allows
# profile keyword/seller/delivery filters but does not name their codes).
FILTER_CODES = (
    "KEYWORD_EXCLUDED",
    "KEYWORD_MISSING",
    "SELLER_TYPE_MISMATCH",
    "DELIVERY_MISSING",
    "PRICE_BELOW_MINIMUM",
    "STORAGE_MISMATCH",
    "LISTING_INACTIVE",
)

ALL_REASON_CODES = HARD_STOP_CODES + MANUAL_REVIEW_CODES + ECONOMICS_CODES + FILTER_CODES
