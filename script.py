import os
import time
import json
import logging
import uuid
from enum import Enum
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
import requests
from web3 import Web3
from web3.types import LogReceipt

# --- Configuration & Setup ---

load_dotenv()

# Configure logging to provide detailed output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger('CrossChainBridgeListener')

# --- Enums and Data Structures ---

class TransactionStatus(Enum):
    """Represents the status of a cross-chain transaction."""
    PENDING = 'PENDING'         # Deposit detected on the source chain
    RELAYED = 'RELAYED'         # Transaction has been relayed to the destination chain
    COMPLETED = 'COMPLETED'     # Transfer confirmed on the destination chain
    FAILED = 'FAILED'           # An error occurred during the process

# --- Core Components ---

class BlockchainConnector:
    """Handles the connection to a single blockchain node via RPC."""

    def __init__(self, chain_name: str, rpc_url: str):
        """
        Initializes the connector.
        :param chain_name: A friendly name for the chain (e.g., 'SourceChain').
        :param rpc_url: The HTTP RPC endpoint URL for the blockchain node.
        """
        self.chain_name = chain_name
        self.rpc_url = rpc_url
        self.web3 = None
        self.connect()

    def connect(self):
        """Establishes a connection to the blockchain node."""
        try:
            self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if not self.web3.is_connected():
                raise ConnectionError(f"Failed to connect to {self.chain_name} at {self.rpc_url}")
            logger.info(f"Successfully connected to {self.chain_name}. Chain ID: {self.web3.eth.chain_id}")
        except Exception as e:
            logger.error(f"Error connecting to {self.chain_name}: {e}")
            self.web3 = None

    def is_connected(self) -> bool:
        """Checks if the connection is active."""
        return self.web3 is not None and self.web3.is_connected()

    def get_latest_block_number(self) -> int:
        """
        Fetches the latest block number from the blockchain.
        Returns -1 if not connected.
        """
        if not self.is_connected():
            logger.warning(f"Cannot get latest block number, not connected to {self.chain_name}.")
            return -1
        try:
            return self.web3.eth.block_number
        except Exception as e:
            logger.error(f"Error fetching latest block number from {self.chain_name}: {e}")
            return -1

    def get_logs(self, from_block: int, to_block: int, address: str, topics: List[str]) -> Optional[List[LogReceipt]]:
        """
        Fetches event logs within a specific block range for a given contract address.
        """
        if not self.is_connected():
            logger.warning(f"Cannot get logs, not connected to {self.chain_name}.")
            return None
        try:
            filter_params = {
                'fromBlock': from_block,
                'toBlock': to_block,
                'address': address,
                'topics': topics
            }
            return self.web3.eth.get_logs(filter_params)
        except Exception as e:
            logger.error(f"Error fetching logs from {self.chain_name} between blocks {from_block}-{to_block}: {e}")
            return None

class BridgeContractEventHandler:
    """Decodes and interprets events from a specific bridge smart contract."""

    def __init__(self, web3_instance: Web3, contract_address: str, contract_abi: List[Dict[str, Any]]):
        """
        Initializes the event handler.
        :param web3_instance: An active Web3 instance.
        :param contract_address: The address of the bridge contract to monitor.
        :param contract_abi: The ABI of the bridge contract.
        """
        self.web3 = web3_instance
        self.contract = self.web3.eth.contract(address=contract_address, abi=contract_abi)

    def decode_log(self, log: LogReceipt) -> Optional[Dict[str, Any]]:
        """Decodes a raw log into a structured event. Returns None if decoding fails."""
        try:
            # This is a simplified approach. A production system would iterate through known event ABIs.
            if log['topics'][0].hex() == Web3.keccak(text="DepositInitiated(address,address,uint256,uint256)").hex():
                return self.contract.events.DepositInitiated().process_log(log)
            elif log['topics'][0].hex() == Web3.keccak(text="TransferCompleted(bytes32,address,uint256)").hex():
                return self.contract.events.TransferCompleted().process_log(log)
        except Exception as e:
            logger.error(f"Failed to decode log {log['transactionHash'].hex()}: {e}")
        return None

