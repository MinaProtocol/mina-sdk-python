"""Mina daemon GraphQL client."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from mina_sdk.daemon import queries
from mina_sdk.types import (
    AccountBalance,
    AccountData,
    BlockInfo,
    Currency,
    DaemonStatus,
    PeerInfo,
    SendDelegationResult,
    SendPaymentResult,
    _parse_response,
)

logger = logging.getLogger(__name__)


class GraphQLError(Exception):
    """Raised when the GraphQL endpoint returns an error response.

    Attributes:
        errors: List of error objects from the GraphQL response.
        query_name: Name of the query/mutation that failed.
    """

    def __init__(self, errors: list[dict[str, Any]], query_name: str = ""):
        self.errors = errors
        self.query_name = query_name
        messages = [e.get("message", str(e)) for e in errors]
        super().__init__(f"GraphQL error in {query_name}: {'; '.join(messages)}")


class DaemonConnectionError(Exception):
    """Raised when the client cannot connect to the daemon after exhausting retries.

    This replaces the previous ``ConnectionError`` name which shadowed the
    built-in ``builtins.ConnectionError``.
    """

    pass


# Keep the old name as an alias for backwards compatibility
ConnectionError = DaemonConnectionError  # noqa: A001


class MinaDaemonClient:
    """Client for interacting with a Mina daemon via its GraphQL API.

    Args:
        graphql_uri: The daemon's GraphQL endpoint URL.
        retries: Number of retry attempts for failed requests (must be >= 1).
        retry_delay: Seconds to wait between retries (must be > 0).
        timeout: HTTP request timeout in seconds (must be > 0).

    Raises:
        ValueError: If any configuration parameter is out of valid range.

    Example::

        with MinaDaemonClient() as client:
            status = client.get_sync_status()
            print(status)
    """

    def __init__(
        self,
        graphql_uri: str = "http://127.0.0.1:3085/graphql",
        retries: int = 3,
        retry_delay: float = 5.0,
        timeout: float = 30.0,
    ):
        if not graphql_uri:
            raise ValueError("graphql_uri must not be empty")
        if retries < 1:
            raise ValueError(f"retries must be >= 1, got {retries}")
        if retry_delay < 0:
            raise ValueError(f"retry_delay must be >= 0, got {retry_delay}")
        if timeout <= 0:
            raise ValueError(f"timeout must be > 0, got {timeout}")

        self._uri = graphql_uri
        self._retries = retries
        self._retry_delay = retry_delay
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        """Release resources held by the HTTP client."""
        self._client.close()

    def __enter__(self) -> MinaDaemonClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _request(
        self, query: str, variables: dict[str, Any] | None = None, query_name: str = ""
    ) -> dict[str, Any]:
        """Execute a GraphQL request with retry logic.

        Returns the ``data`` field of the response.

        Raises:
            GraphQLError: If the response contains GraphQL-level errors (not retried).
            DaemonConnectionError: If all retry attempts fail due to network errors.
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        last_error: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                logger.debug("GraphQL %s attempt %d/%d", query_name, attempt, self._retries)
                resp = self._client.post(self._uri, json=payload)
                resp.raise_for_status()

                try:
                    resp_json = resp.json()
                except ValueError as e:
                    raise DaemonConnectionError(
                        f"Invalid JSON response from {query_name}: {e}"
                    ) from e

                if "errors" in resp_json:
                    raise GraphQLError(resp_json["errors"], query_name)

                return resp_json.get("data", {})

            except GraphQLError:
                raise
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(
                    "GraphQL %s HTTP %d (attempt %d/%d)",
                    query_name,
                    e.response.status_code,
                    attempt,
                    self._retries,
                )
            except httpx.HTTPError as e:
                last_error = e
                logger.warning(
                    "GraphQL %s connection error (attempt %d/%d): %s",
                    query_name,
                    attempt,
                    self._retries,
                    e,
                )

            if attempt < self._retries:
                time.sleep(self._retry_delay)

        raise DaemonConnectionError(
            f"Failed to execute {query_name} after {self._retries} attempts: {last_error}"
        )

    # -- Queries --

    def get_sync_status(self) -> str:
        """Get the node's sync status.

        Returns:
            One of: ``CONNECTING``, ``LISTENING``, ``OFFLINE``, ``BOOTSTRAP``,
            ``SYNCED``, ``CATCHUP``.
        """
        data = self._request(queries.SYNC_STATUS, query_name="get_sync_status")
        return data["syncStatus"]

    def get_daemon_status(self) -> DaemonStatus:
        """Get comprehensive daemon status including sync state, chain height,
        uptime, commit hash, and connected peers."""
        data = self._request(queries.DAEMON_STATUS, query_name="get_daemon_status")
        status = data["daemonStatus"]

        peers = None
        if status.get("peers"):
            peers = [
                PeerInfo(
                    peer_id=p["peerId"],
                    host=p["host"],
                    port=p["libp2pPort"],
                )
                for p in status["peers"]
            ]

        return DaemonStatus(
            sync_status=status["syncStatus"],
            blockchain_length=status.get("blockchainLength"),
            highest_block_length_received=status.get("highestBlockLengthReceived"),
            uptime_secs=status.get("uptimeSecs"),
            state_hash=status.get("stateHash"),
            commit_id=status.get("commitId"),
            peers=peers,
        )

    def get_network_id(self) -> str:
        """Get the network identifier (e.g. ``mina:mainnet``, ``mina:testnet``)."""
        data = self._request(queries.NETWORK_ID, query_name="get_network_id")
        return data["networkID"]

    def get_account(
        self, public_key: str, token_id: str | None = None
    ) -> AccountData:
        """Get account data for a public key.

        Args:
            public_key: Base58-encoded public key (starts with ``B62q``).
            token_id: Optional token ID (defaults to MINA token).

        Raises:
            ValueError: If the account does not exist on the ledger.
        """
        variables: dict[str, Any] = {"publicKey": public_key}
        if token_id is not None:
            variables["token"] = token_id

        data = self._request(queries.GET_ACCOUNT, variables=variables, query_name="get_account")
        acc = data.get("account")
        if acc is None:
            raise ValueError(f"account not found: {public_key}")

        balance = acc["balance"]
        return AccountData(
            public_key=acc["publicKey"],
            nonce=int(acc["nonce"]),
            delegate=acc.get("delegate"),
            token_id=acc.get("tokenId"),
            balance=AccountBalance(
                total=Currency.from_graphql(balance["total"]),
                liquid=Currency.from_graphql(balance["liquid"]) if balance.get("liquid") else None,
                locked=Currency.from_graphql(balance["locked"]) if balance.get("locked") else None,
            ),
        )

    def get_best_chain(self, max_length: int | None = None) -> list[BlockInfo]:
        """Get blocks from the best chain, ordered from highest to lowest.

        Args:
            max_length: Maximum number of blocks to return.  ``None`` uses the
                daemon's default.
        """
        variables: dict[str, Any] = {}
        if max_length is not None:
            variables["maxLength"] = max_length

        data = self._request(
            queries.BEST_CHAIN, variables=variables or None, query_name="get_best_chain"
        )
        chain = data.get("bestChain")
        if not chain:
            return []

        blocks = []
        for block in chain:
            consensus = block["protocolState"]["consensusState"]
            creator = block.get("creatorAccount", {})
            creator_pk = creator.get("publicKey", "unknown")
            if isinstance(creator_pk, dict):
                creator_pk = str(creator_pk)

            blocks.append(
                BlockInfo(
                    state_hash=block["stateHash"],
                    height=int(consensus["blockHeight"]),
                    global_slot_since_hard_fork=int(consensus["slot"]),
                    global_slot_since_genesis=int(consensus["slotSinceGenesis"]),
                    creator_pk=creator_pk,
                    command_transaction_count=block["commandTransactionCount"],
                )
            )
        return blocks

    def get_peers(self) -> list[PeerInfo]:
        """Get the list of connected peers."""
        data = self._request(queries.GET_PEERS, query_name="get_peers")
        return [
            PeerInfo(peer_id=p["peerId"], host=p["host"], port=p["libp2pPort"])
            for p in data.get("getPeers", [])
        ]

    def get_pooled_user_commands(self, public_key: str | None = None) -> list[dict[str, Any]]:
        """Get pending user commands from the transaction pool.

        Args:
            public_key: Optional filter by sender public key.

        Returns:
            Raw list of transaction dictionaries from the mempool.  Each dict
            contains keys: ``id``, ``hash``, ``kind``, ``nonce``, ``amount``,
            ``fee``, ``from``, ``to``.
        """
        variables: dict[str, Any] = {}
        if public_key is not None:
            variables["publicKey"] = public_key

        data = self._request(
            queries.POOLED_USER_COMMANDS,
            variables=variables or None,
            query_name="get_pooled_user_commands",
        )
        return data.get("pooledUserCommands", [])

    # -- Mutations --

    def send_payment(
        self,
        sender: str,
        receiver: str,
        amount: Currency | str,
        fee: Currency | str,
        memo: str | None = None,
        nonce: int | None = None,
    ) -> SendPaymentResult:
        """Send a payment transaction.

        Requires the sender's account to be unlocked on the node.

        Args:
            sender: Sender public key (base58).
            receiver: Receiver public key (base58).
            amount: Amount to send (``Currency`` or MINA string like ``"1.5"``).
            fee: Transaction fee (``Currency`` or MINA string).
            memo: Optional transaction memo (max 32 bytes).
            nonce: Optional explicit nonce.  If omitted the daemon auto-increments.

        Raises:
            GraphQLError: If the daemon rejects the transaction.
        """
        if isinstance(amount, str):
            amount = Currency(amount)
        if isinstance(fee, str):
            fee = Currency(fee)

        input_obj: dict[str, Any] = {
            "from": sender,
            "to": receiver,
            "amount": amount.to_nanomina_str(),
            "fee": fee.to_nanomina_str(),
        }
        if memo is not None:
            input_obj["memo"] = memo
        if nonce is not None:
            input_obj["nonce"] = str(nonce)

        data = self._request(
            queries.SEND_PAYMENT, variables={"input": input_obj}, query_name="send_payment"
        )
        payment = _parse_response(data, ["sendPayment", "payment"])
        return SendPaymentResult(
            id=payment["id"],
            hash=payment["hash"],
            nonce=int(payment["nonce"]),
        )

    def send_delegation(
        self,
        sender: str,
        delegate_to: str,
        fee: Currency | str,
        memo: str | None = None,
        nonce: int | None = None,
    ) -> SendDelegationResult:
        """Send a stake delegation transaction.

        Requires the sender's account to be unlocked on the node.

        Args:
            sender: Delegator public key (base58).
            delegate_to: Delegate-to public key (base58).
            fee: Transaction fee (``Currency`` or MINA string).
            memo: Optional transaction memo.
            nonce: Optional explicit nonce.
        """
        if isinstance(fee, str):
            fee = Currency(fee)

        input_obj: dict[str, Any] = {
            "from": sender,
            "to": delegate_to,
            "fee": fee.to_nanomina_str(),
        }
        if memo is not None:
            input_obj["memo"] = memo
        if nonce is not None:
            input_obj["nonce"] = str(nonce)

        data = self._request(
            queries.SEND_DELEGATION, variables={"input": input_obj}, query_name="send_delegation"
        )
        delegation = _parse_response(data, ["sendDelegation", "delegation"])
        return SendDelegationResult(
            id=delegation["id"],
            hash=delegation["hash"],
            nonce=int(delegation["nonce"]),
        )

    def set_snark_worker(self, public_key: str | None) -> str | None:
        """Set or unset the SNARK worker key.

        Args:
            public_key: Public key for snark worker, or ``None`` to disable.

        Returns:
            The previous snark worker public key, or ``None`` if there was none.
        """
        data = self._request(
            queries.SET_SNARK_WORKER,
            variables={"input": public_key},
            query_name="set_snark_worker",
        )
        return _parse_response(data, ["setSnarkWorker", "lastSnarkWorker"])

    def set_snark_work_fee(self, fee: Currency | str) -> str:
        """Set the fee for SNARK work.

        Args:
            fee: The fee amount (``Currency`` or MINA string).

        Returns:
            The previous fee as a nanomina string.
        """
        if isinstance(fee, str):
            fee = Currency(fee)
        data = self._request(
            queries.SET_SNARK_WORK_FEE,
            variables={"fee": fee.to_nanomina_str()},
            query_name="set_snark_work_fee",
        )
        return _parse_response(data, ["setSnarkWorkFee", "lastFee"])
