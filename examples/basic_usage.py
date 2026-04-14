"""Basic usage of the Mina Python SDK."""

from mina_sdk import (
    Currency,
    DaemonConnectionError,
    GraphQLError,
    MinaDaemonClient,
)


def main():
    """Demonstrate core SDK features against a local daemon."""
    # Connect to a local Mina daemon (default: http://127.0.0.1:3085/graphql)
    with MinaDaemonClient() as client:
        # Check sync status
        sync_status = client.get_sync_status()
        print(f"Sync status: {sync_status}")

        # Get daemon status with peer info
        status = client.get_daemon_status()
        print(f"Blockchain length: {status.blockchain_length}")
        print(f"Peers: {len(status.peers) if status.peers else 0}")

        # Get network ID
        network_id = client.get_network_id()
        print(f"Network: {network_id}")

        # Query an account (replace with a real public key)
        try:
            account = client.get_account("B62qrPN5Y5yq8kGE3FbVKbGTdTAJNdtNtS5vH1tH...")
            print(f"Balance: {account.balance.total} MINA")
            print(f"Nonce: {account.nonce}")
        except ValueError as e:
            print(f"Account not found: {e}")

        # Get recent blocks
        blocks = client.get_best_chain(max_length=5)
        for block in blocks:
            print(
                f"Block {block.height}: {block.state_hash[:20]}... "
                f"({block.command_transaction_count} txns)"
            )

        # Send a payment (requires sender account unlocked on node)
        try:
            result = client.send_payment(
                sender="B62qsender...",
                receiver="B62qreceiver...",
                amount=Currency("1.5"),  # 1.5 MINA
                fee=Currency("0.01"),  # 0.01 MINA fee
                memo="hello from SDK",
            )
            print(f"Payment sent! Hash: {result.hash}, Nonce: {result.nonce}")
        except GraphQLError as e:
            print(f"Payment failed: {e}")


def connect_to_remote_node():
    """Connect to a remote daemon with custom retry settings."""
    try:
        client = MinaDaemonClient(
            graphql_uri="http://my-mina-node:3085/graphql",
            retries=5,
            retry_delay=10.0,
            timeout=60.0,
        )
        try:
            status = client.get_sync_status()
            print(f"Remote node status: {status}")
        finally:
            client.close()
    except DaemonConnectionError as e:
        print(f"Could not reach remote node: {e}")


if __name__ == "__main__":
    main()
