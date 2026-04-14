"""Tests for mina_sdk.types."""

import pytest

from mina_sdk.types import Currency, CurrencyFormat, CurrencyUnderflow


class TestCurrency:
    def test_whole_from_int(self):
        c = Currency(5)
        assert c.nanomina == 5_000_000_000
        assert c.mina == "5.000000000"

    def test_whole_from_float(self):
        c = Currency(1.5)
        assert c.nanomina == 1_500_000_000

    def test_whole_from_string(self):
        c = Currency("2.5")
        assert c.nanomina == 2_500_000_000

    def test_whole_from_string_no_decimal(self):
        c = Currency("100")
        assert c.nanomina == 100_000_000_000

    def test_nano_from_int(self):
        c = Currency(1000, fmt=CurrencyFormat.NANO)
        assert c.nanomina == 1000
        assert c.mina == "0.000001000"

    def test_nano_rejects_float(self):
        with pytest.raises(TypeError):
            Currency(1.5, fmt=CurrencyFormat.NANO)

    def test_from_nanomina(self):
        c = Currency.from_nanomina(500_000_000)
        assert c.mina == "0.500000000"

    def test_from_graphql(self):
        c = Currency.from_graphql("1500000000")
        assert c.nanomina == 1_500_000_000

    def test_to_nanomina_str(self):
        c = Currency(3)
        assert c.to_nanomina_str() == "3000000000"

    def test_addition(self):
        a = Currency(1)
        b = Currency(2)
        assert (a + b).nanomina == 3_000_000_000

    def test_subtraction(self):
        a = Currency(3)
        b = Currency(1)
        assert (a - b).nanomina == 2_000_000_000

    def test_subtraction_underflow(self):
        a = Currency(1)
        b = Currency(2)
        with pytest.raises(CurrencyUnderflow):
            a - b

    def test_multiplication_by_int(self):
        c = Currency(2)
        assert (c * 3).nanomina == 6_000_000_000

    def test_equality(self):
        a = Currency(1)
        b = Currency.from_nanomina(1_000_000_000)
        assert a == b

    def test_comparison(self):
        a = Currency(1)
        b = Currency(2)
        assert a < b
        assert a <= b
        assert b > a
        assert b >= a

    def test_hash(self):
        a = Currency(1)
        b = Currency.from_nanomina(1_000_000_000)
        assert hash(a) == hash(b)
        assert {a, b} == {a}

    def test_repr(self):
        c = Currency("1.23")
        assert repr(c) == "Currency(1.230000000)"

    def test_str(self):
        c = Currency(0, fmt=CurrencyFormat.NANO)
        assert str(c) == "0.000000000"

    def test_random(self):
        lower = Currency(1)
        upper = Currency(10)
        for _ in range(50):
            r = Currency.random(lower, upper)
            assert lower <= r <= upper

    def test_random_equal_bounds(self):
        c = Currency(5)
        assert Currency.random(c, c) == c

    def test_invalid_decimal_format(self):
        with pytest.raises(ValueError):
            Currency("1.2345678901")  # >9 decimal places

    def test_small_nanomina_display(self):
        c = Currency.from_nanomina(1)
        assert c.mina == "0.000000001"

    def test_negative_whole_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            Currency(-10)

    def test_negative_nano_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            Currency(-1, fmt=CurrencyFormat.NANO)

    def test_rmul(self):
        c = Currency(2)
        assert (3 * c).nanomina == 6_000_000_000

    def test_mul_currency_by_currency_rejected(self):
        a = Currency(2)
        b = Currency(3)
        result = a.__mul__(b)
        assert result is NotImplemented
