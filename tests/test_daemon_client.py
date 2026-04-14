"""Tests for mina_sdk.daemon.client."""

from __future__ import annotations

import httpx
import pytest
import respx

from mina_sdk.daemon.client import ConnectionError, GraphQLError, MinaDaemonClient
from mina_sdk.types import Currency

GRAPHQL_URL = "http://localhost:3085/graphql"


@pytest.fixture
def client():
    c = MinaDaemonClient(graphql_uri=GRAPHQL_URL, retries=1, retry_delay=0.0, timeout=5.0)
    yield c
    c.close()


def _gql_response(data):
    return httpx.Response(200, json={"data": data})


def _gql_error(errors):
    return httpx.Response(200, json={"errors": errors})


@respx.mock
def test_sync_status_synced(client):
    respx.post(GRAPHQL_URL).mock(return_value=_gql_response({"syncStatus": "SYNCED"}))
    assert client.get_sync_status() == "SYNCED"


@respx.mock
def test_sync_status_bootstrap(client):
    respx.post(GRAPHQL_URL).mock(return_value=_gql_response({"syncStatus": "BOOTSTRAP"}))
    assert client.get_sync_status() == "BOOTSTRAP"


@respx.mock
def test_daemon_status(client):
    respx.post(GRAPHQL_URL).mock(
        return_value=_gql_response(
            {
                "daemonStatus": {
                    "syncStatus": "SYNCED",
                    "blockchainLength": 100,
                    "highestBlockLengthReceived": 100,
                    "uptimeSecs": 3600,
                    "stateHash": "3NKtest...",
                    "commitId": "abc123",
                    "peers": [{"peerId": "peer1", "host": "1.2.3.4", "libp2pPort": 8302}],
                }
            }
        )
    )
    status = client.get_daemon_status()
    assert status.sync_status == "SYNCED"
    assert status.blockchain_length == 100
    assert status.uptime_secs == 3600
    assert len(status.peers) == 1
    assert status.peers[0].peer_id == "peer1"
    assert status.peers[0].host == "1.2.3.4"
    assert status.peers[0].port == 8302


@respx.mock
def test_network_id(client):
    respx.post(GRAPHQL_URL).mock(return_value=_gql_response({"networkID": "mina:testnet"}))
    assert client.get_network_id() == "mina:testnet"


@respx.mock
def test_get_account(client):
    respx.post(GRAPHQL_URL).mock(
        return_value=_gql_response(
            {
                "account": {
                    "publicKey": "B62qtest...",
                    "nonce": "5",
                    "delegate": "B62qdelegate...",
                    "tokenId": "1",
                    "balance": {
                        "total": "1500000000000",
                        "liquid": "1000000000000",
                        "locked": "500000000000",
                    },
                }
            }
        )
    )
    account = client.get_account("B62qtest...")
    assert account.public_key == "B62qtest..."
    assert account.nonce == 5
    assert account.delegate == "B62qdelegate..."
    assert account.balance.total == Currency(1500)
    assert account.balance.liquid == Currency(1000)
    assert account.balance.locked == Currency(500)


@respx.mock
def test_get_account_not_found(client):
    respx.post(GRAPHQL_URL).mock(return_value=_gql_response({"account": None}))
    with pytest.raises(ValueError, match="account not found"):
        client.get_account("B62qnotfound...")


@respx.mock
def test_best_chain(client):
    respx.post(GRAPHQL_URL).mock(
        return_value=_gql_response(
            {
                "bestChain": [
                    {
                        "stateHash": "3NKhash1",
                        "commandTransactionCount": 3,
                        "creatorAccount": {"publicKey": "B62qcreator..."},
                        "protocolState": {
                            "consensusState": {
                                "blockHeight": "50",
                                "slotSinceGenesis": "1000",
                                "slot": "500",
                            }
                        },
                    }
                ]
            }
        )
    )
    blocks = client.get_best_chain(max_length=1)
    assert len(blocks) == 1
    assert blocks[0].state_hash == "3NKhash1"
    assert blocks[0].height == 50
    assert blocks[0].creator_pk == "B62qcreator..."
    assert blocks[0].command_transaction_count == 3


@respx.mock
def test_best_chain_empty(client):
    respx.post(GRAPHQL_URL).mock(return_value=_gql_response({"bestChain": None}))
    assert client.get_best_chain() == []


@respx.mock
def test_send_payment(client):
    respx.post(GRAPHQL_URL).mock(
        return_value=_gql_response(
            {
                "sendPayment": {
                    "payment": {
                        "id": "txn-id-123",
                        "hash": "CkpHash...",
                        "nonce": "6",
                    }
                }
            }
        )
    )
    result = client.send_payment(
        sender="B62qsender...",
        receiver="B62qreceiver...",
        amount=Currency(10),
        fee=Currency("0.1"),
    )
    assert result.id == "txn-id-123"
    assert result.hash == "CkpHash..."
    assert result.nonce == 6


