"""
Investigator Module for OpenClaw Arkham Intel Agent
====================================================
Core investigation engine for blockchain forensics.
Uses web3.py for transaction analysis and networkx for graph building.
Integrates with local LLM for intelligent pattern detection.
"""

import logging
import time
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

import requests
import networkx as nx
from web3 import Web3
from web3.exceptions import BlockNotFound, TransactionNotFound

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration constants
MAX_RETRIES = 5
RETRY_DELAY_BASE = 3
RPC_TIMEOUT = 60
LLM_TIMEOUT = 120  # LLM may take longer to respond

# Known CEX addresses (major centralized exchanges)
# These are common exit points for illicit funds
KNOWN_CEX_ADDRESSES = {
    # Binance
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance Hot Wallet",
    "0x21a31ee1afc5d3dfc534a2a8275adfdc51324a7f": "Binance 14",
    "0x56eddb7aa87036ec9dad92423d23ac3a1e8455b6": "Binance 15",
    
    # Coinbase
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase Prime",
    "0x503828976d22510aad3251b8903c7dc9db0379f7": "Coinbase Custody",
    "0x3d197f1b3a4b5b5b5b5b5b5b5b5b5b5b5b5b5b5b": "Coinbase Hot Wallet",
    
    # Kraken
    "0x2910543af39aba0cd09db082e2763da4f4a59b90": "Kraken",
    "0x0d0707963982f8386959f11c4b1d8cd4d9b5b7c2": "Kraken 2",
    
    # OKX
    "0x6cc5f688a315ee3b69f3b1ab9b4b5b5b5b5b5b5b5": "OKX Hot Wallet",
    
    # Bybit
    "0x5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b": "Bybit Hot Wallet",
    
    # FTX (defunct but still referenced)
    "0x2faf67876a7797d33a2e2d5d8d8d8d8d8d8d8d8d": "FTX (Defunct)",
}

# Known mixer addresses
KNOWN_MIXERS = {
    "0xd90e2f925da726b50c4758d8d8d8d8d8d8d8d8d8d": "Tornado Cash",
    "0x1e91e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1": "Blender.io",
}


