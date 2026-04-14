# Mina Python SDK

Python SDK for interacting with [Mina Protocol](https://minaprotocol.com) nodes.

## Features

- **Daemon GraphQL client** -- query node status, accounts, blocks; send payments and delegations
- Typed response objects with `Currency` arithmetic
- Automatic retry with configurable backoff
- Context manager support for clean resource management

## Installation

```bash
pip install mina-sdk
```

For archive database support (coming soon):

```bash
pip install mina-sdk[archive]
```

## Quick Start

```python
from mina_sdk import MinaDaemonClient, Currency

with MinaDaemonClient() as client:
    # Check sync status
    print(client.get_sync_status())  # "SYNCED"

    # Query an account
    account = client.get_account("B62q...")
    print(f"Balance: {account.balance.total} MINA")

    # Send a payment
    result = client.send_payment(
        sender="B62qsender...",
        receiver="B62qreceiver...",
        amount=Currency("1.5"),
        fee=Currency("0.01"),
    )
    print(f"Tx hash: {result.hash}")
```

## Configuration

```python
client = MinaDaemonClient(
    graphql_uri="http://127.0.0.1:3085/graphql",  # default
    retries=3,        # retry failed requests (must be >= 1)
    retry_delay=5.0,  # seconds between retries (must be >= 0)
    timeout=30.0,     # HTTP timeout in seconds (must be > 0)
)
```

## API Reference

### Queries

| Method | Returns | Description |
|--------|---------|-------------|
| `get_sync_status()` | `str` | Node sync status (SYNCED, BOOTSTRAP, etc.) |
| `get_daemon_status()` | `DaemonStatus` | Comprehensive daemon status |
| `get_network_id()` | `str` | Network identifier |
| `get_account(public_key)` | `AccountData` | Account balance, nonce, delegate |
| `get_best_chain(max_length)` | `list[BlockInfo]` | Recent blocks from best chain |
| `get_peers()` | `list[PeerInfo]` | Connected peers |
| `get_pooled_user_commands(public_key)` | `list[dict]` | Pending transactions |

### Mutations

| Method | Returns | Description |
|--------|---------|-------------|
| `send_payment(sender, receiver, amount, fee)` | `SendPaymentResult` | Send a payment |
| `send_delegation(sender, delegate_to, fee)` | `SendDelegationResult` | Delegate stake |
| `set_snark_worker(public_key)` | `str \| None` | Set/unset SNARK worker |
| `set_snark_work_fee(fee)` | `str` | Set SNARK work fee |

### Currency

```python
from mina_sdk import Currency

a = Currency(10)              # 10 MINA
b = Currency("1.5")           # 1.5 MINA
c = Currency.from_nanomina(1_000_000_000)  # 1 MINA

print(a + b)        # 11.500000000
print(a.nanomina)   # 10000000000
print(a > b)        # True
print(3 * b)        # 4.500000000
```

### Error Handling

```python
from mina_sdk import MinaDaemonClient, GraphQLError, DaemonConnectionError, CurrencyUnderflow

with MinaDaemonClient(retries=3, retry_delay=2.0) as client:
    try:
        account = client.get_account("B62q...")
    except ValueError as e:
        # Account not found on ledger
        print(f"Account does not exist: {e}")
    except GraphQLError as e:
        # Daemon returned a GraphQL-level error
        print(f"GraphQL error: {e}")
        print(f"Raw errors: {e.errors}")
    except DaemonConnectionError as e:
        # All retry attempts exhausted
        print(f"Cannot reach daemon after retries: {e}")

# Currency underflow
from mina_sdk import Currency, CurrencyUnderflow

try:
    result = Currency(1) - Currency(2)
except CurrencyUnderflow:
    print("Subtraction would result in negative balance")
```

### Data Types

All response types are importable from the top-level package:

```python
from mina_sdk import (
    AccountBalance,    # total, liquid, locked balances
    AccountData,       # public_key, nonce, balance, delegate, token_id
    BlockInfo,         # state_hash, height, slots, creator, tx count
    DaemonStatus,      # sync_status, chain height, peers, uptime
    PeerInfo,          # peer_id, host, port
    SendPaymentResult,     # id, hash, nonce
    SendDelegationResult,  # id, hash, nonce
)
```

## Development

```bash
git clone https://github.com/MinaProtocol/mina-sdk-python.git
cd mina-sdk-python
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

### Running integration tests

Integration tests require a running Mina daemon:

```bash
MINA_GRAPHQL_URI=http://127.0.0.1:3085/graphql \
MINA_TEST_SENDER_KEY=B62q... \
MINA_TEST_RECEIVER_KEY=B62q... \
pytest tests/test_integration.py -v
```

## Troubleshooting

**Connection refused / DaemonConnectionError**

The daemon is not running or not reachable at the configured URI. Check:
- Is the daemon running? (`mina client status`)
- Is the GraphQL port open? (default: 3085)
- Is `--insecure-rest-server` set if connecting from a different host?

**GraphQLError: field not found**

The SDK's queries may be out of sync with the daemon's GraphQL schema. This can happen after a daemon upgrade. Check the [schema drift CI](https://github.com/MinaProtocol/mina-sdk-python/actions/workflows/schema-drift.yml) for compatibility status.

**Account not found**

`get_account()` raises `ValueError` when the account doesn't exist on the ledger. This is normal for new accounts that haven't received any transactions yet.

## License

Apache License 2.0
