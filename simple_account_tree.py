#!/usr/bin/env python3
"""
Simple account tree printer - loads GnuCash accounts and shows mapping by entity.
"""

import json
import re
from piecash import open_book

db_path = r"D:\Users\Conrad\Documents\GnuCash\gnuCash414\CFSIV_Sqlite3_database.gnucash"
entity_map_file = "entity-map-suggested.json"

# Load entity map
with open(entity_map_file) as f:
    entity_map = json.load(f)

print("=" * 100)
print("ACCOUNT TREE ORGANIZED BY ENTITY")
print("=" * 100)
print()

# Open GnuCash book
book = open_book(db_path, readonly=True, do_backup=False)

# Get all non-placeholder accounts
accounts = [a for a in book.accounts if not a.placeholder and a.type != "ROOT"]

# Match accounts to entities using the patterns
accounts_by_entity = {}

for account in accounts:
    matched_entity = None
    
    # Try to match against each entity's patterns
    for entity_id, patterns in entity_map.get("patterns", {}).items():
        for pattern in patterns:
            if re.search(pattern, account.fullname):
                matched_entity = entity_id
                break
        if matched_entity:
            break
    
    if matched_entity:
        if matched_entity not in accounts_by_entity:
            accounts_by_entity[matched_entity] = []
        accounts_by_entity[matched_entity].append(account)

# Print accounts grouped by entity
for entity_id in sorted([k for k in accounts_by_entity.keys() if k != "personal"]) + ["personal"]:
    if entity_id not in accounts_by_entity:
        continue
        
    entity = entity_map["entities"][entity_id]
    accts = sorted(accounts_by_entity[entity_id], key=lambda a: a.fullname)
    
    print()
    print("=" * 100)
    print(f"{entity['label'].upper()}")
    print("=" * 100)
    print(f"Entity ID: {entity_id}")
    print(f"Type: {entity['type']}")
    print(f"Total Accounts: {len(accts)}")
    print("-" * 100)
    print()
    
    for account in accts:
        # Get account type
        acct_type = account.type if hasattr(account, 'type') else 'UNKNOWN'
        
        # Print with full path
        print(f"  [{acct_type:10s}]  {account.fullname}")
    
    print()

print("=" * 100)
print(f"TOTAL ACCOUNTS MAPPED: {sum(len(v) for v in accounts_by_entity.values())}")
print("=" * 100)

book.close()
