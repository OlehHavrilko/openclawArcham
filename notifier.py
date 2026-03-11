"""
Notifier Module for OpenClaw Arkham Intel Agent
================================================
Handles Telegram notifications for alerts and status updates.
Implements retry logic for reliable message delivery.
"""

import logging
import time
from typing import Optional
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_DELAY_BASE = 3
TELEGRAM_TIMEOUT = 30


class TelegramNotifier:
    """Telegram notification handler with retry logic."""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.session = requests.Session()
        logger.info("Telegram notifier initialized")
    
    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send message via Telegram Bot API with retry logic."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
                response.raise_for_status()
                result = response.json()
                
                if result.get("ok"):
                    logger.info("Telegram message sent successfully")
                    return True
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Telegram timeout (attempt {attempt + 1}/{MAX_RETRIES})")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Telegram connection error: {e}")
            except requests.exceptions.HTTPError as e:
                logger.error(f"Telegram HTTP error: {e.response.status_code}")
                if e.response.status_code == 401:
                    logger.error("Invalid bot token")
                    return False
            except Exception as e:
                logger.error(f"Telegram error: {e}")
            
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                time.sleep(delay)
        
        logger.error("Failed to send Telegram message after retries")
        return False


def send_telegram_message(text: str, bot_token: str, chat_id: str) -> bool:
    """Convenience function for sending Telegram messages."""
    notifier = TelegramNotifier(bot_token, chat_id)
    return notifier.send_message(text)


def format_target_alert(address: str, reward: float, title: str) -> str:
    """Format target discovery alert message."""
    return f"""🎯 *NEW BOUNTY TARGET FOUND*

📍 Address: `{address[:20]}...`
💰 Reward: ${reward:,.2f}
📝 Title: {title}

⏰ Agent is starting investigation..."""


def format_submission_alert(address: str, ipfs_cid: str, tx_hash: str) -> str:
    """Format successful submission alert message."""
    return f"""✅ *REPORT SUBMITTED*

📍 Target: `{address[:20]}...`
📄 IPFS: `{ipfs_cid}`
🔗 TX: `{tx_hash}`

🎉 Bounty claim submitted!"""


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat = os.getenv('TELEGRAM_CHAT_ID')
    
    if token and chat:
        msg = format_target_alert("0xABCDEF...", 2500.0, "Test Target")
        print(send_telegram_message(msg, token, chat))
    else:
        print("Telegram credentials not configured")