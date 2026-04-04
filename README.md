# Mina Python SDK

Python SDK for interacting with [Mina Protocol](https://minaprotocol.com) nodes.

## Features

- **Daemon GraphQL client** — query node status, accounts, blocks; send payments and delegations
- Typed response objects with `Currency` arithmetic
- Automatic retry with configurable backoff
- Context manager support

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
    retries=3,        # retry failed requests
    retry_delay=5.0,  # seconds between retries
    timeout=30.0,     # HTTP timeout in seconds
)
```

## API Reference

### Queries

| Method | Description |
|--------|-------------|
| `get_sync_status()` | Node sync status (SYNCED, BOOTSTRAP, etc.) |
| `get_daemon_status()` | Comprehensive daemon status |
| `get_network_id()` | Network identifier |
| `get_account(public_key)` | Account balance, nonce, delegate |
| `get_best_chain(max_length)` | Recent blocks from best chain |
| `get_peers()` | Connected peers |
| `get_pooled_user_commands(public_key)` | Pending transactions |

### Mutations

| Method | Description |
|--------|-------------|
| `send_payment(sender, receiver, amount, fee)` | Send a payment |
| `send_delegation(sender, delegate_to, fee)` | Delegate stake |
| `set_snark_worker(public_key)` | Set/unset SNARK worker |
| `set_snark_work_fee(fee)` | Set SNARK work fee |

### Currency

```python
from mina_sdk import Currency

a = Currency(10)              # 10 MINA
b = Currency("1.5")           # 1.5 MINA
c = Currency.from_nanomina(1_000_000_000)  # 1 MINA

print(a + b)        # 11.500000000
print(a.nanomina)   # 10000000000
print(a > b)        # True
```

## Development

```bash
git clone https://github.com/MinaProtocol/mina-sdk-python.git
cd mina-sdk-python
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

Apache License 2.0
