"""
Database Module for OpenClaw Arkham Intel Agent
================================================
SQLite-based storage for tracking bounty targets and submissions.
Designed for 12+ hours of uninterrupted operation.
"""

import sqlite3
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database file path
DB_FILE = "bounty_tracker.db"


class Database:
    """
    SQLite database manager for bounty tracking.
    Handles connection pooling and error recovery.
    """
    
    def __init__(self, db_file: str = DB_FILE):
        """
        Initialize database connection and create tables if needed.
        
        Args:
            db_file: Path to SQLite database file
        """
        self.db_file = db_file
        self.connection: Optional[sqlite3.Connection] = None
        self._connect()
        self._create_tables()
    
    def _connect(self) -> None:
        """
        Establish database connection with retry logic.
        Handles potential connection failures gracefully.
        """
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                self.connection = sqlite3.connect(
                    self.db_file,
                    timeout=30.0,  # 30 second timeout for locks
                    check_same_thread=False  # Allow multi-threading
                )
                self.connection.row_factory = sqlite3.Row
                logger.info(f"Database connected: {self.db_file}")
                return
            except sqlite3.Error as e:
                logger.error(f"Database connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
        
        raise RuntimeError("Failed to establish database connection after retries")
    
    def _create_tables(self) -> None:
        """
        Create necessary tables if they don't exist.
        Idempotent - safe to call multiple times.
        """
        create_targets_table = """
        CREATE TABLE IF NOT EXISTS targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT NOT NULL UNIQUE,
            reward REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            tx_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            investigation_report TEXT,
            ipfs_cid TEXT
        );
        """
        
        create_index = """
        CREATE INDEX IF NOT EXISTS idx_targets_status 
        ON targets(status);
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(create_targets_table)
            cursor.execute(create_index)
            self.connection.commit()
            logger.info("Database tables verified/created")
        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}")
            self.connection.rollback()
            raise
    
    def _ensure_connection(self) -> None:
        """
        Ensure database connection is active.
        Reconnects if connection was lost.
        """
        try:
            # Test connection with simple query
            self.connection.execute("SELECT 1")
        except (sqlite3.Error, AttributeError):
            logger.warning("Database connection lost, reconnecting...")
            self._connect()
    
    def add_target(
        self, 
        address: str, 
        reward: float,
        status: str = "new"
    ) -> Optional[int]:
        """
        Add a new bounty target to the database.
        
        Args:
            address: Blockchain address of the target
            reward: Bounty reward amount in USD
            status: Initial status (default: 'new')
            
        Returns:
            Target ID if successful, None otherwise
        """
        self._ensure_connection()
        
        insert_query = """
        INSERT OR IGNORE INTO targets (address, reward, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """
        
        now = datetime.utcnow().isoformat()
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(insert_query, (address, reward, status, now, now))
            self.connection.commit()
            
            if cursor.rowcount > 0:
                target_id = cursor.lastrowid
                logger.info(f"Added new target: {address[:10]}... (reward: ${reward})")
                return target_id
            else:
                logger.debug(f"Target already exists: {address[:10]}...")
                return self.get_target_by_address(address)['id']
                
        except sqlite3.Error as e:
            logger.error(f"Error adding target {address[:10]}...: {e}")
            self.connection.rollback()
            return None
    
    def update_status(
        self, 
        target_id: int, 
        status: str,
        tx_hash: Optional[str] = None,
        investigation_report: Optional[str] = None,
        ipfs_cid: Optional[str] = None
    ) -> bool:
        """
        Update target status and associated data.
        
        Args:
            target_id: Target's database ID
            status: New status ('investigating', 'completed', 'submitted', 'failed')
            tx_hash: Transaction hash if submitted to blockchain
            investigation_report: Generated investigation report
            ipfs_cid: IPFS content identifier for the report
            
        Returns:
            True if update successful, False otherwise
        """
        self._ensure_connection()
        
        update_query = """
        UPDATE targets 
        SET status = ?, 
            tx_hash = COALESCE(?, tx_hash),
            investigation_report = COALESCE(?, investigation_report),
            ipfs_cid = COALESCE(?, ipfs_cid),
            updated_at = ?
        WHERE id = ?
        """
        
        now = datetime.utcnow().isoformat()
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                update_query, 
                (status, tx_hash, investigation_report, ipfs_cid, now, target_id)
            )
            self.connection.commit()
            
            success = cursor.rowcount > 0
            if success:
                logger.info(f"Updated target {target_id} status to: {status}")
            return success
            
        except sqlite3.Error as e:
            logger.error(f"Error updating target {target_id}: {e}")
            self.connection.rollback()
            return False
    
    def get_target_by_address(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve target by blockchain address.
        
        Args:
            address: Blockchain address to look up
            
        Returns:
            Target dict or None if not found
        """
        self._ensure_connection()
        
        query = "SELECT * FROM targets WHERE address = ?"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (address,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error fetching target {address[:10]}...: {e}")
            return None
    
    def get_targets_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Retrieve all targets with a specific status.
        
        Args:
            status: Status to filter by
            
        Returns:
            List of target dicts
        """
        self._ensure_connection()
        
        query = "SELECT * FROM targets WHERE status = ? ORDER BY reward DESC"
        
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (status,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error fetching targets by status {status}: {e}")
            return []
    
    def get_pending_targets(self) -> List[Dict[str, Any]]:
        """
        Get all targets that need investigation.
        
        Returns:
            List of targets with 'new' status
        """
        return self.get_targets_by_status('new')
    
    def close(self) -> None:
        """
        Close database connection gracefully.
        """
        if self.connection:
            try:
                self.connection.close()
                logger.info("Database connection closed")
            except sqlite3.Error as e:
                logger.error(f"Error closing database: {e}")


# Convenience functions for module-level usage
_db_instance: Optional[Database] = None


def get_database() -> Database:
    """
    Get or create database singleton instance.
    
    Returns:
        Database instance
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance


def add_target(address: str, reward: float, status: str = "new") -> Optional[int]:
    """
    Add new target using default database instance.
    """
    return get_database().add_target(address, reward, status)


def update_status(
    target_id: int, 
    status: str,
    tx_hash: Optional[str] = None,
    investigation_report: Optional[str] = None,
    ipfs_cid: Optional[str] = None
) -> bool:
    """
    Update target status using default database instance.
    """
    return get_database().update_status(
        target_id, status, tx_hash, investigation_report, ipfs_cid
    )


if __name__ == "__main__":
    # Test database initialization
    print("Initializing database...")
    db = Database()
    print(f"Database created: {DB_FILE}")
    
    # Test insert
    test_id = db.add_target(
        "0x1234567890abcdef1234567890abcdef12345678",
        1000.0
    )
    print(f"Test target added with ID: {test_id}")
    
    # Test query
    targets = db.get_pending_targets()
    print(f"Pending targets: {len(targets)}")
    
    db.close()
    print("Database test complete.")