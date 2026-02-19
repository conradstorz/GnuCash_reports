#!/usr/bin/env python3
"""
Entity Account Mapper

Scans a GnuCash database and maps all accounts to entities based on naming patterns.
If a parent account matches an entity pattern, all child accounts inherit that entity.
Outputs a JSON file with entities and their associated accounts.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from piecash import open_book


# Entity definitions with their matching patterns
ENTITIES = {
    "placeholder_only_acct": {
        "label": "Placeholder Only Account",
        "aliases": [],  # Special entity for placeholder accounts
    },
    "unassigned": {
        "label": "Unassigned",
        "aliases": [],  # Default entity - no patterns
    },
    "personal": {
        "label": "Personal",
        "aliases": ["personal", "3023 old hill rd", "3023 old hill", "old hill rd"],
    },
    "storz_amusements": {
        "label": "Storz Amusements",
        "aliases": ["storz amusements", "storz amusement", "samuse", "s\\.?a\\.?music", "s\\.?a\\.?muse"],
    },
    "storz_cash": {
        "label": "Storz Cash",
        "aliases": ["storz cash", "scsllc", "scs llc", "s\\.?c\\.?s"],
    },
    "storz_property": {
        "label": "Storz Property",  
        "aliases": ["storz property", "storz properties", "spmllc", "spm llc", "s\\.?p\\.?m"],
    },
}


def build_entity_patterns() -> Dict[str, List[re.Pattern]]:
    """
    Build compiled regex patterns for each entity.
    
    Returns:
        Dictionary mapping entity keys to lists of compiled regex patterns.
    """
    patterns = {}
    
    for entity_key, entity_info in ENTITIES.items():
        if entity_key in ("unassigned", "placeholder_only_acct"):
            patterns[entity_key] = []
            continue
            
        entity_patterns = []
        for alias in entity_info["aliases"]:
            # Create pattern that matches the alias as a whole word or phrase
            # Use word boundaries for proper word matching
            pattern = r'\b' + alias + r'\b'
            entity_patterns.append(re.compile(pattern, re.IGNORECASE))
        
        patterns[entity_key] = entity_patterns
    
    return patterns


def match_entity(account_name: str, entity_patterns: Dict[str, List[re.Pattern]]) -> Optional[str]:
    """
    Match an account name against entity patterns.
    
    Args:
        account_name: The account name to match.
        entity_patterns: Dictionary of entity patterns.
        
    Returns:
        Entity key if matched, None otherwise.
    """
    for entity_key, patterns in entity_patterns.items():
        if entity_key in ("unassigned", "placeholder_only_acct"):
            continue
            
        for pattern in patterns:
            if pattern.search(account_name):
                return entity_key
    
    return None


def build_account_tree(book):
    """
    Build a tree structure of all accounts with parent-child relationships.
    
    Args:
        book: Open piecash book.
        
    Returns:
        Tuple of (accounts_dict, root_accounts) where:
        - accounts_dict maps account GUID to account info
        - root_accounts is list of accounts with no parent (or ROOT parent)
    """
    accounts_dict = {}
    root_accounts = []
    
    for account in book.accounts:
        # Skip ROOT account type
        if account.type == "ROOT":
            continue
            
        account_info = {
            "guid": account.guid,
            "name": account.name,
            "full_name": account.fullname,
            "type": account.type,
            "parent_guid": account.parent.guid if account.parent and account.parent.type != "ROOT" else None,
            "children_guids": [],
            "entity": None,  # Will be assigned later
            "is_placeholder": bool(account.placeholder),  # Track placeholder status
        }
        
        accounts_dict[account.guid] = account_info
        
        # Track root accounts (those with ROOT parent or no parent)
        if not account.parent or account.parent.type == "ROOT":
            root_accounts.append(account.guid)
    
    # Build children relationships
    for guid, account_info in accounts_dict.items():
        if account_info["parent_guid"]:
            parent = accounts_dict.get(account_info["parent_guid"])
            if parent:
                parent["children_guids"].append(guid)
    
    return accounts_dict, root_accounts


def assign_entities_with_inheritance(
    accounts_dict: Dict[str, dict],
    root_accounts: List[str],
    entity_patterns: Dict[str, List[re.Pattern]]
) -> None:
    """
    Assign entities to accounts with parent-to-child inheritance.
    
    If a parent account matches an entity pattern, all descendants inherit that entity.
    Otherwise, check each account individually for pattern matches.
    
    Args:
        accounts_dict: Dictionary of account information.
        root_accounts: List of root account GUIDs.
        entity_patterns: Compiled entity patterns.
    """
    def assign_recursive(account_guid: str, inherited_entity: Optional[str] = None):
        """Recursively assign entity to account and its children."""
        account = accounts_dict[account_guid]
        
        # Check if this is a placeholder account
        if account.get("is_placeholder", False):
            account["entity"] = "placeholder_only_acct"
            entity_to_pass = None  # Don't inherit placeholder entity
        # If we have an inherited entity, use it
        elif inherited_entity:
            account["entity"] = inherited_entity
            entity_to_pass = inherited_entity
        else:
            # Try to match this account's name against patterns
            matched_entity = match_entity(account["full_name"], entity_patterns)
            if matched_entity:
                account["entity"] = matched_entity
                entity_to_pass = matched_entity
            else:
                # No match, assign to unassigned
                account["entity"] = "unassigned"
                entity_to_pass = None  # Don't inherit "unassigned"
        
        # Recursively process children
        for child_guid in account["children_guids"]:
            assign_recursive(child_guid, entity_to_pass)
    
    # Process all root accounts
    for root_guid in root_accounts:
        assign_recursive(root_guid)


def generate_entity_report(accounts_dict: Dict[str, dict]) -> Dict[str, List[dict]]:
    """
    Generate the final report structure: entities mapped to their accounts.
    
    Args:
        accounts_dict: Dictionary of account information with entities assigned.
        
    Returns:
        Dictionary mapping entity keys to lists of account information.
    """
    report = defaultdict(list)
    
    for account_info in accounts_dict.values():
        entity_key = account_info["entity"]
        
        # Create clean account object for output
        account_output = {
            "guid": account_info["guid"],
            "name": account_info["name"],
            "full_name": account_info["full_name"],
            "type": account_info["type"],
            "parent_guid": account_info["parent_guid"],
        }
        
        report[entity_key].append(account_output)
    
    # Sort accounts within each entity by full name
    for entity_key in report:
        report[entity_key].sort(key=lambda a: a["full_name"])
    
    return dict(report)


def generate_summary(report: Dict[str, List[dict]]) -> Dict:
    """
    Generate a summary section for the report.
    
    Args:
        report: The entity report.
        
    Returns:
        Dictionary with summary statistics.
    """
    summary = {
        "total_accounts": sum(len(accounts) for accounts in report.values()),
        "entity_counts": {
            entity_key: len(accounts) 
            for entity_key, accounts in report.items()
        },
        "entity_labels": {
            entity_key: ENTITIES[entity_key]["label"]
            for entity_key in report.keys()
        }
    }
    return summary


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Map GnuCash accounts to entities based on naming patterns."
    )
    parser.add_argument(
        "database",
        type=str,
        help="Path to the GnuCash database file"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="entity_account_map.json",
        help="Output JSON file path (default: entity_account_map.json)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    # Validate database file exists
    db_path = Path(args.database)
    if not db_path.exists():
        print(f"Error: Database file not found: {args.database}", file=sys.stderr)
        sys.exit(1)
    
    if args.verbose:
        print(f"Opening GnuCash database: {db_path}")
    
    # Open the GnuCash book
    try:
        book = open_book(str(db_path), readonly=True, do_backup=False)
    except Exception as e:
        print(f"Error opening database: {e}", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Build entity patterns
        if args.verbose:
            print("Building entity patterns...")
        entity_patterns = build_entity_patterns()
        
        # Build account tree
        if args.verbose:
            print("Building account tree...")
        accounts_dict, root_accounts = build_account_tree(book)
        
        if args.verbose:
            print(f"Found {len(accounts_dict)} accounts")
        
        # Assign entities with inheritance
        if args.verbose:
            print("Assigning entities to accounts...")
        assign_entities_with_inheritance(accounts_dict, root_accounts, entity_patterns)
        
        # Generate report
        if args.verbose:
            print("Generating report...")
        report = generate_entity_report(accounts_dict)
        summary = generate_summary(report)
        
        # Create final output structure
        output = {
            "summary": summary,
            "entities": report,
        }
        
        # Write to JSON file
        output_path = Path(args.output)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        if args.verbose:
            print(f"\nReport written to: {output_path}")
            print(f"\nSummary:")
            for entity_key, count in summary["entity_counts"].items():
                label = summary["entity_labels"][entity_key]
                print(f"  {label:20s}: {count:4d} accounts")
            print(f"  {'-' * 26}")
            print(f"  {'Total':20s}: {summary['total_accounts']:4d} accounts")
        else:
            print(f"Entity mapping complete. Output written to: {output_path}")
    
    finally:
        book.close()


if __name__ == "__main__":
    main()
