"""U-04, U-05: модель и память; boundary-случаи реестра §6.7.1."""

import pytest

from apps.pricing.constants import MODEL_REGISTRY
from apps.pricing.extraction import (
    battery_defect_code,
    extract_battery_percent,
    extract_model,
    extract_storage,
)


class TestModelExtraction:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("iPhone 13", "iphone_13"),
            ("IPHONE 13 PRO", "iphone_13_pro"),
            ("iphone 13 pro max", "iphone_13_pro_max"),
            ("Айфон 13 Про Макс", "iphone_13_pro_max"),
            ("айфон13", "iphone_13"),
            ("iPhone 12 mini 64", "iphone_12_mini"),
            ("Продам iPhone 14 Plus", "iphone_14_plus"),
            ("iPhone 15 Pro Max 256", "iphone_15_pro_max"),
            ("iPhone 11 PRO", "iphone_11_pro"),
        ],
    )
    def test_exact_model(self, text, expected):
        assert extract_model(text) == (expected, False)

    def test_pro_not_confused_with_base(self):
        # U-04 boundary: «13 Pro» никогда не должен схлопнуться в «13».
        assert extract_model("iPhone 13 Pro 128") == ("iphone_13_pro", False)
        assert extract_model("iPhone 13 128") == ("iphone_13", False)

    def test_ambiguous_two_models(self):
        model, ambiguous = extract_model("Обмен iPhone 13 на iPhone 14")
        assert model is None
        assert ambiguous is True

    def test_unknown_model(self):
        assert extract_model("Samsung Galaxy S24") == (None, False)
        assert extract_model("iPhone 16 Pro") == (None, False)  # вне реестра MVP

    def test_word_boundaries(self):
        # «про» как часть слова не должно распознаваться.
        model, ambiguous = extract_model("айфон 13 проверенный")
        assert model == "iphone_13"
        assert ambiguous is False


class TestStorage:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("128 GB", 128),
            ("128gb", 128),
            ("128 ГБ", 128),
            ("256GB", 256),
            ("1TB", 1024),
            ("1 tb", 1024),
            ("1024gb", 1024),
            ("1024 gb", 1024),
            ("64 гб", 64),
            ("без указания", None),
            ("Дом 128 квартира", None),  # число без единицы измерения
        ],
    )
    def test_extract_storage(self, text, expected):
        assert extract_storage(text) == expected

    def test_conflicting_values_unknown(self):
        assert extract_storage("продам 128gb или 256gb") is None

    def test_invalid_pair_for_model(self):
        # 15 Pro Max не существует с 128 GB — реестр это знает.
        assert 128 not in MODEL_REGISTRY["iphone_15_pro_max"]["storage"]


class TestBattery:
    def test_battery_extraction(self):
        assert extract_battery_percent("АКБ 87%") == 87
        assert extract_battery_percent("батарея 100") == 100
        assert extract_battery_percent("ємність 79%") == 79
        assert extract_battery_percent("без данных") is None

    @pytest.mark.parametrize(
        "percent,code",
        [
            (79, "BATTERY_LT_80"),
            (80, "BATTERY_80_84"),
            (84, "BATTERY_80_84"),
            (85, "BATTERY_85_89"),
            (89, "BATTERY_85_89"),
            (90, None),
            (None, None),
        ],
    )
    def test_battery_groups(self, percent, code):
        assert battery_defect_code(percent) == code
