"""GraphQL query and mutation strings for the Mina daemon."""

SYNC_STATUS = """
query {
    syncStatus
}
"""

DAEMON_STATUS = """
query {
    daemonStatus {
        syncStatus
        blockchainLength
        highestBlockLengthReceived
        uptimeSecs
        stateHash
        commitId
        peers {
            peerId
            host
            libp2pPort
        }
    }
}
"""

NETWORK_ID = """
query {
    networkID
}
"""

GET_ACCOUNT = """
query ($publicKey: PublicKey!, $token: UInt64) {
    account(publicKey: $publicKey, token: $token) {
        publicKey
        nonce
        delegate
        tokenId
        balance {
            total
            liquid
            locked
        }
    }
}
"""

BEST_CHAIN = """
query ($maxLength: Int) {
    bestChain(maxLength: $maxLength) {
        stateHash
        commandTransactionCount
        creatorAccount {
            publicKey
        }
        protocolState {
            consensusState {
                blockHeight
                slotSinceGenesis
                slot
            }
        }
    }
}
"""

GET_PEERS = """
query {
    getPeers {
        peerId
        host
        libp2pPort
    }
}
"""

POOLED_USER_COMMANDS = """
query ($publicKey: PublicKey!) {
    pooledUserCommands(publicKey: $publicKey) {
        id
        hash
        kind
        nonce
        amount
        fee
        from
        to
    }
}
"""

POOLED_USER_COMMANDS_ALL = """
query {
    pooledUserCommands {
        id
        hash
        kind
        nonce
        amount
        fee
        from
        to
    }
}
"""

SEND_PAYMENT = """
mutation ($input: SendPaymentInput!) {
    sendPayment(input: $input) {
        payment {
            id
            hash
            nonce
        }
    }
}
"""

SEND_DELEGATION = """
mutation ($input: SendDelegationInput!) {
    sendDelegation(input: $input) {
        delegation {
            id
            hash
            nonce
        }
    }
}
"""

SET_SNARK_WORKER = """
mutation ($input: SetSnarkWorkerInput!) {
    setSnarkWorker(input: $input) {
        lastSnarkWorker
    }
}
"""

SET_SNARK_WORK_FEE = """
mutation ($fee: UInt64!) {
    setSnarkWorkFee(input: {fee: $fee}) {
        lastFee
    }
}
"""
