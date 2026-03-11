"""
Main Controller for OpenClaw Arkham Intel Agent
================================================
Autonomous blockchain bounty hunter system.
Designed for 12-13 hour continuous operation.
"""

import logging
import time
import sys
from datetime import datetime

from dotenv import load_dotenv
import os

from database import Database, init_database
from scout import Scout, find_new_bounties
from investigator import BlockchainInvestigator
from auto_submitter import PinataUploader, BlockchainSubmitter
from notifier import TelegramNotifier, format_target_alert, format_submission_alert

# Configure logging for long-running operation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('arkham_agent.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuration
CYCLE_DELAY = 3600  # 1 hour between cycles (normal operation)
ERROR_RETRY_DELAY = 60  # 1 minute retry after network errors


class ArkhamAgent:
    """Main autonomous agent controller."""
    
    def __init__(self):
        """Initialize agent with all components."""
        logger.info("=" * 60)
        logger.info("ARKHAM INTEL AGENT v1.0 - OpenClaw Autonomous Investigator")
        logger.info("=" * 60)
        
        # Load environment variables
        load_dotenv()
        
        self.rpc_url = os.getenv('WEB3_RPC_URL')
        self.pinata_key = os.getenv('PINATA_API_KEY')
        self.pinata_secret = os.getenv('PINATA_SECRET_KEY')
        self.tg_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.tg_chat = os.getenv('TELEGRAM_CHAT_ID')
        self.private_key = os.getenv('WORKER_WALLET_PRIVATE_KEY')
        self.contract_addr = os.getenv('ARKHAM_CONTRACT_ADDRESS')
        
        # Validate configuration
        self._validate_config()
        
        # Initialize components
        self.db = init_database()
        self.scout = Scout()
        self.investigator = BlockchainInvestigator(self.rpc_url) if self.rpc_url else None
        
        self.uploader = None
        if self.pinata_key and self.pinata_secret:
            self.uploader = PinataUploader(self.pinata_key, self.pinata_secret)
        
        self.submitter = None
        if all([self.rpc_url, self.private_key, self.contract_addr]):
            self.submitter = BlockchainSubmitter(
                self.rpc_url, self.private_key, self.contract_addr
            )
        
        self.notifier = None
        if self.tg_token and self.tg_chat:
            self.notifier = TelegramNotifier(self.tg_token, self.tg_chat)
        
        self.running = True
        self.cycle_count = 0
        
        logger.info("Agent initialized successfully")
    
    def _validate_config(self):
        """Validate required configuration."""
        required = ['WEB3_RPC_URL']
        for key in required:
            if not os.getenv(key):
                logger.error(f"Missing required config: {key}")
    
    def run_cycle(self):
        """Execute one investigation cycle."""
        self.cycle_count += 1
        logger.info(f"\n{'='*60}\nCYCLE #{self.cycle_count} - {datetime.utcnow().isoformat()}\n{'='*60}")
        
        # Step 1: Scout for new bounties
        logger.info("[1/5] Scouting for new bounty targets...")
        targets = self.scout.find_new_bounties()
        
        if not targets:
            logger.info("No new targets found this cycle")
            return
        
        logger.info(f"Found {len(targets)} potential target(s)")
        
        for target in targets:
            target_id = None  # Initialize BEFORE any operations for safe error handling
            address = target.get('address')
            reward = target.get('reward', 0)
            title = target.get('title', 'Unknown')
            
            try:
                # Check if already tracked
                existing = self.db.get_target_by_address(address)
                if existing:
                    logger.info(f"Target {address[:16]}... already tracked")
                    continue
                
                # Add to database
                self.db.add_target(address, reward, title)
                target_id = self.db.cursor.lastrowid
                
                # Send alert
                if self.notifier:
                    alert = format_target_alert(address, reward, title)
                    self.notifier.send_message(alert)
                
                # Step 2: Investigate
                logger.info(f"[2/5] Investigating {address[:16]}...")
                
                if not self.investigator:
                    logger.warning("Investigator not configured - skipping")
                    continue
                
                report, metadata = self.investigator.investigate(address)
                
                if not report:
                    logger.warning("Investigation produced no report")
                    self.db.update_status(target_id, 'failed')
                    continue
                
                # Step 3: Upload to IPFS
                logger.info("[3/5] Uploading report to IPFS...")
                
                if not self.uploader:
                    logger.warning("Uploader not configured - skipping")
                    self.db.update_status(target_id, 'investigated')
                    continue
                
                ipfs_cid = self.uploader.upload_to_ipfs(report)
                
                if not ipfs_cid:
                    logger.error("IPFS upload failed")
                    self.db.update_status(target_id, 'upload_failed')
                    continue
                
                logger.info(f"Report uploaded: {ipfs_cid}")
                
                # Step 4: Submit to blockchain
                logger.info("[4/5] Submitting to blockchain...")
                
                if not self.submitter:
                    logger.warning("Submitter not configured - skipping")
                    self.db.update_status(target_id, 'uploaded', ipfs_cid)
                    continue
                
                tx_hash = self.submitter.submit_report(ipfs_cid, address)
                
                if tx_hash:
                    self.db.update_status(target_id, 'submitted', tx_hash)
                    logger.info(f"Transaction: {tx_hash}")
                    
                    # Step 5: Notify
                    logger.info("[5/5] Sending notification...")
                    
                    if self.notifier:
                        alert = format_submission_alert(address, ipfs_cid, tx_hash)
                        self.notifier.send_message(alert)
                else:
                    self.db.update_status(target_id, 'tx_failed', ipfs_cid)
                    
            except Exception as e:
                logger.error(f"Investigation error for target {address}: {e}")
                if target_id is not None:
                    self.db.update_status(target_id, 'error')
    
    def run(self):
        """Main loop for continuous operation."""
        logger.info(f"Starting autonomous operation (cycle delay: {CYCLE_DELAY}s)")
        
        while self.running:
            try:
                self.run_cycle()
                if self.running:
                    logger.info(f"Cycle complete. Sleeping for {CYCLE_DELAY}s...")
                    time.sleep(CYCLE_DELAY)
            except KeyboardInterrupt:
                logger.info("Shutdown requested")
                self.running = False
                break
            except Exception as e:
                # Short sleep on network errors (e.g., WiFi disconnection)
                # Prevents losing a full hour due to momentary connectivity issues
                logger.error(f"Unexpected cycle error: {e}. Retrying in {ERROR_RETRY_DELAY}s...")
                time.sleep(ERROR_RETRY_DELAY)
        
        logger.info("Agent stopped")


def main():
    """Entry point."""
    agent = ArkhamAgent()
    agent.run()


if __name__ == "__main__":
    main()