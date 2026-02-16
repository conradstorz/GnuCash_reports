#!/usr/bin/env python3
"""
Display Entity Account Tree

Reads the entity_account_map.json file and displays accounts in a tree structure
organized by entity.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List


def build_tree_structure(accounts: List[dict]) -> Dict[str, dict]:
    """
    Build a tree structure from flat account list.
    
    Args:
        accounts: List of account dictionaries.
        
    Returns:
        Dictionary mapping account GUIDs to account info with children.
    """
    # Create lookup dictionary
    accounts_by_guid = {}
    for account in accounts:
        accounts_by_guid[account["guid"]] = {
            **account,
            "children": []
        }
    
    # Find root accounts and build parent-child relationships
    root_accounts = []
    for guid, account in accounts_by_guid.items():
        parent_guid = account.get("parent_guid")
        if parent_guid and parent_guid in accounts_by_guid:
            accounts_by_guid[parent_guid]["children"].append(account)
        else:
            root_accounts.append(account)
    
    return accounts_by_guid, root_accounts


def print_tree(account: dict, prefix: str = "", is_last: bool = True):
    """
    Recursively print account tree with visual formatting.
    
    Args:
        account: Account dictionary with children.
        prefix: Current line prefix for tree structure.
        is_last: Whether this is the last child at this level.
    """
    # Determine the connector characters (using ASCII-safe characters)
    connector = "+-- " if is_last else "|-- "
    
    # Print current account
    account_type = account.get("type", "UNKNOWN")
    account_name = account.get("name", "Unknown")
    print(f"{prefix}{connector}[{account_type:10s}] {account_name}")
    
    # Prepare prefix for children
    if is_last:
        child_prefix = prefix + "    "
    else:
        child_prefix = prefix + "|   "
    
    # Print children
    children = account.get("children", [])
    # Sort children by name
    children.sort(key=lambda a: a.get("name", ""))
    
    for i, child in enumerate(children):
        is_last_child = (i == len(children) - 1)
        print_tree(child, child_prefix, is_last_child)


def display_entity_trees(data: dict, show_counts: bool = True):
    """
    Display all entity trees.
    
    Args:
        data: The loaded JSON data.
        show_counts: Whether to show account counts in headers.
    """
    summary = data.get("summary", {})
    entities_data = data.get("entities", {})
    entity_labels = summary.get("entity_labels", {})
    entity_counts = summary.get("entity_counts", {})
    
    # Define display order (put unassigned last)
    entity_order = ["personal", "storz_amusements", "storz_cash", "storz_property", "unassigned"]
    
    # Add any entities not in the predefined order
    for entity_key in entities_data.keys():
        if entity_key not in entity_order:
            entity_order.append(entity_key)
    
    print("=" * 100)
    print("ACCOUNT TREES BY ENTITY")
    print("=" * 100)
    
    if show_counts:
        print("\nSummary:")
        print(f"  Total Accounts: {summary.get('total_accounts', 0)}")
        print()
    
    for entity_key in entity_order:
        if entity_key not in entities_data:
            continue
        
        accounts = entities_data[entity_key]
        label = entity_labels.get(entity_key, entity_key.replace("_", " ").title())
        count = entity_counts.get(entity_key, len(accounts))
        
        # Print entity header
        print()
        print("=" * 100)
        print(f"{label.upper()}")
        print("=" * 100)
        print(f"Entity: {entity_key}")
        if show_counts:
            print(f"Accounts: {count}")
        print("-" * 100)
        print()
        
        if not accounts:
            print("  (No accounts)")
            continue
        
        # Build and display tree
        accounts_by_guid, root_accounts = build_tree_structure(accounts)
        
        # Sort root accounts by name
        root_accounts.sort(key=lambda a: a.get("name", ""))
        
        # Print each root account tree
        for i, root_account in enumerate(root_accounts):
            is_last = (i == len(root_accounts) - 1)
            print_tree(root_account, "", is_last)
        
        print()
    
    print("=" * 100)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Display account trees organized by entity from JSON mapping file."
    )
    parser.add_argument(
        "json_file",
        type=str,
        nargs="?",
        default="entity_account_map.json",
        help="Path to the entity account map JSON file (default: entity_account_map.json)"
    )
    parser.add_argument(
        "--no-counts",
        action="store_true",
        help="Hide account counts in output"
    )
    
    args = parser.parse_args()
    
    # Load JSON file
    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"Error: File not found: {args.json_file}", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Display trees
    display_entity_trees(data, show_counts=not args.no_counts)


if __name__ == "__main__":
    main()
