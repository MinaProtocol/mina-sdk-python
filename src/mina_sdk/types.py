"""Shared types for the Mina SDK."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CurrencyFormat(Enum):
    """Representation format for Mina currency values.

    WHOLE: 1 MINA = 10^9 nanomina
    NANO: atomic unit (nanomina)
    """

    WHOLE = 1
    NANO = 2


class CurrencyUnderflow(Exception):
    pass


class Currency:
    """Convenience wrapper for Mina currency values with arithmetic support.

    Internally stores values as nanomina (the atomic unit).
    Supports addition, subtraction, multiplication, and comparison.
    """

    NANOMINA_PER_MINA = 1_000_000_000

    def __init__(self, value: int | float | str, fmt: CurrencyFormat = CurrencyFormat.WHOLE):
        if fmt == CurrencyFormat.WHOLE:
            if isinstance(value, int):
                self._nanomina = value * self.NANOMINA_PER_MINA
            elif isinstance(value, float):
                self._nanomina = self._parse_decimal(str(value))
            elif isinstance(value, str):
                self._nanomina = self._parse_decimal(value)
            else:
                raise TypeError(f"cannot construct Currency from {type(value)}")
        elif fmt == CurrencyFormat.NANO:
            if not isinstance(value, int):
                raise TypeError(f"nanomina value must be int, got {type(value)}")
            self._nanomina = value
        else:
            raise ValueError(f"invalid CurrencyFormat: {fmt}")

    @staticmethod
    def _parse_decimal(s: str) -> int:
        segments = s.split(".")
        if len(segments) == 1:
            return int(segments[0]) * Currency.NANOMINA_PER_MINA
        elif len(segments) == 2:
            left, right = segments
            if len(right) <= 9:
                return int(left + right + "0" * (9 - len(right)))
            else:
                raise ValueError(f"invalid mina currency format: {s}")
        else:
            raise ValueError(f"invalid mina currency format: {s}")

    @classmethod
    def from_nanomina(cls, nanomina: int) -> Currency:
        return cls(nanomina, fmt=CurrencyFormat.NANO)

    @classmethod
    def from_graphql(cls, value: str) -> Currency:
        """Parse a currency value as returned by the GraphQL API (nanomina string)."""
        return cls(int(value), fmt=CurrencyFormat.NANO)

    @classmethod
    def random(cls, lower: Currency, upper: Currency) -> Currency:
        if not (isinstance(lower, Currency) and isinstance(upper, Currency)):
            raise TypeError("bounds must be Currency instances")
        if upper.nanomina < lower.nanomina:
            raise ValueError("upper bound must be >= lower bound")
        if lower.nanomina == upper.nanomina:
            return lower
        delta = random.randint(0, upper.nanomina - lower.nanomina)
        return cls.from_nanomina(lower.nanomina + delta)

    @property
    def nanomina(self) -> int:
        return self._nanomina

    @property
    def mina(self) -> str:
        """Decimal string representation in whole MINA."""
        s = str(self._nanomina)
        if len(s) > 9:
            return s[:-9] + "." + s[-9:]
        else:
            return "0." + "0" * (9 - len(s)) + s

    def to_nanomina_str(self) -> str:
        """String representation for GraphQL API (nanomina)."""
        return str(self._nanomina)

    def __str__(self) -> str:
        return self.mina

    def __repr__(self) -> str:
        return f"Currency({self.mina})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Currency):
            return self._nanomina == other._nanomina
        return NotImplemented

    def __lt__(self, other: Currency) -> bool:
        if isinstance(other, Currency):
            return self._nanomina < other._nanomina
        return NotImplemented

    def __le__(self, other: Currency) -> bool:
        if isinstance(other, Currency):
            return self._nanomina <= other._nanomina
        return NotImplemented

    def __gt__(self, other: Currency) -> bool:
        if isinstance(other, Currency):
            return self._nanomina > other._nanomina
        return NotImplemented

    def __ge__(self, other: Currency) -> bool:
        if isinstance(other, Currency):
            return self._nanomina >= other._nanomina
        return NotImplemented

    def __add__(self, other: Currency) -> Currency:
        if isinstance(other, Currency):
            return Currency.from_nanomina(self._nanomina + other._nanomina)
        return NotImplemented

    def __sub__(self, other: Currency) -> Currency:
        if isinstance(other, Currency):
            result = self._nanomina - other._nanomina
            if result < 0:
                raise CurrencyUnderflow(f"subtraction would result in negative: {self} - {other}")
            return Currency.from_nanomina(result)
        return NotImplemented

    def __mul__(self, other: int | Currency) -> Currency:
        if isinstance(other, int):
            return Currency.from_nanomina(self._nanomina * other)
        if isinstance(other, Currency):
            return Currency.from_nanomina(self._nanomina * other._nanomina)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._nanomina)


@dataclass(frozen=True)
class AccountBalance:
    total: Currency
    liquid: Currency | None = None
    locked: Currency | None = None


@dataclass(frozen=True)
class AccountData:
    public_key: str
    nonce: int
    balance: AccountBalance
    delegate: str | None = None
    token_id: str | None = None


@dataclass(frozen=True)
class PeerInfo:
    peer_id: str
    host: str
    port: int


@dataclass(frozen=True)
class DaemonStatus:
    sync_status: str
    blockchain_length: int | None = None
    highest_block_length_received: int | None = None
    uptime_secs: int | None = None
    peers: list[PeerInfo] | None = None
    commit_id: str | None = None
    state_hash: str | None = None


@dataclass(frozen=True)
class BlockInfo:
    state_hash: str
    height: int
    global_slot_since_hard_fork: int
    global_slot_since_genesis: int
    creator_pk: str
    command_transaction_count: int


@dataclass(frozen=True)
class SendPaymentResult:
    id: str
    hash: str
    nonce: int


@dataclass(frozen=True)
class SendDelegationResult:
    id: str
    hash: str
    nonce: int


def _parse_response(data: dict[str, Any], path: list[str]) -> Any:
    """Navigate a nested dict by a list of keys, raising clear errors on missing fields."""
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"missing field '{key}' in response at path {path}")
        current = current[key]
    return current