class CrossChainTransactionManager:
    """Manages the state of cross-chain transactions in-memory."""

    def __init__(self):
        """
        Initializes the transaction manager.
        NOTE: In a production environment, this would be a persistent database (e.g., Redis, PostgreSQL)
        to ensure state is not lost on restart.
        """
        self.transactions: Dict[str, Dict[str, Any]] = {}
        logger.info("CrossChainTransactionManager initialized (in-memory). Note: State will be lost on exit.")

    def initiate_transaction(self, event_data: Dict[str, Any]) -> str:
        """
        Creates a new transaction record from a DepositInitiated event.
        Returns the unique transaction ID.
        """
        tx_id = uuid.uuid4().hex
        self.transactions[tx_id] = {
            'id': tx_id,
            'status': TransactionStatus.PENDING,
            'source_tx_hash': event_data['transactionHash'].hex(),
            'details': event_data['args'],
            'created_at': time.time(),
            'updated_at': time.time()
        }
        logger.info(f"New transaction initiated [ID: {tx_id}] from source tx {event_data['transactionHash'].hex()}")
        return tx_id

    def update_transaction_status(self, tx_id: str, new_status: TransactionStatus, details: Dict = None):
        """Updates the status and details of an existing transaction."""
        if tx_id in self.transactions:
            self.transactions[tx_id]['status'] = new_status
            self.transactions[tx_id]['updated_at'] = time.time()
            if details:
                self.transactions[tx_id].update(details)
            logger.info(f"Transaction [ID: {tx_id}] status updated to {new_status.value}")
        else:
            logger.warning(f"Attempted to update non-existent transaction [ID: {tx_id}]")

    def get_transactions_by_status(self, status: TransactionStatus) -> List[Dict[str, Any]]:
        """Retrieves all transactions with a given status."""
        return [tx for tx in self.transactions.values() if tx['status'] == status]

