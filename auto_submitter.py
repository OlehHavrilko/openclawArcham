"""
Auto Submitter Module for OpenClaw Arkham Intel Agent
======================================================
Handles IPFS upload via Pinata and blockchain submission.
Designed for resilient operation with comprehensive retry logic.
"""

import logging
import time
import json
from typing import Optional, Dict, Any
from datetime import datetime

import requests
from web3 import Web3
from web3.exceptions import TransactionNotFound, TimeExhausted

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration constants
MAX_RETRIES = 5
RETRY_DELAY_BASE = 5
PINATA_API_TIMEOUT = 60
RPC_TIMEOUT = 120
TX_TIMEOUT = 600  # 10 minutes for transaction confirmation

# Pinata API endpoints
PINATA_API_URL = "https://api.pinata.cloud"
PINATA_PIN_ENDPOINT = f"{PINATA_API_URL}/pinning/pinJSONToIPFS"


class PinataUploader:
    """
    Handles uploading reports to IPFS via Pinata API.
    Implements robust retry logic for network resilience.
    """
    
    def __init__(self, api_key: str, secret_key: str):
        """
        Initialize Pinata uploader with credentials.
        
        Args:
            api_key: Pinata API key
            secret_key: Pinata API secret
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.session = requests.Session()
        self.session.headers.update({
            'pinata_api_key': api_key,
            'pinata_secret_api_key': secret_key,
            'Content-Type': 'application/json'
        })
        
        logger.info("Pinata uploader initialized")
    
    def upload_to_ipfs(
        self, 
        content: str, 
        filename: str = "investigation_report.md"
    ) -> Optional[str]:
        """
        Upload content to IPFS via Pinata REST API.
        
        Handles network interruptions with exponential backoff retry.
        
        Args:
            content: Content to upload (Markdown string)
            filename: Name for the uploaded file
            
        Returns:
            IPFS CID (Content Identifier) or None on failure
        """
        if not content:
            logger.error("No content provided for upload")
            return None
        
        # Prepare metadata
        metadata = {
            "name": f"arkham_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            "keyvalues": {
                "filename": filename,
                "type": "investigation_report",
                "agent": "openclaw_arkham",
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        payload = {
            "pinataContent": {
                "content": content,
                "filename": filename,
                "uploaded_at": datetime.utcnow().isoformat()
            },
            "pinataMetadata": metadata
        }
        
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Uploading to IPFS via Pinata (attempt {attempt + 1})...")
                
                response = self.session.post(
                    PINATA_PIN_ENDPOINT,
                    json=payload,
                    timeout=PINATA_API_TIMEOUT
                )
                response.raise_for_status()
                
                result = response.json()
                
                if 'IpfsHash' in result:
                    cid = result['IpfsHash']
                    logger.info(f"IPFS upload successful. CID: {cid}")
                    return cid
                else:
                    logger.warning(f"Unexpected Pinata response: {result}")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Pinata API timeout (attempt {attempt + 1}/{MAX_RETRIES})")
                
            except requests.exceptions.ConnectionError as e:
                logger.warning(
                    f"Pinata connection error (attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                logger.info("Network issue detected - Wi-Fi may be unstable")
                
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else 'unknown'
                logger.error(f"Pinata HTTP error {status_code}")
                
                # Don't retry on authentication errors
                if status_code in [401, 403]:
                    logger.error("Pinata authentication failed - check API keys")
                    return None
                    
            except Exception as e:
                logger.error(f"Pinata upload error (attempt {attempt + 1}): {e}")
            
            # Exponential backoff before retry
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logger.info(f"Retrying Pinata upload in {delay}s...")
                time.sleep(delay)
        
        logger.error("IPFS upload failed after all retries")
        return None
    
    def test_connection(self) -> bool:
        """
        Test Pinata API connection.
        
        Returns:
            True if connection successful
        """
        test_endpoint = f"{PINATA_API_URL}/data/testAuthentication"
        
        try:
            response = self.session.get(test_endpoint, timeout=30)
            response.raise_for_status()
            logger.info("Pinata API connection: OK")
            return True
        except Exception as e:
            logger.error(f"Pinata API connection failed: {e}")
            return False


class BlockchainSubmitter:
    """
    Handles blockchain transaction submission.
    Signs and submits transactions to smart contract.
    """
    
    def __init__(
        self, 
        rpc_url: str, 
        private_key: str,
        contract_address: str,
        chain_id: int = 1  # Ethereum mainnet
    ):
        """
        Initialize blockchain submitter.
        
        Args:
            rpc_url: Web3 RPC endpoint
            private_key: Wallet private key for signing
            contract_address: Target smart contract address
            chain_id: Blockchain chain ID (default: 1 for mainnet)
        """
        self.rpc_url = rpc_url
        self.private_key = private_key
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.chain_id = chain_id
        self.w3: Optional[Web3] = None
        self.account_address: Optional[str] = None
        
        self._connect()
        
        logger.info(f"Blockchain submitter initialized for contract: {contract_address[:10]}...")
    
    def _connect(self) -> bool:
        """
        Connect to Web3 provider with retry logic.
        
        Returns:
            True if connected successfully
        """
        for attempt in range(MAX_RETRIES):
            try:
                self.w3 = Web3(
                    Web3.HTTPProvider(
                        self.rpc_url,
                        request_kwargs={'timeout': RPC_TIMEOUT}
                    )
                )
                
                if self.w3.is_connected():
                    # Get account address from private key
                    self.account_address = self.w3.eth.account.from_key(
                        self.private_key
                    ).address
                    
                    balance = self.w3.eth.get_balance(self.account_address)
                    balance_eth = float(self.w3.from_wei(balance, 'ether'))
                    
                    logger.info(
                        f"Web3 connected. Account: {self.account_address[:10]}... "
                        f"(Balance: {balance_eth:.4f} ETH)"
                    )
                    return True
                    
            except Exception as e:
                logger.error(f"Web3 connection error (attempt {attempt + 1}): {e}")
            
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logger.info(f"Retrying Web3 connection in {delay}s...")
                time.sleep(delay)
        
        logger.error("Failed to connect to Web3 after all retries")
        return False
    
    def _ensure_connection(self) -> bool:
        """
        Ensure Web3 connection is active.
        
        Returns:
            True if connected
        """
        try:
            if self.w3 and self.w3.is_connected():
                return True
        except:
            pass
        
        logger.warning("Web3 connection lost, reconnecting...")
        return self._connect()
    
    def submit_report(
        self, 
        ipfs_cid: str,
        target_address: str,
        gas_limit: int = 200000,
        max_fee_per_gas: Optional[int] = None,
        max_priority_fee_per_gas: Optional[int] = None
    ) -> Optional[str]:
        """
        Submit report to blockchain smart contract.
        
        Signs and broadcasts transaction with the IPFS CID.
        
        Args:
            ipfs_cid: IPFS content identifier for the report
            target_address: Address being reported
            gas_limit: Gas limit for the transaction
            max_fee_per_gas: Maximum total fee per gas (in wei)
            max_priority_fee_per_gas: Priority fee per gas (in wei)
            
        Returns:
            Transaction hash or None on failure
        """
        if not self._ensure_connection():
            logger.error("Cannot submit: Web3 not connected")
            return None
        
        try:
            # Get nonce for account
            nonce = self.w3.eth.get_transaction_count(self.account_address)
            
            # Build transaction
            # This is a generic submission - actual ABI depends on the contract
            # Assuming a simple function: submitReport(address target, string ipfsCid)
            
            # Convert IPFS CID to bytes32 if needed (first 32 bytes of CID)
            cid_bytes = ipfs_cid.encode('utf-8')[:32].ljust(32, b'\0')
            
            # Encode function call (placeholder - actual encoding depends on contract ABI)
            # For demonstration, we'll send ETH with data
            tx_data = {
                'nonce': nonce,
                'to': self.contract_address,
                'value': 0,  # No ETH transfer
                'gas': gas_limit,
                'data': self.w3.keccak(text='submitReport')[:4] + 
                        Web3.to_checksum_address(target_address).encode('utf-8').ljust(32, b'\0') +
                        cid_bytes,
                'chainId': self.chain_id
            }
            
            # EIP-1559 transaction
            if max_fee_per_gas is None or max_priority_fee_per_gas is None:
                # Get current gas prices
                latest_block = self.w3.eth.get_block('latest')
                base_fee = latest_block['baseFeePerGas']
                
                if max_priority_fee_per_gas is None:
                    max_priority_fee_per_gas = self.w3.to_wei(1, 'gwei')
                
                if max_fee_per_gas is None:
                    max_fee_per_gas = base_fee * 2 + max_priority_fee_per_gas
                
                tx_data['maxFeePerGas'] = max_fee_per_gas
                tx_data['maxPriorityFeePerGas'] = max_priority_fee_per_gas
                tx_data['type'] = 0x2  # EIP-1559 transaction
            else:
                tx_data['maxFeePerGas'] = max_fee_per_gas
                tx_data['maxPriorityFeePerGas'] = max_priority_fee_per_gas
                tx_data['type'] = 0x2
            
            # Sign transaction
            signed_tx = self.w3.eth.account.sign_transaction(tx_data, self.private_key)
            
            logger.info(f"Broadcasting transaction...")
            
            # Broadcast transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            tx_hash_hex = tx_hash.hex()
            
            logger.info(f"Transaction broadcast: {tx_hash_hex}")
            
            # Wait for confirmation
            try:
                receipt = self.w3.eth.wait_for_transaction_receipt(
                    tx_hash, 
                    timeout=TX_TIMEOUT
                )
                
                if receipt['status'] == 1:
                    logger.info(f"Transaction confirmed! Block: {receipt['blockNumber']}")
                    return tx_hash_hex
                else:
                    logger.error(f"Transaction reverted in block {receipt['blockNumber']}")
                    return None
                    
            except TimeExhausted:
                logger.warning("Transaction pending but not confirmed yet")
                return tx_hash_hex  # Return hash anyway - can check later
                
        except Exception as e:
            logger.error(f"Transaction submission error: {e}")
            return None
    
    def get_balance(self) -> float:
        """
        Get current account balance in ETH.
        
        Returns:
            Balance in ETH
        """
        if not self._ensure_connection():
            return 0.0
        
        try:
            balance_wei = self.w3.eth.get_balance(self.account_address)
            return float(self.w3.from_wei(balance_wei, 'ether'))
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.0


def upload_report_to_ipfs(
    content: str, 
    api_key: str, 
    secret_key: str,
    filename: str = "investigation_report.md"
) -> Optional[str]:
    """
    Convenience function to upload report to IPFS.
    
    Args:
        content: Report content
        api_key: Pinata API key
        secret_key: Pinata API secret
        filename: Name for uploaded file
        
    Returns:
        IPFS CID or None
    """
    uploader = PinataUploader(api_key, secret_key)
    return uploader.upload_to_ipfs(content, filename)


def submit_to_blockchain(
    ipfs_cid: str,
    target_address: str,
    rpc_url: str,
    private_key: str,
    contract_address: str,
    chain_id: int = 1
) -> Optional[str]:
    """
    Convenience function to submit report to blockchain.
    
    Args:
        ipfs_cid: IPFS content identifier
        target_address: Address being reported
        rpc_url: Web3 RPC endpoint
        private_key: Wallet private key
        contract_address: Smart contract address
        chain_id: Blockchain chain ID
        
    Returns:
        Transaction hash or None
    """
    submitter = BlockchainSubmitter(
        rpc_url, private_key, contract_address, chain_id
    )
    return submitter.submit_report(ipfs_cid, target_address)


if __name__ == "__main__":
    # Test auto_submitter module
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    print("Testing Auto Submitter Module...")
    print("=" * 50)
    
    # Test Pinata connection
    pinata_key = os.getenv('PINATA_API_KEY')
    pinata_secret = os.getenv('PINATA_SECRET_KEY')
    
    if pinata_key and pinata_secret:
        print("\nTesting Pinata connection...")
        uploader = PinataUploader(pinata_key, pinata_secret)
        
        if uploader.test_connection():
            print("Pinata connection: OK")
            
            # Test upload
            test_content = "# Test Report\n\nThis is a test report from OpenClaw."
            print("\nUploading test content...")
            cid = uploader.upload_to_ipfs(test_content, "test_report.md")
            print(f"Test CID: {cid}" if cid else "Upload failed")
    else:
        print("Pinata credentials not configured - skipping upload test")
    
    # Test Web3 connection
    rpc_url = os.getenv('WEB3_RPC_URL')
    private_key = os.getenv('WORKER_WALLET_PRIVATE_KEY')
    contract_address = os.getenv('ARKHAM_CONTRACT_ADDRESS')
    
    if rpc_url and private_key and contract_address:
        print("\n" + "-" * 50)
        print("Testing Web3 connection...")
        
        try:
            submitter = BlockchainSubmitter(rpc_url, private_key, contract_address)
            balance = submitter.get_balance()
            print(f"Account balance: {balance:.4f} ETH")
        except Exception as e:
            print(f"Web3 test error: {e}")
    else:
        print("Blockchain credentials not configured - skipping Web3 test")
    
    print("\n" + "=" * 50)
    print("Auto submitter test complete.")