@respx.mock
def test_send_payment_string_amounts(client):
    respx.post(GRAPHQL_URL).mock(
        return_value=_gql_response(
            {"sendPayment": {"payment": {"id": "x", "hash": "y", "nonce": "1"}}}
        )
    )
    result = client.send_payment(
        sender="B62qsender...",
        receiver="B62qreceiver...",
        amount="5.0",
        fee="0.01",
    )
    assert result.nonce == 1


@respx.mock
def test_send_delegation(client):
    respx.post(GRAPHQL_URL).mock(
        return_value=_gql_response(
            {
                "sendDelegation": {
                    "delegation": {
                        "id": "del-id-456",
                        "hash": "CkpDel...",
                        "nonce": "7",
                    }
                }
            }
        )
    )
    result = client.send_delegation(
        sender="B62qsender...",
        delegate_to="B62qdelegate...",
        fee=Currency("0.1"),
    )
    assert result.id == "del-id-456"
    assert result.hash == "CkpDel..."
    assert result.nonce == 7


@respx.mock
def test_graphql_error(client):
    respx.post(GRAPHQL_URL).mock(return_value=_gql_error([{"message": "field not found"}]))
    with pytest.raises(GraphQLError, match="field not found"):
        client.get_sync_status()


@respx.mock
def test_connection_error_after_retries():
    respx.post(GRAPHQL_URL).mock(side_effect=httpx.ConnectError("refused"))
    client = MinaDaemonClient(graphql_uri=GRAPHQL_URL, retries=2, retry_delay=0.0, timeout=1.0)
    with pytest.raises(ConnectionError, match="after 2 attempts"):
        client.get_sync_status()
    client.close()


@respx.mock
def test_context_manager():
    respx.post(GRAPHQL_URL).mock(return_value=_gql_response({"syncStatus": "SYNCED"}))
    with MinaDaemonClient(graphql_uri=GRAPHQL_URL, retries=1) as client:
        assert client.get_sync_status() == "SYNCED"


@respx.mock
def test_get_peers(client):
    respx.post(GRAPHQL_URL).mock(
        return_value=_gql_response(
            {
                "getPeers": [
                    {"peerId": "p1", "host": "10.0.0.1", "libp2pPort": 8302},
                    {"peerId": "p2", "host": "10.0.0.2", "libp2pPort": 8302},
                ]
            }
        )
    )
    peers = client.get_peers()
    assert len(peers) == 2
    assert peers[0].peer_id == "p1"
    assert peers[1].host == "10.0.0.2"


@respx.mock
def test_pooled_user_commands(client):
    respx.post(GRAPHQL_URL).mock(
        return_value=_gql_response(
            {
                "pooledUserCommands": [
                    {
                        "id": "cmd1",
                        "hash": "CkpHash1",
                        "kind": "PAYMENT",
                        "nonce": "1",
                        "amount": "1000000000",
                        "fee": "10000000",
                        "from": "B62qsender...",
                        "to": "B62qreceiver...",
                    }
                ]
            }
        )
    )
    cmds = client.get_pooled_user_commands("B62qsender...")
    assert len(cmds) == 1
    assert cmds[0]["kind"] == "PAYMENT"


# -- Parameter validation tests --


def test_invalid_retries():
    with pytest.raises(ValueError, match="retries must be >= 1"):
        MinaDaemonClient(retries=0)


def test_invalid_negative_retry_delay():
    with pytest.raises(ValueError, match="retry_delay must be >= 0"):
        MinaDaemonClient(retry_delay=-1.0)


def test_invalid_timeout():
    with pytest.raises(ValueError, match="timeout must be > 0"):
        MinaDaemonClient(timeout=0)


def test_empty_graphql_uri():
    with pytest.raises(ValueError, match="graphql_uri must not be empty"):
        MinaDaemonClient(graphql_uri="")


@respx.mock
def test_json_decode_error():
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(200, text="not json"))
    client = MinaDaemonClient(graphql_uri=GRAPHQL_URL, retries=1, retry_delay=0.0, timeout=5.0)
    with pytest.raises(ConnectionError, match="Invalid JSON"):
        client.get_sync_status()
    client.close()


@respx.mock
def test_http_500_retried():
    respx.post(GRAPHQL_URL).mock(return_value=httpx.Response(500, text="Internal Server Error"))
    client = MinaDaemonClient(graphql_uri=GRAPHQL_URL, retries=2, retry_delay=0.0, timeout=5.0)
    with pytest.raises(ConnectionError, match="after 2 attempts"):
        client.get_sync_status()
    client.close()


@respx.mock
def test_daemon_connection_error_alias():
    """DaemonConnectionError and ConnectionError are the same class."""
    from mina_sdk.daemon.client import DaemonConnectionError

    respx.post(GRAPHQL_URL).mock(side_effect=httpx.ConnectError("refused"))
    client = MinaDaemonClient(graphql_uri=GRAPHQL_URL, retries=1, retry_delay=0.0, timeout=1.0)
    with pytest.raises(DaemonConnectionError):
        client.get_sync_status()
    client.close()
