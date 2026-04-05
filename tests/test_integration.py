"""Integration tests for mina_sdk against a running Mina daemon.

These tests require a running Mina daemon with GraphQL enabled.
They are skipped by default unless MINA_GRAPHQL_URI is set.

Usage:
    # Against a local network started with mina-local-network.sh:
    MINA_GRAPHQL_URI=http://127.0.0.1:3001/graphql pytest tests/test_integration.py -v

    # Against a default daemon:
    MINA_GRAPHQL_URI=http://127.0.0.1:3085/graphql pytest tests/test_integration.py -v

    # With a known funded account (for payment tests):
    MINA_GRAPHQL_URI=http://127.0.0.1:3001/graphql \
    MINA_TEST_SENDER_KEY=B62q... \
    MINA_TEST_RECEIVER_KEY=B62q... \
    pytest tests/test_integration.py -v
"""

from __future__ import annotations

import os
import time

import pytest

from mina_sdk import Currency, MinaDaemonClient

GRAPHQL_URI = os.environ.get("MINA_GRAPHQL_URI", "")
SENDER_KEY = os.environ.get("MINA_TEST_SENDER_KEY", "")
RECEIVER_KEY = os.environ.get("MINA_TEST_RECEIVER_KEY", "")

skip_no_daemon = pytest.mark.skipif(
    not GRAPHQL_URI,
    reason="MINA_GRAPHQL_URI not set — no daemon available",
)

skip_no_accounts = pytest.mark.skipif(
    not (GRAPHQL_URI and SENDER_KEY and RECEIVER_KEY),
    reason="MINA_GRAPHQL_URI, MINA_TEST_SENDER_KEY, and MINA_TEST_RECEIVER_KEY must all be set",
)


@pytest.fixture(scope="module")
def client():
    if not GRAPHQL_URI:
        pytest.skip("no daemon")
    c = MinaDaemonClient(graphql_uri=GRAPHQL_URI, retries=5, retry_delay=10.0, timeout=30.0)
    yield c
    c.close()


@pytest.fixture(scope="module")
def synced_client(client):
    """Wait for daemon to be synced before running tests."""
    max_wait = 300  # 5 minutes
    poll_interval = 5
    elapsed = 0
    while elapsed < max_wait:
        try:
            status = client.get_sync_status()
            if status == "SYNCED":
                return client
            print(f"Waiting for SYNCED, current status: {status} ({elapsed}s)")
        except Exception as e:
            print(f"Waiting for daemon... {e} ({elapsed}s)")
        time.sleep(poll_interval)
        elapsed += poll_interval
    pytest.fail(f"Daemon did not reach SYNCED within {max_wait}s")


# -- Read-only queries (safe, no state changes) --


@skip_no_daemon
class TestDaemonQueries:
    def test_sync_status(self, synced_client):
        status = synced_client.get_sync_status()
        assert status in ("CONNECTING", "LISTENING", "OFFLINE", "BOOTSTRAP", "SYNCED", "CATCHUP")

    def test_daemon_status(self, synced_client):
        status = synced_client.get_daemon_status()
        assert status.sync_status == "SYNCED"
        assert status.blockchain_length is not None
        assert status.blockchain_length > 0

    def test_network_id(self, synced_client):
        network_id = synced_client.get_network_id()
        assert isinstance(network_id, str)
        assert len(network_id) > 0

    def test_get_peers(self, synced_client):
        peers = synced_client.get_peers()
        assert isinstance(peers, list)

    def test_best_chain(self, synced_client):
        blocks = synced_client.get_best_chain(max_length=3)
        assert len(blocks) > 0
        block = blocks[0]
        assert block.height > 0
        assert len(block.state_hash) > 0
        assert len(block.creator_pk) > 0

    def test_best_chain_ordering(self, synced_client):
        blocks = synced_client.get_best_chain(max_length=5)
        if len(blocks) >= 2:
            for i in range(len(blocks) - 1):
                assert blocks[i].height >= blocks[i + 1].height

    def test_pooled_user_commands_no_filter(self, synced_client):
        cmds = synced_client.get_pooled_user_commands()
        assert isinstance(cmds, list)


# -- Account queries (need a known public key) --


@skip_no_accounts
class TestAccountQueries:
    def test_get_account(self, synced_client):
        account = synced_client.get_account(SENDER_KEY)
        assert account.public_key == SENDER_KEY
        assert account.nonce >= 0
        assert account.balance.total >= Currency(0)

    def test_get_account_balance_types(self, synced_client):
        account = synced_client.get_account(SENDER_KEY)
        assert isinstance(account.balance.total, Currency)
        assert account.balance.total.nanomina >= 0

    def test_account_not_found(self, synced_client):
        # A valid-format but non-existent key
        fake_key = "B62qpRzFVjd56FiHnNfxokVbcHMQLT119My1FEdSq8ss7KomLiSZcan"
        with pytest.raises(ValueError, match="account not found"):
            synced_client.get_account(fake_key)


# -- Mutations (send transactions — only if accounts are funded) --


@skip_no_accounts
class TestPayments:
    def test_send_payment(self, synced_client):
        result = synced_client.send_payment(
            sender=SENDER_KEY,
            receiver=RECEIVER_KEY,
            amount=Currency("0.001"),
            fee=Currency("0.01"),
            memo="mina-sdk integration test",
        )
        assert len(result.hash) > 0
        assert result.nonce >= 0
        assert len(result.id) > 0

    def test_send_delegation(self, synced_client):
        result = synced_client.send_delegation(
            sender=SENDER_KEY,
            delegate_to=RECEIVER_KEY,
            fee=Currency("0.01"),
            memo="mina-sdk delegation test",
        )
        assert len(result.hash) > 0
        assert result.nonce >= 0

    def test_payment_appears_in_pool(self, synced_client):
        result = synced_client.send_payment(
            sender=SENDER_KEY,
            receiver=RECEIVER_KEY,
            amount=Currency("0.001"),
            fee=Currency("0.01"),
        )
        # Give the pool a moment to accept it
        time.sleep(2)
        cmds = synced_client.get_pooled_user_commands(SENDER_KEY)
        hashes = [cmd.get("hash") for cmd in cmds]
        assert result.hash in hashes, f"Transaction {result.hash} not found in pool"