class EventListenerService:
    """Orchestrates the entire process of listening for and processing bridge events."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.source_connector = BlockchainConnector('SourceChain', config['source_chain']['rpc_url'])
        self.dest_connector = BlockchainConnector('DestinationChain', config['destination_chain']['rpc_url'])
        self.tx_manager = CrossChainTransactionManager()

        if self.source_connector.is_connected():
            self.source_handler = BridgeContractEventHandler(
                self.source_connector.web3,
                config['source_chain']['contract_address'],
                config['bridge_contract_abi']
            )

        if self.dest_connector.is_connected():
            self.dest_handler = BridgeContractEventHandler(
                self.dest_connector.web3,
                config['destination_chain']['contract_address'],
                config['bridge_contract_abi']
            )
        
        self.last_processed_source_block = config.get('start_block_source', self.source_connector.get_latest_block_number())
        self.last_processed_dest_block = config.get('start_block_dest', self.dest_connector.get_latest_block_number())
        self.running = True

    def _process_source_chain_events(self):
        """Polls the source chain for new `DepositInitiated` events."""
        if not self.source_connector.is_connected():
            logger.warning("Source chain disconnected. Attempting to reconnect...")
            self.source_connector.connect()
            return

        latest_block = self.source_connector.get_latest_block_number()
        if latest_block <= self.last_processed_source_block:
            return

        to_block = latest_block
        from_block = self.last_processed_source_block + 1
        logger.info(f"Scanning source chain blocks from {from_block} to {to_block}...")

        deposit_event_topic = self.source_connector.web3.keccak(text="DepositInitiated(address,address,uint256,uint256)").hex()
        logs = self.source_connector.get_logs(
            from_block, to_block, self.config['source_chain']['contract_address'], [deposit_event_topic]
        )

        if logs:
            for log in logs:
                decoded_log = self.source_handler.decode_log(log)
                if decoded_log:
                    logger.info(f"Detected DepositInitiated event in tx {decoded_log['transactionHash'].hex()}")
                    tx_id = self.tx_manager.initiate_transaction(decoded_log)
                    self._simulate_relay_action(tx_id, decoded_log['args'])
        
        self.last_processed_source_block = to_block

    def _simulate_relay_action(self, tx_id: str, event_args: Dict):
        """
        Simulates calling a relayer service to execute the transaction on the destination chain.
        This uses the `requests` library to make an outbound API call.
        """
        logger.info(f"Relaying transaction {tx_id} to destination chain...")
        relayer_endpoint = self.config.get('relayer_api_endpoint')
        if not relayer_endpoint:
            logger.warning("RELAYER_API_ENDPOINT not configured. Skipping relay simulation.")
            self.tx_manager.update_transaction_status(tx_id, TransactionStatus.FAILED, {'error': 'Relayer not configured'})
            return

        payload = {
            'source_tx_id': tx_id,
            'recipient': event_args['to'],
            'amount': event_args['amount'],
            'source_chain_id': event_args['sourceChainId']
        }

        try:
            # In a real scenario, this would trigger an off-chain relayer to sign and send a transaction
            response = requests.post(relayer_endpoint, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"Successfully relayed transaction {tx_id}. Relayer response: {response.json()}")
                self.tx_manager.update_transaction_status(tx_id, TransactionStatus.RELAYED)
            else:
                logger.error(f"Relayer API failed for tx {tx_id}. Status: {response.status_code}, Body: {response.text}")
                self.tx_manager.update_transaction_status(tx_id, TransactionStatus.FAILED, {'error': 'Relayer API Error'})
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to call relayer API for tx {tx_id}: {e}")
            self.tx_manager.update_transaction_status(tx_id, TransactionStatus.FAILED, {'error': 'Relayer network error'})

    def _process_destination_chain_events(self):
        """Polls the destination chain for `TransferCompleted` events to confirm transactions."""
        if not self.dest_connector.is_connected():
            logger.warning("Destination chain disconnected. Attempting to reconnect...")
            self.dest_connector.connect()
            return

        latest_block = self.dest_connector.get_latest_block_number()
        if latest_block <= self.last_processed_dest_block:
            return

        to_block = latest_block
        from_block = self.last_processed_dest_block + 1
        logger.info(f"Scanning destination chain blocks from {from_block} to {to_block}...")

        transfer_event_topic = self.dest_connector.web3.keccak(text="TransferCompleted(bytes32,address,uint256)").hex()
        logs = self.dest_connector.get_logs(
            from_block, to_block, self.config['destination_chain']['contract_address'], [transfer_event_topic]
        )

        if logs:
            relayed_txs = self.tx_manager.get_transactions_by_status(TransactionStatus.RELAYED)
            if not relayed_txs:
                return

            # This is inefficient. A production system would map source tx hash to destination tx hash.
            for log in logs:
                decoded_log = self.dest_handler.decode_log(log)
                if decoded_log:
                    # Here we would have logic to correlate the completion event with a relayed transaction.
                    # For this simulation, we'll just complete the oldest relayed transaction.
                    tx_to_complete = relayed_txs[0]
                    logger.info(f"Detected TransferCompleted event. Marking tx {tx_to_complete['id']} as COMPLETED.")
                    self.tx_manager.update_transaction_status(tx_to_complete['id'], TransactionStatus.COMPLETED, {'dest_tx_hash': decoded_log['transactionHash'].hex()})
                    relayed_txs.pop(0) # Remove from list to avoid double-processing
        
        self.last_processed_dest_block = to_block

    def run(self):
        """Starts the main event listening loop."""
        logger.info("Starting cross-chain event listener service...")
        while self.running:
            try:
                self._process_source_chain_events()
                self._process_destination_chain_events()
                time.sleep(self.config.get('poll_interval', 15))
            except KeyboardInterrupt:
                logger.info("Shutdown signal received. Stopping listener service...")
                self.running = False
            except Exception as e:
                logger.critical(f"An unhandled error occurred in the main loop: {e}", exc_info=True)
                time.sleep(60) # Wait longer after a critical error

# --- Main Execution ---

def main():
    """Main function to set up and run the service."""
    # A simplified ABI for the bridge contract. Real ABIs are much larger.
    BRIDGE_ABI = json.loads('''
    [
        {"type":"event","name":"DepositInitiated","inputs":[{"name":"from","type":"address","indexed":true},{"name":"to","type":"address","indexed":true},{"name":"amount","type":"uint256","indexed":false},{"name":"sourceChainId","type":"uint256","indexed":false}],"anonymous":false},
        {"type":"event","name":"TransferCompleted","inputs":[{"name":"sourceTxHash","type":"bytes32","indexed":true},{"name":"recipient","type":"address","indexed":true},{"name":"amount","type":"uint256","indexed":false}],"anonymous":false}
    ]
    ''')

    # Configuration is loaded from environment variables for security and flexibility.
    # In a real app, use a proper config management library.
    config = {
        'source_chain': {
            'rpc_url': os.getenv('SOURCE_CHAIN_RPC_URL'),
            'contract_address': Web3.to_checksum_address(os.getenv('SOURCE_BRIDGE_CONTRACT_ADDRESS', '0x0000000000000000000000000000000000000001'))
        },
        'destination_chain': {
            'rpc_url': os.getenv('DESTINATION_CHAIN_RPC_URL'),
            'contract_address': Web3.to_checksum_address(os.getenv('DESTINATION_BRIDGE_CONTRACT_ADDRESS', '0x0000000000000000000000000000000000000002'))
        },
        'bridge_contract_abi': BRIDGE_ABI,
        'relayer_api_endpoint': os.getenv('RELAYER_API_ENDPOINT', 'https://api.example.com/relay'),
        'poll_interval': int(os.getenv('POLL_INTERVAL', '15')),
    }

    if not config['source_chain']['rpc_url'] or not config['destination_chain']['rpc_url']:
        logger.error("RPC URLs for source and destination chains must be set in the .env file.")
        return

    service = EventListenerService(config)
    service.run()

if __name__ == '__main__':
    main()
