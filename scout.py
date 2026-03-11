"""
Scout Module for OpenClaw Arkham Intel Agent
=============================================
Monitors Arkham API for new bounty targets.
Designed for continuous operation with retry logic.
"""

import logging
import time
import random
from typing import List, Dict, Any, Optional
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration constants
MIN_REWARD_THRESHOLD = 500.0  # Minimum reward in USD to consider
API_TIMEOUT = 30  # seconds
MAX_RETRIES = 5
RETRY_DELAY_BASE = 5  # Base delay in seconds (exponential backoff)

# Arkham API endpoints (simulated - replace with actual endpoints)
ARKHAM_API_BASE = "https://api.arkhamintelligence.com"
BOUNTIES_ENDPOINT = f"{ARKHAM_API_BASE}/bounties"


class ArkhamScout:
    """
    Scout class for monitoring Arkham bounty board.
    Implements resilient API polling with retry logic.
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        min_reward: float = MIN_REWARD_THRESHOLD
    ):
        """
        Initialize the scout.
        
        Args:
            api_key: Optional API key for authentication
            min_reward: Minimum reward threshold to filter targets
        """
        self.api_key = api_key
        self.min_reward = min_reward
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'OpenClaw-Arkham-Agent/1.0',
            'Accept': 'application/json'
        })
        if api_key:
            self.session.headers['Authorization'] = f'Bearer {api_key}'
        
        logger.info(f"Scout initialized with min_reward threshold: ${min_reward}")
    
    def _make_request_with_retry(
        self, 
        url: str, 
        params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Make HTTP GET request with exponential backoff retry logic.
        Handles network interruptions and timeouts gracefully.
        
        Args:
            url: Target URL
            params: Query parameters
            
        Returns:
            JSON response dict or None if all retries failed
        """
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(
                    url, 
                    params=params, 
                    timeout=API_TIMEOUT
                )
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.Timeout:
                logger.warning(
                    f"Request timeout (attempt {attempt + 1}/{MAX_RETRIES}): {url}"
                )
                
            except requests.exceptions.ConnectionError as e:
                logger.warning(
                    f"Connection error (attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else 'unknown'
                logger.warning(
                    f"HTTP error {status_code} (attempt {attempt + 1}/{MAX_RETRIES}): {url}"
                )
                
                # Don't retry on 4xx client errors (except 429 rate limit)
                if e.response and 400 <= status_code < 500 and status_code != 429:
                    logger.error(f"Client error, not retrying: {status_code}")
                    return None
                    
            except Exception as e:
                logger.error(
                    f"Unexpected error (attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                )
            
            # Calculate exponential backoff delay
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt) + random.uniform(0, 1)
                logger.info(f"Retrying in {delay:.1f} seconds...")
                time.sleep(delay)
        
        logger.error(f"All retries exhausted for: {url}")
        return None
    
    def fetch_bounties_from_api(self) -> List[Dict[str, Any]]:
        """
        Fetch active bounties from Arkham API.
        
        Returns:
            List of bounty dictionaries
        """
        logger.info("Fetching bounties from Arkham API...")
        
        response = self._make_request_with_retry(BOUNTIES_ENDPOINT)
        
        if response and 'bounties' in response:
            bounties = response['bounties']
            logger.info(f"Fetched {len(bounties)} total bounties")
            return bounties
        
        logger.warning("No bounties received from API")
        return []
    
    def simulate_api_response(self) -> List[Dict[str, Any]]:
        """
        Simulate API response for testing/demo purposes.
        Returns mock bounty data that mimics real Arkham responses.
        
        Returns:
            List of simulated bounty dictionaries
        """
        logger.info("Generating simulated bounty data...")
        
        # Simulated bounty targets with realistic data
        simulated_bounties = [
            {
                "id": "ark_bounty_001",
                "address": "0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
                "network": "ethereum",
                "reward_usd": 2500.00,
                "title": "Unknown wallet connected to North Korean Lazarus Group",
                "description": "Large scale theft from DeFi protocol",
                "created_at": "2026-03-11T08:00:00Z",
                "category": "hack"
            },
            {
                "id": "ark_bounty_002",
                "address": "0x9876543210FEDCBA9876543210FEDCBA98765432",
                "network": "ethereum",
                "reward_usd": 1500.00,
                "title": "Mixer output wallet investigation",
                "description": "Funds traced from Tornado Cash",
                "created_at": "2026-03-10T14:30:00Z",
                "category": "mixer"
            },
            {
                "id": "ark_bounty_003",
                "address": "0x5555666677778888999900001111222233334444",
                "network": "ethereum",
                "reward_usd": 5000.00,
                "title": "CEX bridge connection needed",
                "description": "Unknown entity with high volume CEX transfers",
                "created_at": "2026-03-09T12:00:00Z",
                "category": "unknown"
            },
            {
                "id": "ark_bounty_004",
                "address": "0x1111222233334444555566667777888899990000",
                "network": "polygon",
                "reward_usd": 750.00,
                "title": "Phishing campaign beneficiary",
                "description": "Wallet receiving funds from phishing attacks",
                "created_at": "2026-03-11T06:15:00Z",
                "category": "scam"
            },
            # Below threshold - should be filtered
            {
                "id": "ark_bounty_005",
                "address": "0xAAAA0000BBBB1111CCCC2222DDDD3333EEEE4444",
                "network": "ethereum",
                "reward_usd": 250.00,
                "title": "Small bounty - below threshold",
                "description": "This should be filtered out",
                "created_at": "2026-03-11T07:00:00Z",
                "category": "unknown"
            }
        ]
        
        logger.info(f"Generated {len(simulated_bounties)} simulated bounties")
        return simulated_bounties
    
    def filter_bounties(
        self, 
        bounties: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Filter bounties by reward threshold.
        
        Args:
            bounties: Raw list of bounties
            
        Returns:
            Filtered list of bounties above threshold
        """
        filtered = [
            b for b in bounties 
            if b.get('reward_usd', 0) >= self.min_reward
        ]
        
        logger.info(
            f"Filtered {len(filtered)} bounties "
            f"(min reward: ${self.min_reward})"
        )
        return filtered
    
    def find_new_bounties(
        self, 
        use_simulation: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Main method to find new bounty targets.
        
        Args:
            use_simulation: If True, use simulated data instead of real API
            
        Returns:
            List of new bounty targets worth investigating
        """
        try:
            if use_simulation:
                all_bounties = self.simulate_api_response()
            else:
                all_bounties = self.fetch_bounties_from_api()
            
            # Filter by minimum reward threshold
            valuable_bounties = self.filter_bounties(all_bounties)
            
            # Log found targets
            for bounty in valuable_bounties:
                logger.info(
                    f"Found target: {bounty['address'][:10]}... "
                    f"(reward: ${bounty['reward_usd']:.2f})"
                )
            
            return valuable_bounties
            
        except Exception as e:
            logger.error(f"Error in find_new_bounties: {e}")
            # Return empty list instead of raising - keeps main loop running
            return []


def find_new_bounties(
    min_reward: float = MIN_REWARD_THRESHOLD,
    use_simulation: bool = True
) -> List[Dict[str, Any]]:
    """
    Convenience function to find new bounties.
    Creates a scout instance and performs search.
    
    Args:
        min_reward: Minimum reward threshold
        use_simulation: Use simulated data if True
        
    Returns:
        List of bounty dictionaries with address and reward
    """
    scout = ArkhamScout(min_reward=min_reward)
    return scout.find_new_bounties(use_simulation=use_simulation)


if __name__ == "__main__":
    # Test the scout module
    print("Testing Arkham Scout Module...")
    print("=" * 50)
    
    # Find bounties using simulation
    bounties = find_new_bounties(use_simulation=True)
    
    print(f"\nFound {len(bounties)} bounties above $500 threshold:")
    print("-" * 50)
    
    for i, bounty in enumerate(bounties, 1):
        print(f"\n{i}. Address: {bounty['address']}")
        print(f"   Reward: ${bounty['reward_usd']:.2f}")
        print(f"   Title: {bounty['title']}")
        print(f"   Network: {bounty['network']}")
    
    print("\n" + "=" * 50)
    print("Scout test complete.")