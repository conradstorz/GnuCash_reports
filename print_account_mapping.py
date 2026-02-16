#!/usr/bin/env python3
"""
Print a report showing all accounts grouped by entity.
"""

import sys
from pathlib import Path
from piecash import open_book
from gcgaap.entity_map import EntityMap

def main():
    db_path = r"D:\Users\Conrad\Documents\GnuCash\gnuCash414\CFSIV_Sqlite3_database.gnucash"
    entity_map_path = Path("entity-map-suggested.json")
    
    print("=" * 100)
    print("ACCOUNT TREE BY ENTITY")
    print("=" * 100)
    print()
    
    # Load entity map
    entity_map = EntityMap()
    entity_map.load(entity_map_path)
    
    print(f"Entity Map: {entity_map_path}")
    print(f"Total Entities: {len(entity_map.entities)}")
    print()
    
    # Open GnuCash book
    print(f"Opening: {db_path}")
    print()
    book = open_book(db_path, readonly=True, do_backup=False)
    
    # Group accounts by entity
    accounts_by_entity = {}
    unmapped = []
    
    for account in book.accounts:
        # Skip placeholder/root accounts
        if account.placeholder or account.type == "ROOT":
            continue
            
        entity_id = entity_map.resolve_entity_for_account(account.guid, account.fullname)
        
        if entity_map.is_explicitly_mapped(account.guid, account.fullname):
            if entity_id not in accounts_by_entity:
                accounts_by_entity[entity_id] = []
            accounts_by_entity[entity_id].append(account)
        else:
            unmapped.append(account)
    
    total_accounts = sum(len(accts) for accts in accounts_by_entity.values()) + len(unmapped)
    print(f"Total Accounts: {total_accounts}")
    print()
    print("=" * 100)
    print()
    
    # Print accounts by entity
    for entity_id in sorted(accounts_by_entity.keys()):
        entity = entity_map.entities[entity_id]
        accounts = sorted(accounts_by_entity[entity_id], key=lambda a: a.fullname)
        
        print()
        print("=" * 100)
        print(f"{entity.label.upper()} ({entity_id})")
        print("=" * 100)
        print(f"Type: {entity.type}")
        print(f"Account Count: {len(accounts)}")
        print("-" * 100)
        print()
        
        for account in accounts:
            account_type = account.type if hasattr(account, 'type') else 'UNKNOWN'
            # Indent based on account depth
            depth = account.fullname.count(':')
            indent = "  " * depth
            account_name = account.name
            print(f"{indent}{account_name:50s} [{account_type:10s}]  {account.fullname}")
        
        print()
    
    # Print unmapped accounts if any
    if unmapped:
        print()
        print("=" * 100)
        print("UNMAPPED ACCOUNTS")
        print("=" * 100)
        print(f"Count: {len(unmapped)}")
        print("-" * 100)
        print()
        for account in sorted(unmapped, key=lambda a: a.fullname):
            account_type = account.type if hasattr(account, 'type') else 'UNKNOWN'
            depth = account.fullname.count(':')
            indent = "  " * depth
            account_name = account.name
            print(f"{indent}{account_name:50s} [{account_type:10s}]  {account.fullname}")
        print()
    
    print()
    print("=" * 100)
    print("END OF REPORT")
    print("=" * 100)
    
    book.close()

if __name__ == "__main__":
    main()