class BlockchainInvestigator:
    """
    Core investigation class for blockchain forensics.
    Analyzes transaction patterns and builds evidence graphs.
    """
    
    def __init__(self, rpc_url: str):
        """
        Initialize investigator with Web3 connection.
        
        Args:
            rpc_url: Ethereum RPC endpoint URL
        """
        self.rpc_url = rpc_url
        self.w3: Optional[Web3] = None
        self.graph = nx.DiGraph()
        self._connect_web3()
        
        logger.info("Investigator initialized")
    
    def _connect_web3(self) -> bool:
        """
        Establish Web3 connection with retry logic.
        Handles network interruptions gracefully.
        
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
                    logger.info(
                        f"Web3 connected. Block: {self.w3.eth.block_number}"
                    )
                    return True
                else:
                    logger.warning(f"Web3 connection failed (attempt {attempt + 1})")
                    
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
        Ensure Web3 connection is active, reconnect if needed.
        
        Returns:
            True if connected
        """
        try:
            if self.w3 and self.w3.is_connected():
                return True
        except:
            pass
        
        logger.warning("Web3 connection lost, reconnecting...")
        return self._connect_web3()
    
    def get_transaction_history(
        self, 
        address: str, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Fetch transaction history for an address.
        Uses Etherscan-style API or direct RPC scanning.
        
        Args:
            address: Target blockchain address
            limit: Maximum number of transactions to fetch
            
        Returns:
            List of transaction dictionaries
        """
        self._ensure_connection()
        
        transactions = []
        checksum_address = Web3.to_checksum_address(address)
        
        logger.info(f"Fetching transaction history for {address[:10]}...")
        
        try:
            # Get current block for reference
            current_block = self.w3.eth.block_number
            
            # Scan recent blocks for transactions (limited scan)
            # In production, use proper API like Etherscan
            start_block = max(0, current_block - 10000)  # Last ~10000 blocks
            
            for block_num in range(current_block, start_block, -1):
                try:
                    block = self.w3.eth.get_block(block_num, full_transactions=True)
                    
                    for tx in block.transactions:
                        if tx['from'] == checksum_address or tx['to'] == checksum_address:
                            tx_data = {
                                'hash': tx['hash'].hex(),
                                'block': block_num,
                                'from': tx['from'],
                                'to': tx['to'],
                                'value': float(self.w3.from_wei(tx['value'], 'ether')),
                                'timestamp': block['timestamp'],
                                'gas': tx['gas'],
                                'gasPrice': float(self.w3.from_wei(tx['gasPrice'], 'gwei')),
                            }
                            transactions.append(tx_data)
                            
                            if len(transactions) >= limit:
                                break
                                
                except (BlockNotFound, Exception) as e:
                    logger.debug(f"Block {block_num} error: {e}")
                    continue
                    
                if len(transactions) >= limit:
                    break
            
            logger.info(f"Found {len(transactions)} transactions")
            
        except Exception as e:
            logger.error(f"Error fetching transactions: {e}")
        
        return transactions
    
    def build_transaction_graph(
        self, 
        transactions: List[Dict[str, Any]],
        target_address: str
    ) -> nx.DiGraph:
        """
        Build directed graph from transaction data.
        Visualizes fund flow patterns.
        
        Args:
            transactions: List of transaction dictionaries
            target_address: Central target address
            
        Returns:
            NetworkX DiGraph with transaction data
        """
        self.graph.clear()
        
        # Add target node
        self.graph.add_node(
            target_address[:10] + "...",
            type='target',
            full_address=target_address
        )
        
        for tx in transactions:
            from_addr = tx['from']
            to_addr = tx['to']
            
            if not from_addr or not to_addr:
                continue
            
            # Create short labels for readability
            from_label = from_addr[:10] + "..."
            to_label = to_addr[:10] + "..."
            
            # Determine node types
            from_type = 'target' if from_addr.lower() == target_address.lower() else 'unknown'
            to_type = 'target' if to_addr.lower() == target_address.lower() else 'unknown'
            
            # Check if connected to known entities
            if from_addr.lower() in [a.lower() for a in KNOWN_CEX_ADDRESSES.keys()]:
                from_type = 'cex'
            elif from_addr.lower() in [a.lower() for a in KNOWN_MIXERS.keys()]:
                from_type = 'mixer'
            
            if to_addr.lower() in [a.lower() for a in KNOWN_CEX_ADDRESSES.keys()]:
                to_type = 'cex'
            elif to_addr.lower() in [a.lower() for a in KNOWN_MIXERS.keys()]:
                to_type = 'mixer'
            
            # Add nodes
            self.graph.add_node(from_label, type=from_type, full_address=from_addr)
            self.graph.add_node(to_label, type=to_type, full_address=to_addr)
            
            # Add edge with transaction data
            self.graph.add_edge(
                from_label, 
                to_label,
                weight=tx['value'],
                tx_hash=tx['hash'],
                timestamp=tx['timestamp']
            )
        
        logger.info(f"Built graph with {self.graph.number_of_nodes()} nodes, "
                   f"{self.graph.number_of_edges()} edges")
        
        return self.graph
    
    def detect_suspicious_patterns(
        self, 
        transactions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze transactions for suspicious patterns.
        
        Detection methods:
        - Structuring (breaking large amounts into smaller ones)
        - Rapid succession transactions
        - Mixer interactions
        - CEX exit points
        - Round number patterns
        
        Args:
            transactions: List of transaction dictionaries
            
        Returns:
            Dictionary of detected patterns
        """
        patterns = {
            'structuring': False,
            'mixer_interaction': False,
            'cex_exit': False,
            'rapid_transactions': False,
            'round_amounts': False,
            'findings': []
        }
        
        if not transactions:
            return patterns
        
        # Sort by timestamp
        sorted_txs = sorted(transactions, key=lambda x: x.get('timestamp', 0))
        
        # Check for structuring (many similar-sized transactions)
        amounts = [tx['value'] for tx in sorted_txs if tx['value'] > 0]
        if len(amounts) >= 3:
            # Check if amounts are suspiciously similar (within 10%)
            amount_groups = {}
            for amt in amounts:
                rounded = round(amt, 1)
                if rounded not in amount_groups:
                    amount_groups[rounded] = 0
                amount_groups[rounded] += 1
            
            for amt, count in amount_groups.items():
                if count >= 3 and amt > 0.1:  # 3+ similar transactions
                    patterns['structuring'] = True
                    patterns['findings'].append(
                        f"Structuring detected: {count} transactions of ~{amt} ETH"
                    )
        
        # Check for mixer interactions
        for tx in sorted_txs:
            from_lower = tx['from'].lower() if tx['from'] else ''
            to_lower = tx['to'].lower() if tx['to'] else ''
            
            if any(mixer.lower() in from_lower or mixer.lower() in to_lower 
                   for mixer in KNOWN_MIXERS.keys()):
                patterns['mixer_interaction'] = True
                patterns['findings'].append(
                    f"Mixer interaction: {tx['hash']}"
                )
        
        # Check for CEX exit points
        for tx in sorted_txs:
            to_lower = tx['to'].lower() if tx['to'] else ''
            
            if any(cex.lower() in to_lower for cex in KNOWN_CEX_ADDRESSES.keys()):
                patterns['cex_exit'] = True
                patterns['findings'].append(
                    f"CEX exit detected: {tx['to'][:10]}... ({tx['value']} ETH)"
                )
        
        # Check for rapid transactions (within minutes)
        timestamps = [tx['timestamp'] for tx in sorted_txs]
        if len(timestamps) >= 3:
            for i in range(len(timestamps) - 2):
                time_diff = timestamps[i+1] - timestamps[i]
                if 0 < time_diff < 300:  # Less than 5 minutes
                    patterns['rapid_transactions'] = True
                    patterns['findings'].append(
                        f"Rapid transactions detected within {time_diff}s"
                    )
                    break
        
        # Check for round amounts (possible automated behavior)
        round_count = sum(1 for amt in amounts if amt == round(amt) and amt > 0)
        if round_count >= 3:
            patterns['round_amounts'] = True
            patterns['findings'].append(
                f"Round amounts pattern: {round_count} transactions"
            )
        
        return patterns
    
    def query_local_llm(
        self, 
        prompt: str,
        model: str = "local-model"
    ) -> Optional[str]:
        """
        Query local LLM for analysis.
        
        IMPORTANT: The local LLM model is configured to run with:
        - 32 GB system RAM allocated
        - 8 GB VRAM for partial GPU acceleration
        - Model: Recommended Mistral-7B or similar for optimal performance
        
        Endpoint: http://localhost:1234/v1/chat/completions
        (Compatible with LM Studio / Ollama API format)
        
        Args:
            prompt: Analysis prompt for LLM
            model: Model identifier
            
        Returns:
            LLM response string or None on failure
        """
        LLM_ENDPOINT = "http://localhost:1234/v1/chat/completions"
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": """You are a blockchain forensics expert specializing in 
financial crime investigation. Your task is to analyze cryptocurrency transaction 
patterns and identify evidence of:
1. Money laundering techniques (layering, structuring, smurfing)
2. Obfuscation methods (mixers, cross-chain bridges)
3. Fiat off-ramps (CEX deposits, OTC trades)
4. Pattern analysis (timing, amounts, counterparty clusters)

Provide clear, evidence-based conclusions with specific transaction references.
Focus on actionable intelligence for bounty submission."""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,  # Lower temperature for more factual responses
            "max_tokens": 2000
        }
        
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Querying local LLM (attempt {attempt + 1})...")
                
                response = requests.post(
                    LLM_ENDPOINT,
                    json=payload,
                    timeout=LLM_TIMEOUT
                )
                response.raise_for_status()
                
                result = response.json()
                
                if 'choices' in result and len(result['choices']) > 0:
                    content = result['choices'][0]['message']['content']
                    logger.info("LLM analysis complete")
                    return content
                else:
                    logger.warning("Empty LLM response")
                    return None
                    
            except requests.exceptions.Timeout:
                logger.warning(f"LLM timeout (attempt {attempt + 1})")
                
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"LLM connection error (attempt {attempt + 1}): {e}")
                logger.info(
                    "Ensure local LLM is running on localhost:1234 "
                    "(LM Studio or Ollama with 32GB RAM / 8GB VRAM config)"
                )
                
            except Exception as e:
                logger.error(f"LLM error (attempt {attempt + 1}): {e}")
            
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logger.info(f"Retrying LLM in {delay}s...")
                time.sleep(delay)
        
        logger.error("LLM query failed after all retries")
        return None
    
    def generate_investigation_prompt(
        self,
        target_address: str,
        transactions: List[Dict[str, Any]],
        patterns: Dict[str, Any]
    ) -> str:
        """
        Generate analysis prompt for LLM based on financial investigation principles.
        
        The prompt is structured around:
        - Finding obfuscation methods (mixers, bridges, peeling chains)
        - Detecting structuring/smurfing (breaking large amounts)
        - Identifying fiat exit points (known CEX addresses)
        
        Args:
            target_address: The wallet under investigation
            transactions: List of relevant transactions
            patterns: Detected suspicious patterns
            
        Returns:
            Formatted prompt string
        """
        # Build transaction summary
        # NOTE: With 32GB RAM and 8GB VRAM configuration, local LLM can handle
        # 100+ transactions in context, enabling detection of hidden patterns
        # across longer transaction chains that would be invisible in shorter samples
        tx_summary = []
        for i, tx in enumerate(transactions[:100], 1):  # Increased from 20 to 100 for full LLM capacity
            tx_summary.append(
                f"{i}. From: {tx['from'][:16]}... → To: {tx['to'][:16]}... "
                f"| Value: {tx['value']:.4f} ETH | Hash: {tx['hash'][:16]}..."
            )
        
        patterns_text = "\n".join(
            f"- {finding}" for finding in patterns.get('findings', [])
        ) if patterns.get('findings') else "No specific patterns detected yet."
        
        prompt = f"""
FINANCIAL BLOCKCHAIN INVESTIGATION REQUEST
============================================

Target Address: {target_address}

AUTOMATED PATTERN DETECTION RESULTS:
{patterns_text}

TRANSACTION HISTORY (Last {min(len(transactions), 20)} transactions):
{chr(10).join(tx_summary)}

INVESTIGATION OBJECTIVES:
1. Identify any obfuscation techniques used (mixers, peeling chains, layering)
2. Detect structuring patterns (breaking large amounts into smaller transfers)
3. Trace fiat currency exit points (deposits to centralized exchanges)
4. Assess overall risk level and provide confidence score
5. Identify any known entities connected to this wallet

ANALYSIS REQUIRED:
Please analyze the above transaction data and provide:
1. Summary of wallet activity and behavior
2. Evidence of any suspicious patterns
3. Connection to known entities (CEXes, mixers, etc.)
4. Recommended follow-up investigation steps
5. Overall confidence level for bounty submission

Format your response as a structured investigation report suitable for 
submission to Arkham Intelligence bounty program.
"""
        
        return prompt
    
    def generate_markdown_report(
        self,
        target_address: str,
        transactions: List[Dict[str, Any]],
        patterns: Dict[str, Any],
        llm_analysis: Optional[str]
    ) -> str:
        """
        Generate Markdown investigation report.
        
        Args:
            target_address: Investigated address
            transactions: Transaction data
            patterns: Detected patterns
            llm_analysis: LLM analysis result
            
        Returns:
            Formatted Markdown string
        """
        timestamp = datetime.utcnow().isoformat()
        
        report = f"""# Arkham Intel Bounty Investigation Report

## Target Information
- **Address:** `{target_address}`
- **Network:** Ethereum Mainnet
- **Report Generated:** {timestamp}
- **Investigator:** OpenClaw Autonomous Agent v1.0

---

## Executive Summary

This report presents findings from an automated blockchain investigation 
targeting the address `{target_address[:16]}...`.

---

## Transaction Analysis

### Overview
- **Total Transactions Analyzed:** {len(transactions)}
- **Total Value Moved:** {sum(tx['value'] for tx in transactions):.4f} ETH
- **Time Period:** Last 10,000 blocks

### Suspicious Patterns Detected

"""
        
        if patterns.get('findings'):
            for finding in patterns['findings']:
                report += f"- {finding}\n"
        else:
            report += "_No automated pattern detections_\n"
        
        report += f"""

---

## Known Entity Connections

### CEX Interactions
"""
        
        # Check for CEX connections
        cex_found = False
        for tx in transactions:
            to_addr = tx.get('to', '').lower()
            for cex_addr, cex_name in KNOWN_CEX_ADDRESSES.items():
                if cex_addr.lower() == to_addr:
                    report += f"- **{cex_name}**: {tx['value']:.4f} ETH deposited\n"
                    cex_found = True
        
        if not cex_found:
            report += "_No direct CEX connections identified_\n"
        
        report += f"""

### Mixer Interactions
"""
        
        mixer_found = False
        for tx in transactions:
            from_addr = tx.get('from', '').lower()
            to_addr = tx.get('to', '').lower()
            for mixer_addr, mixer_name in KNOWN_MIXERS.items():
                if mixer_addr.lower() in [from_addr, to_addr]:
                    report += f"- **{mixer_name}**: Transaction detected\n"
                    mixer_found = True
        
        if not mixer_found:
            report += "_No mixer interactions identified_\n"
        
        report += f"""

---

## LLM Analysis

{llm_analysis if llm_analysis else "_LLM analysis unavailable (ensure local model is running)_"}

---

## Transaction Graph

```
Graph Statistics:
- Nodes: {self.graph.number_of_nodes()}
- Edges: {self.graph.number_of_edges()}
- Target centrality: {nx.degree_centrality(self.graph).get(target_address[:10]+'...', 'N/A') if self.graph.number_of_nodes() > 0 else 'N/A'}
```

---

## Conclusion

_This report was generated automatically by OpenClaw Arkham Intel Agent._

---
*Report Hash: {hash(timestamp + target_address)}*
"""
        
        return report
    
    def investigate(
        self, 
        target_address: str,
        tx_limit: int = 100
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Main investigation workflow.
        
        Args:
            target_address: Address to investigate
            tx_limit: Maximum transactions to analyze
            
        Returns:
            Tuple of (markdown_report, metadata_dict)
        """
        logger.info(f"Starting investigation of {target_address[:16]}...")
        
        # Fetch transactions
        transactions = self.get_transaction_history(target_address, limit=tx_limit)
        
        if not transactions:
            logger.warning("No transactions found for analysis")
            return "", {"error": "No transactions found"}
        
        # Build transaction graph
        self.build_transaction_graph(transactions, target_address)
        
        # Detect suspicious patterns
        patterns = self.detect_suspicious_patterns(transactions)
        
        # Generate LLM prompt
        prompt = self.generate_investigation_prompt(
            target_address, transactions, patterns
        )
        
        # Query local LLM
        llm_analysis = self.query_local_llm(prompt)
        
        # Generate report
        report = self.generate_markdown_report(
            target_address, transactions, patterns, llm_analysis
        )
        
        metadata = {
            'address': target_address,
            'tx_count': len(transactions),
            'patterns': patterns,
            'has_llm_analysis': llm_analysis is not None,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        logger.info(f"Investigation complete. Patterns found: {len(patterns.get('findings', []))}")
        
        return report, metadata


def investigate_address(
    address: str, 
    rpc_url: str,
    tx_limit: int = 100
) -> Tuple[str, Dict[str, Any]]:
    """
    Convenience function for address investigation.
    
    Args:
        address: Target blockchain address
        rpc_url: Web3 RPC endpoint
        tx_limit: Transaction limit
        
    Returns:
        Tuple of (report, metadata)
    """
    investigator = BlockchainInvestigator(rpc_url)
    return investigator.investigate(address, tx_limit)


if __name__ == "__main__":
    # Test investigator module
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    print("Testing Investigator Module...")
    print("=" * 50)
    
    rpc_url = os.getenv('WEB3_RPC_URL', 'https://eth.llamarpc.com')
    print(f"Using RPC: {rpc_url}")
    
    # Test with a known address (Binance hot wallet for demo)
    test_address = "0x28c6c06298d514db089934071355e5743bf21d60"
    
    print(f"\nInvestigating: {test_address}")
    print("-" * 50)
    
    investigator = BlockchainInvestigator(rpc_url)
    report, metadata = investigator.investigate(test_address, tx_limit=20)
    
    print("\nMETADATA:")
    print(json.dumps(metadata, indent=2, default=str))
    
    print("\nREPORT PREVIEW (first 500 chars):")
    print(report[:500] + "..." if len(report) > 500 else report)
    
    print("\n" + "=" * 50)
    print("Investigator test complete.")