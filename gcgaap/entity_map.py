"""
Entity mapping functionality for GCGAAP.

Provides the ability to map GnuCash accounts to logical entities (e.g., personal,
various businesses) using a persistent JSON configuration file with GUID-based
and pattern-based mapping rules.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EntityDefinition:
    """
    Definition of a logical entity within the GnuCash book.
    
    Attributes:
        key: Unique identifier for this entity (e.g., "personal", "alpha_llc").
        label: Human-readable display name.
        type: Entity type - "individual" or "business".
    """
    
    key: str
    label: str
    type: str  # "individual" or "business"
    
    def __post_init__(self):
        """Validate entity type."""
        if self.type not in ("individual", "business"):
            logger.warning(
                f"Entity '{self.key}' has unexpected type '{self.type}'. "
                f"Expected 'individual' or 'business'."
            )


@dataclass
class EntityMap:
    """
    Maps GnuCash accounts to logical entities.
    
    Supports both explicit GUID-based mapping and regex pattern-based mapping
    against account full names.
    
    Attributes:
        version: Schema version of the entity map file.
        entities: Dictionary of entity definitions keyed by entity key.
        account_entities: Dictionary mapping account GUID to entity key.
        patterns: Dictionary mapping entity key to list of regex patterns
                 for matching account full names.
    """
    
    version: int = 1
    entities: dict[str, EntityDefinition] = field(default_factory=dict)
    account_entities: dict[str, str] = field(default_factory=dict)
    patterns: dict[str, list[str]] = field(default_factory=dict)
    
    # Compiled regex cache (not persisted)
    _compiled_patterns: dict[str, list[re.Pattern]] = field(
        default_factory=dict, init=False, repr=False
    )
    
    def __post_init__(self):
        """Compile regex patterns for efficient matching."""
        self._compile_patterns()
    
    def _compile_patterns(self) -> None:
        """Compile all regex patterns for performance."""
        self._compiled_patterns = {}
        for entity_key, pattern_list in self.patterns.items():
            compiled_list = []
            for pattern_str in pattern_list:
                try:
                    compiled_list.append(re.compile(pattern_str))
                except re.error as e:
                    logger.error(
                        f"Invalid regex pattern for entity '{entity_key}': "
                        f"'{pattern_str}' - {e}"
                    )
            self._compiled_patterns[entity_key] = compiled_list
    
    @classmethod
    def load(cls, path: Path) -> "EntityMap":
        """
        Load entity map from a JSON file.
        
        Args:
            path: Path to the entity-map.json file.
            
        Returns:
            EntityMap instance loaded from the file.
            
        Raises:
            FileNotFoundError: If the file does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
            KeyError: If required fields are missing.
        """
        logger.info(f"Loading entity map from {path}")
        
        if not path.exists():
            logger.warning(f"Entity map file not found: {path}")
            logger.warning("Starting with empty entity map")
            return cls()
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        version = data.get("version", 1)
        
        # Load entity definitions
        entities = {}
        for key, entity_data in data.get("entities", {}).items():
            entities[key] = EntityDefinition(
                key=key,
                label=entity_data["label"],
                type=entity_data["type"]
            )
        
        # Load account mappings
        account_entities = data.get("accounts", {})
        
        # Load patterns
        patterns = data.get("patterns", {})
        
        entity_map = cls(
            version=version,
            entities=entities,
            account_entities=account_entities,
            patterns=patterns
        )
        
        logger.info(
            f"Loaded {len(entities)} entities, "
            f"{len(account_entities)} account mappings, "
            f"{sum(len(p) for p in patterns.values())} patterns"
        )
        
        return entity_map
    
    def save(self, path: Path) -> None:
        """
        Save entity map to a JSON file.
        
        Args:
            path: Path where the entity-map.json file should be written.
        """
        logger.info(f"Saving entity map to {path}")
        
        data = {
            "version": self.version,
            "entities": {
                key: {
                    "label": entity.label,
                    "type": entity.type
                }
                for key, entity in self.entities.items()
            },
            "accounts": self.account_entities,
            "patterns": self.patterns
        }
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info("Entity map saved successfully")
    
    def resolve_entity_for_account(
        self, 
        guid: str, 
        full_name: str
    ) -> Optional[str]:
        """
        Resolve the entity key for a given account.
        
        Resolution order:
        1. Check explicit GUID mapping in account_entities
        2. Check pattern matching against full_name
        3. Return None if no match found
        
        Args:
            guid: The account GUID.
            full_name: The account's full name (e.g., "Assets:Checking:Alpha LLC").
            
        Returns:
            The entity key if found, None otherwise.
        """
        # First, check explicit GUID mapping
        if guid in self.account_entities:
            return self.account_entities[guid]
        
        # Second, check pattern matching
        for entity_key, pattern_list in self._compiled_patterns.items():
            for pattern in pattern_list:
                if pattern.search(full_name):
                    logger.debug(
                        f"Account '{full_name}' ({guid}) matched pattern "
                        f"for entity '{entity_key}'"
                    )
                    return entity_key
        
        # No match found
        return None
    
    def add_account_mapping(self, guid: str, entity_key: str) -> None:
        """
        Add or update an explicit account-to-entity mapping.
        
        Args:
            guid: The account GUID.
            entity_key: The entity key to map to.
            
        Raises:
            ValueError: If the entity_key does not exist in entities.
        """
        if entity_key not in self.entities:
            raise ValueError(
                f"Entity key '{entity_key}' not found in entity definitions"
            )
        
        self.account_entities[guid] = entity_key
        logger.debug(f"Mapped account {guid} to entity '{entity_key}'")
    
    def add_entity(
        self, 
        key: str, 
        label: str, 
        entity_type: str
    ) -> None:
        """
        Add a new entity definition.
        
        Args:
            key: Unique entity key.
            label: Human-readable label.
            entity_type: "individual" or "business".
            
        Raises:
            ValueError: If entity_type is invalid or key already exists.
        """
        if entity_type not in ("individual", "business"):
            raise ValueError(
                f"Invalid entity type: '{entity_type}'. "
                f"Must be 'individual' or 'business'."
            )
        
        if key in self.entities:
            raise ValueError(f"Entity key '{key}' already exists")
        
        self.entities[key] = EntityDefinition(
            key=key,
            label=label,
            type=entity_type
        )
        
        logger.info(f"Added new entity: '{key}' ({label})")
