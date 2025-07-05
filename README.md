# Project-Seed: Cross-Chain Bridge Event Listener

This repository contains a Python-based simulation of an event listener component for a cross-chain bridge. It is designed as an architectural blueprint, demonstrating how to build a resilient and modular service for monitoring and reacting to on-chain events in a decentralized system.

## Concept

A cross-chain bridge enables the transfer of assets or data between two different blockchains. The process typically involves a user locking assets in a smart contract on the source chain, which emits an event. A network of off-chain listeners (or "relayers") detects this event, validates it, and then initiates a corresponding action on the destination chain, such as minting a wrapped version of the asset for the user.

This script simulates the core logic of such a listener. It monitors a "bridge" smart contract on a source chain for `DepositInitiated` events. Upon detection, it simulates calling a relayer service to process the transfer and then watches for a corresponding `TransferCompleted` event on the destination chain to finalize the transaction's state.

## Code Architecture

The script is designed with a modular, object-oriented approach to separate concerns and enhance maintainability. The main components are:

-   **`BlockchainConnector`**: A dedicated class for managing the connection to a single blockchain node via its RPC endpoint. It handles connection logic, retries, and provides methods for fetching blocks and logs. The service instantiates two of these: one for the source chain and one for the destination chain.

-   **`BridgeContractEventHandler`**: This class understands the specific smart contract it's monitoring. It holds the contract's ABI and address and is responsible for decoding raw event logs into structured, human-readable data.

-   **`CrossChainTransactionManager`**: The state machine of the service. It manages the lifecycle of each cross-chain transaction, tracking its status (`PENDING`, `RELAYED`, `COMPLETED`, `FAILED`). In this simulation, state is managed in-memory, but the class is designed to be easily adaptable to a persistent database like Redis or PostgreSQL in a production environment.

-   **`EventListenerService`**: The main orchestrator. It initializes all other components, runs the primary polling loop, and coordinates the flow of data between the different parts of the system. It handles the logic for scanning block ranges, processing events, and managing the overall service lifecycle.

### Architectural Flow

```
+----------------+     +------------------------+     +----------------------------+
|  Source Chain  | --> |  BlockchainConnector   | --> |   EventListenerService     |
+----------------+     +------------------------+     | (Main Loop)                |
                                                    |                            |
                                                    |   +------------------------+ <--- Decodes Logs
                                                    |   | BridgeEventHandler     |
                                                    |   +------------------------+ 
                                                    |                            |
                                                    |   +------------------------+ <--- Manages State
                                                    |   | CrossChainTxManager    |
                                                    |   +------------------------+ 
                                                    +-------------+--------------+
                                                                  | Simulates action
                                                                  v
                                                         +--------------------+
                                                         | Relayer API (POST) |
                                                         +--------------------+
                                                                  |
                                                                  v
+--------------------+     +------------------------+     Processes completion
| Destination Chain  | <-- |  BlockchainConnector   | <---------------------------
+--------------------+     +------------------------+
```

## How it Works

1.  **Initialization**: The `EventListenerService` is instantiated. It creates connectors for both the source and destination chains using the RPC URLs provided in the `.env` file.

2.  **Polling the Source Chain**: The service enters a continuous loop. In each iteration, it checks the latest block number on the source chain.

3.  **Event Detection**: It queries for event logs between the last processed block and the latest block, specifically looking for the `DepositInitiated` event signature from the bridge contract.

4.  **Transaction Initiation**: If a `DepositInitiated` event is found, the `CrossChainTransactionManager` creates a new transaction record with the status `PENDING`.

5.  **Relayer Simulation**: The service then calls the `_simulate_relay_action` method. This function sends a `POST` request (using the `requests` library) to a mock relayer API endpoint with the transaction details. This simulates notifying an external system to process the transaction on the destination chain. The transaction status is updated to `RELAYED` upon a successful API call.

6.  **Polling the Destination Chain**: Concurrently, the service also polls the destination chain for `TransferCompleted` events.

7.  **Transaction Completion**: When a `TransferCompleted` event is detected, the service finds the corresponding `RELAYED` transaction in the `CrossChainTransactionManager` and updates its status to `COMPLETED`.

8.  **Error Handling**: The system includes handling for RPC connection errors, API call failures, and provides continuous logging for visibility into its operations. A `KeyboardInterrupt` (Ctrl+C) will trigger a graceful shutdown.

## Usage Example

### 1. Prerequisites
-   Python 3.8+
-   `pip` package installer

### 2. Setup

Clone the repository:
```bash
git clone https://github.com/your-username/project-seed.git
cd project-seed
```

Install the required Python libraries:
```bash
pip install -r requirements.txt
```

Create a `.env` file in the root of the project directory by copying the example:
```bash
# .env file
# RPC URLs for the chains you want to monitor (e.g., from Infura, Alchemy, or a local node)
SOURCE_CHAIN_RPC_URL="https://eth-sepolia.g.alchemy.com/v2/YOUR_ALCHEMY_API_KEY"
DESTINATION_CHAIN_RPC_URL="https://polygon-mumbai.g.alchemy.com/v2/YOUR_ALCHEMY_API_KEY"

# Bridge contract addresses on each chain
SOURCE_BRIDGE_CONTRACT_ADDRESS="0x..."
DESTINATION_BRIDGE_CONTRACT_ADDRESS="0x..."

# A mock API endpoint for the relayer simulation (you can use a service like Beeceptor)
RELAYER_API_ENDPOINT="https://your-mock-api.free.beeceptor.com/relay"

# Polling interval in seconds
POLL_INTERVAL=15
```

**Note**: You will need to replace the placeholder values with actual RPC endpoints and contract addresses. For simulation purposes, the contract addresses can be any valid address, but no events will be found unless they actually exist and emit the expected events.

### 3. Running the Script

Execute the script from your terminal:
```bash
python script.py
```

The service will start, and you will see log output in your console.

### Example Output

```
2023-10-27 14:30:00 - INFO - [CrossChainBridgeListener] - Successfully connected to SourceChain. Chain ID: 11155111
2023-10-27 14:30:01 - INFO - [CrossChainBridgeListener] - Successfully connected to DestinationChain. Chain ID: 80001
2023-10-27 14:30:01 - INFO - [CrossChainBridgeListener] - CrossChainTransactionManager initialized (in-memory). Note: State will be lost on exit.
2023-10-27 14:30:01 - INFO - [CrossChainBridgeListener] - Starting cross-chain event listener service...
2023-10-27 14:30:02 - INFO - [CrossChainBridgeListener] - Scanning source chain blocks from 480100 to 480102...
2023-10-27 14:30:04 - INFO - [CrossChainBridgeListener] - Detected DepositInitiated event in tx 0x123abc...
2023-10-27 14:30:04 - INFO - [CrossChainBridgeListener] - New transaction initiated [ID: a1b2c3d4] from source tx 0x123abc...
2023-10-27 14:30:04 - INFO - [CrossChainBridgeListener] - Relaying transaction a1b2c3d4 to destination chain...
2023-10-27 14:30:05 - INFO - [CrossChainBridgeListener] - Successfully relayed transaction a1b2c3d4. Relayer response: {'status': 'received'}
2023-10-27 14:30:05 - INFO - [CrossChainBridgeListener] - Transaction [ID: a1b2c3d4] status updated to RELAYED
2023-10-27 14:30:05 - INFO - [CrossChainBridgeListener] - Scanning destination chain blocks from 950230 to 950231...
...
```