#!/usr/bin/env python3
"""
Print a report showing all accounts grouped by entity using gcgaap modules.
"""

import sys
from pathlib import Path
from gcgaap.entity_map import EntityMap
from gcgaap.gnucash_access import GnuCashBook

def main():
    db_path = Path(r"D:\Users\Conrad\Documents\GnuCash\gnuCash414\CFSIV_Sqlite3_database.gnucash")
    entity_map_path = Path("entity-map-suggested.json")
    
    print("=" * 100)
    print("ACCOUNT MAPPING BY ENTITY")
    print("=" * 100)
    print()
    
    # Load entity map
    print(f"Loading entity map from: {entity_map_path}")
    entity_map = EntityMap.load(entity_map_path)
    
    print(f"Total Entities: {len(entity_map.entities)}")
    print(f"Default Entity: {entity_map.default_entity}")
    print()
    
    # Open GnuCash book
    print(f"Opening GnuCash book: {db_path}")
    print()
    
    with GnuCashBook(db_path) as book:
        # Group accounts by entity
        accounts_by_entity = {}
        unmapped = []
        
        for account in book.iter_accounts():
            entity_id = entity_map.resolve_entity_for_account(account.guid, account.full_name)
            
            if entity_map.is_explicitly_mapped(account.guid, account.full_name):
                if entity_id not in accounts_by_entity:
                    accounts_by_entity[entity_id] = []
                accounts_by_entity[entity_id].append(account)
            else:
                unmapped.append(account)
        
        total_accounts = sum(len(accts) for accts in accounts_by_entity.values()) + len(unmapped)
        total_mapped = sum(len(accts) for accts in accounts_by_entity.values())
        
        print(f"Total Accounts: {total_accounts}")
        print(f"Explicitly Mapped: {total_mapped}")
        print(f"Using Default Entity: {len(unmapped)}")
        print()
        print("=" * 100)
        print()
        
        # Print accounts by entity
        for entity_id in sorted(accounts_by_entity.keys()):
            entity = entity_map.entities.get(entity_id)
            if not entity:
                print(f"WARNING: Entity '{entity_id}' not found in entity definitions")
                continue
                
            accounts = sorted(accounts_by_entity[entity_id], key=lambda a: a.full_name)
            
            print()
            print("=" * 100)
            print(f"{entity.label.upper()} ({entity_id})")
            print("=" * 100)
            print(f"Type: {entity.type}")
            print(f"Account Count: {len(accounts)}")
            print("-" * 100)
            print()
            
            for account in accounts:
                # Indent based on account depth
                depth = account.full_name.count(':')
                indent = "  " * depth
                account_name = account.full_name.split(':')[-1]
                print(f"{indent}{account_name:60s} [{account.type:12s}] {account.guid[:8]}")
            
            print()
        
        # Print unmapped accounts if any
        if unmapped:
            print()
            print("=" * 100)
            print(f"ACCOUNTS USING DEFAULT ENTITY ('{entity_map.default_entity}')")
            print("=" * 100)
            print(f"Count: {len(unmapped)}")
            print("-" * 100)
            print()
            for account in sorted(unmapped, key=lambda a: a.full_name):
                depth = account.full_name.count(':')
                indent = "  " * depth
                account_name = account.full_name.split(':')[-1]
                print(f"{indent}{account_name:60s} [{account.type:12s}] {account.guid[:8]}")
            print()
    
    print()
    print("=" * 100)
    print("END OF REPORT")
    print("=" * 100)

if __name__ == "__main__":
    main()
