"""Mina Protocol Python SDK.

Provides a typed client for the Mina daemon's GraphQL API with
currency arithmetic, automatic retries, and context manager support.

Quick start::

    from mina_sdk import MinaDaemonClient, Currency

    with MinaDaemonClient() as client:
        status = client.get_sync_status()
        account = client.get_account("B62q...")
        print(f"Balance: {account.balance.total} MINA")
"""

from mina_sdk.daemon.client import (
    DaemonConnectionError,
    GraphQLError,
    MinaDaemonClient,
)
from mina_sdk.types import (
    AccountBalance,
    AccountData,
    BlockInfo,
    Currency,
    CurrencyFormat,
    CurrencyUnderflow,
    DaemonStatus,
    PeerInfo,
    SendDelegationResult,
    SendPaymentResult,
)

__all__ = [
    "AccountBalance",
    "AccountData",
    "BlockInfo",
    "Currency",
    "CurrencyFormat",
    "CurrencyUnderflow",
    "DaemonConnectionError",
    "DaemonStatus",
    "GraphQLError",
    "MinaDaemonClient",
    "PeerInfo",
    "SendDelegationResult",
    "SendPaymentResult",
]

__version__ = "0.1.0"
