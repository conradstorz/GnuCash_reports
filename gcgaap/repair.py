"""
Database repair utilities for GnuCash files.

Provides functions to diagnose and repair common data integrity issues
that prevent proper reading and processing of GnuCash databases.
"""

import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RepairResult:
    """
    Result of a repair operation.
    
    Attributes:
        success: Whether the repair was successful.
        items_fixed: Number of items repaired.
        backup_path: Path to the backup file created.
        message: Human-readable message about the repair.
    """
    
    success: bool
    items_fixed: int
    backup_path: Path
    message: str


def create_backup(db_path: Path) -> Path:
    """
    Create a timestamped backup of the GnuCash database.
    
    Args:
        db_path: Path to the GnuCash database file.
        
    Returns:
        Path to the backup file.
        
    Raises:
        IOError: If backup creation fails.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(f'.backup_{timestamp}.gnucash')
    
    logger.info(f"Creating backup: {backup_path}")
    
    try:
        shutil.copy2(db_path, backup_path)
        logger.info("Backup created successfully")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        raise IOError(f"Could not create backup: {e}")


def diagnose_empty_reconcile_dates(db_path: Path) -> Tuple[int, List[str]]:
    """
    Diagnose how many splits have empty reconcile_date fields.
    
    Args:
        db_path: Path to the GnuCash database file.
        
    Returns:
        Tuple of (count of affected splits, list of affected transaction descriptions).
        
    Raises:
        sqlite3.Error: If database access fails.
    """
    logger.info("Diagnosing empty reconcile_date fields...")
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Count affected splits
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM splits
            WHERE reconcile_date = ''
        """)
        
        count = cursor.fetchone()['count']
        
        # Get descriptions of affected transactions
        cursor.execute("""
            SELECT DISTINCT t.description
            FROM transactions t
            JOIN splits s ON t.guid = s.tx_guid
            WHERE s.reconcile_date = ''
            ORDER BY t.description
        """)
        
        descriptions = [row['description'] for row in cursor.fetchall()]
        
        logger.info(f"Found {count} splits with empty reconcile_date in {len(descriptions)} transactions")
        
        return count, descriptions
        
    finally:
        conn.close()


def repair_empty_reconcile_dates(db_path: Path, create_backup_first: bool = True) -> RepairResult:
    """
    Repair empty reconcile_date fields by setting them to NULL.
    
    Empty string values in date fields cause piecash to fail with:
    "Couldn't parse datetime string: ''"
    
    This function converts empty strings to NULL, which piecash handles correctly.
    
    Args:
        db_path: Path to the GnuCash database file.
        create_backup_first: Whether to create a backup before repairing (default: True).
        
    Returns:
        RepairResult with details of the repair operation.
        
    Raises:
        IOError: If backup creation fails.
        sqlite3.Error: If database modification fails.
    """
    logger.info(f"Starting repair of empty reconcile_date fields in {db_path}")
    
    # Create backup if requested
    backup_path = None
    if create_backup_first:
        backup_path = create_backup(db_path)
    
    # Open database connection
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Count affected splits before repair
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM splits
            WHERE reconcile_date = ''
        """)
        
        count_before = cursor.fetchone()[0]
        
        if count_before == 0:
            logger.info("No empty reconcile_date fields found - database is clean")
            return RepairResult(
                success=True,
                items_fixed=0,
                backup_path=backup_path,
                message="No repairs needed - database is clean"
            )
        
        logger.info(f"Found {count_before} splits with empty reconcile_date")
        
        # Perform the repair
        cursor.execute("""
            UPDATE splits
            SET reconcile_date = NULL
            WHERE reconcile_date = ''
        """)
        
        items_fixed = cursor.rowcount
        
        # Commit changes
        conn.commit()
        
        # Verify the fix
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM splits
            WHERE reconcile_date = ''
        """)
        
        count_after = cursor.fetchone()[0]
        
        if count_after == 0:
            logger.info(f"Successfully repaired {items_fixed} splits")
            return RepairResult(
                success=True,
                items_fixed=items_fixed,
                backup_path=backup_path,
                message=f"Successfully repaired {items_fixed} split(s)"
            )
        else:
            logger.warning(f"{count_after} splits still have empty reconcile_date after repair")
            return RepairResult(
                success=False,
                items_fixed=items_fixed,
                backup_path=backup_path,
                message=f"Partial repair: {items_fixed} fixed, {count_after} remain"
            )
            
    except Exception as e:
        conn.rollback()
        logger.error(f"Repair failed: {e}")
        raise
    finally:
        conn.close()


def verify_repair(db_path: Path, problem_guids: List[str]) -> bool:
    """
    Verify that specific transactions are now readable after repair.
    
    Args:
        db_path: Path to the GnuCash database file.
        problem_guids: List of transaction GUIDs to check.
        
    Returns:
        True if all transactions are clean, False otherwise.
    """
    logger.info("Verifying repair...")
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        all_clean = True
        
        for guid in problem_guids:
            cursor.execute("""
                SELECT t.description,
                       (SELECT COUNT(*) FROM splits WHERE tx_guid = ? AND reconcile_date = '') as empty_dates
                FROM transactions t
                WHERE t.guid = ?
            """, (guid, guid))
            
            row = cursor.fetchone()
            if row:
                desc = row['description']
                empty = row['empty_dates']
                
                if empty > 0:
                    logger.warning(f"Transaction '{desc}' still has {empty} empty date(s)")
                    all_clean = False
                else:
                    logger.debug(f"Transaction '{desc}' is clean")
        
        return all_clean
        
    finally:
        conn.close()
