"""
Smart entity inference using pattern analysis.

Analyzes GnuCash account names to intelligently suggest entity groupings
and generate entity mapping configurations.
"""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .gnucash_access import GCAccount, GnuCashBook

logger = logging.getLogger(__name__)


@dataclass
class EntitySuggestion:
    """
    A suggested entity discovered through account analysis.
    
    Attributes:
        key: Suggested entity key (e.g., "alpha_llc").
        label: Human-readable label.
        type: Suggested type ("business" or "individual").
        confidence: Confidence score (0.0 to 1.0).
        account_count: Number of accounts that would map to this entity.
        sample_accounts: Sample account names for this entity.
        suggested_patterns: Suggested regex patterns for matching.
    """
    
    key: str
    label: str
    type: str  # "business" or "individual"
    confidence: float
    account_count: int
    sample_accounts: list[str] = field(default_factory=list)
    suggested_patterns: list[str] = field(default_factory=list)


@dataclass
class InferenceResult:
    """
    Results from entity inference analysis.
    
    Attributes:
        suggestions: List of entity suggestions.
        unmapped_accounts: Accounts that don't fit any pattern.
        analysis_notes: Additional analysis observations.
    """
    
    suggestions: list[EntitySuggestion] = field(default_factory=list)
    unmapped_accounts: list[GCAccount] = field(default_factory=list)
    analysis_notes: list[str] = field(default_factory=list)


class EntityInferenceEngine:
    """
    Analyzes account names to infer logical entity groupings.
    
    Uses pattern matching, common business/personal account structures,
    and heuristics to suggest entity definitions.
    """
    
    def __init__(self):
        """Initialize the inference engine."""
        self.accounts = []
        
        # Common business indicators
        self.business_indicators = [
            r'\bLLC\b', r'\bInc\b', r'\bCorp\b', r'\bLtd\b',
            r'\bCompany\b', r'\bBusiness\b', r'\bEnterprise\b',
            r'\bPartners\b', r'\bAssociates\b'
        ]
        
        # Common personal indicators  
        self.personal_indicators = [
            r'\bPersonal\b', r'\bFamily\b', r'\bHome\b',
            r'\bIndividual\b', r'\bPrivate\b'
        ]
    
    def analyze_book(self, book: GnuCashBook) -> InferenceResult:
        """
        Analyze a GnuCash book and infer entity groupings.
        
        Args:
            book: Opened GnuCashBook to analyze.
            
        Returns:
            InferenceResult with entity suggestions.
        """
        logger.info("Starting smart entity inference")
        
        # Collect all accounts
        self.accounts = list(book.iter_accounts())
        logger.info(f"Analyzing {len(self.accounts)} accounts")
        
        result = InferenceResult()
        
        # Step 1: Identify account path segments
        path_analysis = self._analyze_account_paths()
        
        # Step 2: Detect business entities
        business_entities = self._detect_business_entities()
        
        # Step 3: Detect personal entity
        personal_entity = self._detect_personal_entity()
        
        # Step 4: Combine suggestions
        all_suggestions = business_entities + ([personal_entity] if personal_entity else [])
        
        # Step 5: Validate and score suggestions
        for suggestion in all_suggestions:
            self._score_suggestion(suggestion)
        
        # Sort by confidence (highest first)
        all_suggestions.sort(key=lambda s: s.confidence, reverse=True)
        
        result.suggestions = all_suggestions
        
        # Identify unmapped accounts
        result.unmapped_accounts = self._find_unmapped_accounts(all_suggestions)
        
        # Add analysis notes
        result.analysis_notes = self._generate_analysis_notes(path_analysis, all_suggestions)
        
        logger.info(f"Inference complete: found {len(all_suggestions)} entity suggestions")
        
        return result
    
    def _analyze_account_paths(self) -> dict:
        """
        Analyze account path structures to find common patterns.
        
        Returns:
            Dictionary with path analysis statistics.
        """
        path_segments = defaultdict(int)
        depth_counts = defaultdict(int)
        
        for account in self.accounts:
            parts = account.full_name.split(':')
            depth_counts[len(parts)] += 1
            
            for i, part in enumerate(parts):
                path_segments[f"{i}:{part}"] += 1
        
        return {
            'segments': path_segments,
            'depths': depth_counts,
            'max_depth': max(depth_counts.keys()) if depth_counts else 0
        }
    
    def _detect_business_entities(self) -> list[EntitySuggestion]:
        """
        Detect business entities by looking for business names in account paths.
        
        Returns:
            List of business entity suggestions.
        """
        suggestions = []
        
        # Group accounts by potential business name
        business_groups = defaultdict(list)
        
        for account in self.accounts:
            # Look for business indicators in account name
            business_name = self._extract_business_name(account.full_name)
            
            if business_name:
                business_groups[business_name].append(account)
        
        # Create suggestions for each business group
        for business_name, accounts in business_groups.items():
            if len(accounts) < 2:  # Need at least 2 accounts to be meaningful
                continue
            
            # Generate entity key (lowercase, underscores)
            entity_key = self._generate_entity_key(business_name)
            
            # Determine patterns
            patterns = self._generate_patterns(business_name, accounts)
            
            # Sample accounts (up to 5)
            samples = [acc.full_name for acc in accounts[:5]]
            
            suggestion = EntitySuggestion(
                key=entity_key,
                label=business_name,
                type="business",
                confidence=0.0,  # Will be scored later
                account_count=len(accounts),
                sample_accounts=samples,
                suggested_patterns=patterns
            )
            
            suggestions.append(suggestion)
        
        return suggestions
    
    def _detect_personal_entity(self) -> Optional[EntitySuggestion]:
        """
        Detect personal/individual entity.
        
        Returns:
            EntitySuggestion for personal entity, or None.
        """
        personal_accounts = []
        
        for account in self.accounts:
            # Check for personal indicators
            if self._is_likely_personal(account.full_name):
                personal_accounts.append(account)
        
        if len(personal_accounts) < 2:
            return None
        
        # Generate patterns
        patterns = []
        for keyword in ['Personal', 'Family', 'Home', 'Individual']:
            if any(keyword in acc.full_name for acc in personal_accounts):
                patterns.append(f"^Assets:{keyword}.*")
                patterns.append(f"^Liabilities:{keyword}.*")
                patterns.append(f"^Equity:{keyword}.*")
        
        # Remove duplicates
        patterns = list(set(patterns))
        
        samples = [acc.full_name for acc in personal_accounts[:5]]
        
        suggestion = EntitySuggestion(
            key="personal",
            label="Personal Finances",
            type="individual",
            confidence=0.0,  # Will be scored later
            account_count=len(personal_accounts),
            sample_accounts=samples,
            suggested_patterns=patterns
        )
        
        return suggestion
    
    def _extract_business_name(self, account_path: str) -> Optional[str]:
        """
        Extract business name from account path if present.
        
        Args:
            account_path: Full account path (colon-separated).
            
        Returns:
            Business name if found, None otherwise.
        """
        # Look for business indicators
        for pattern in self.business_indicators:
            match = re.search(pattern, account_path, re.IGNORECASE)
            if match:
                # Try to extract the full business name around the match
                parts = account_path.split(':')
                for part in parts:
                    if re.search(pattern, part, re.IGNORECASE):
                        return part.strip()
        
        # Look for common business account structures
        # e.g., "Assets:Business:XYZ Corp" or "Assets:XYZ LLC:Checking"
        parts = account_path.split(':')
        for i, part in enumerate(parts):
            # Check if this segment contains business keywords
            if 'Business' in part and i + 1 < len(parts):
                # Next segment might be the business name
                return parts[i + 1].strip()
            
            # Check if segment itself looks like a business name
            if any(re.search(ind, part, re.IGNORECASE) for ind in self.business_indicators):
                return part.strip()
        
        return None
    
    def _is_likely_personal(self, account_path: str) -> bool:
        """
        Check if an account path likely belongs to personal finances.
        
        Args:
            account_path: Full account path.
            
        Returns:
            True if likely personal, False otherwise.
        """
        for pattern in self.personal_indicators:
            if re.search(pattern, account_path, re.IGNORECASE):
                return True
        return False
    
    def _generate_entity_key(self, name: str) -> str:
        """
        Generate a valid entity key from a name.
        
        Args:
            name: Entity name.
            
        Returns:
            Valid entity key (lowercase, underscores).
        """
        # Remove special characters, convert to lowercase
        key = re.sub(r'[^\w\s]', '', name)
        key = re.sub(r'\s+', '_', key)
        key = key.lower().strip('_')
        
        # Limit length
        if len(key) > 30:
            key = key[:30]
        
        return key
    
    def _generate_patterns(
        self, 
        entity_name: str, 
        accounts: list[GCAccount]
    ) -> list[str]:
        """
        Generate regex patterns for matching accounts to an entity.
        
        Args:
            entity_name: Name of the entity.
            accounts: Sample accounts for this entity.
            
        Returns:
            List of regex patterns.
        """
        patterns = []
        
        # Escape special regex characters in entity name
        escaped_name = re.escape(entity_name)
        
        # Common account type prefixes
        account_types = ['Assets', 'Liabilities', 'Equity', 'Income', 'Expenses']
        
        # Generate patterns like "^Assets:.*EntityName.*"
        for acc_type in account_types:
            # Check if any accounts actually use this pattern
            if any(acc.full_name.startswith(f"{acc_type}:") and entity_name in acc.full_name 
                   for acc in accounts):
                patterns.append(f"^{acc_type}:.*{escaped_name}.*")
        
        # Look for common path positions
        # e.g., if entity appears in 2nd position: "Assets:EntityName:..."
        entity_positions = defaultdict(int)
        for account in accounts:
            parts = account.full_name.split(':')
            for i, part in enumerate(parts):
                if entity_name in part:
                    entity_positions[i] += 1
        
        # If entity consistently appears in a specific position, create targeted pattern
        for position, count in entity_positions.items():
            if count >= len(accounts) * 0.5:  # 50% threshold
                # Create pattern for this position
                if position == 1:
                    patterns.append(f"^[^:]+:{escaped_name}.*")
                elif position == 2:
                    patterns.append(f"^[^:]+:[^:]+:{escaped_name}.*")
        
        # Remove duplicates
        patterns = list(set(patterns))
        
        return patterns
    
    def _score_suggestion(self, suggestion: EntitySuggestion) -> None:
        """
        Calculate confidence score for a suggestion.
        
        Args:
            suggestion: EntitySuggestion to score (modified in place).
        """
        score = 0.0
        
        # Base score from account count
        if suggestion.account_count >= 10:
            score += 0.4
        elif suggestion.account_count >= 5:
            score += 0.3
        elif suggestion.account_count >= 2:
            score += 0.2
        
        # Bonus for having clear patterns
        if suggestion.suggested_patterns:
            score += 0.2
        
        # Bonus for business type with business indicators
        if suggestion.type == "business":
            for pattern in self.business_indicators:
                if any(re.search(pattern, acc, re.IGNORECASE) 
                       for acc in suggestion.sample_accounts):
                    score += 0.2
                    break
        
        # Bonus for personal type with personal indicators
        if suggestion.type == "individual":
            for pattern in self.personal_indicators:
                if any(re.search(pattern, acc, re.IGNORECASE) 
                       for acc in suggestion.sample_accounts):
                    score += 0.2
                    break
        
        # Cap at 1.0
        suggestion.confidence = min(score, 1.0)
    
    def _find_unmapped_accounts(
        self, 
        suggestions: list[EntitySuggestion]
    ) -> list[GCAccount]:
        """
        Find accounts that don't match any suggested entity.
        
        Args:
            suggestions: List of entity suggestions.
            
        Returns:
            List of unmapped accounts.
        """
        unmapped = []
        
        # Compile all patterns
        compiled_patterns = []
        for suggestion in suggestions:
            for pattern_str in suggestion.suggested_patterns:
                try:
                    compiled_patterns.append(re.compile(pattern_str))
                except re.error:
                    logger.warning(f"Invalid regex pattern: {pattern_str}")
        
        # Check each account
        for account in self.accounts:
            matched = False
            for pattern in compiled_patterns:
                if pattern.search(account.full_name):
                    matched = True
                    break
            
            if not matched:
                unmapped.append(account)
        
        return unmapped
    
    def _generate_analysis_notes(
        self, 
        path_analysis: dict,
        suggestions: list[EntitySuggestion]
    ) -> list[str]:
        """
        Generate human-readable analysis notes.
        
        Args:
            path_analysis: Path analysis results.
            suggestions: Entity suggestions.
            
        Returns:
            List of note strings.
        """
        notes = []
        
        notes.append(f"Analyzed {len(self.accounts)} total accounts")
        notes.append(f"Maximum account depth: {path_analysis['max_depth']} levels")
        notes.append(f"Identified {len(suggestions)} potential entities")
        
        business_count = sum(1 for s in suggestions if s.type == "business")
        personal_count = sum(1 for s in suggestions if s.type == "individual")
        
        notes.append(f"  - {business_count} business entit{'y' if business_count == 1 else 'ies'}")
        notes.append(f"  - {personal_count} personal entit{'y' if personal_count == 1 else 'ies'}")
        
        # Confidence distribution
        high_conf = sum(1 for s in suggestions if s.confidence >= 0.7)
        med_conf = sum(1 for s in suggestions if 0.4 <= s.confidence < 0.7)
        low_conf = sum(1 for s in suggestions if s.confidence < 0.4)
        
        notes.append(f"Confidence levels: {high_conf} high, {med_conf} medium, {low_conf} low")
        
        return notes


def build_entity_map_from_suggestions(suggestions: list) -> "EntityMap":
    """
    Build an EntityMap from inference suggestions.

    Args:
        suggestions: List of EntitySuggestion objects.

    Returns:
        EntityMap with suggested entities and patterns.
    """
    from .entity_map import EntityMap, EntityDefinition

    entity_map = EntityMap()

    for suggestion in suggestions:
        # Add entity definition
        entity_map.entities[suggestion.key] = EntityDefinition(
            key=suggestion.key,
            label=suggestion.label,
            type=suggestion.type
        )

        # Add patterns
        if suggestion.suggested_patterns:
            entity_map.patterns[suggestion.key] = suggestion.suggested_patterns

    # Recompile patterns
    entity_map._compile_patterns()

    return entity_map


def merge_entity_maps(existing: "EntityMap", suggested: "EntityMap") -> "EntityMap":
    """
    Merge suggested entity map with existing one.

    Args:
        existing: Existing EntityMap.
        suggested: Suggested EntityMap.

    Returns:
        Merged EntityMap (keeps existing, adds new suggestions).
    """
    from .entity_map import EntityMap

    merged = EntityMap(
        version=existing.version,
        entities=dict(existing.entities),
        account_entities=dict(existing.account_entities),
        patterns=dict(existing.patterns)
    )

    # Add new entities (don't overwrite existing)
    for key, entity in suggested.entities.items():
        if key not in merged.entities:
            merged.entities[key] = entity
            logger.info(f"Added new entity: {key}")

    # Add new patterns (merge lists for existing entities)
    for key, patterns in suggested.patterns.items():
        if key in merged.patterns:
            # Merge pattern lists, avoiding duplicates
            existing_patterns = set(merged.patterns[key])
            new_patterns = [p for p in patterns if p not in existing_patterns]
            if new_patterns:
                merged.patterns[key].extend(new_patterns)
                logger.info(f"Added {len(new_patterns)} new pattern(s) for entity: {key}")
        else:
            merged.patterns[key] = patterns
            logger.info(f"Added patterns for new entity: {key}")

    # Recompile patterns
    merged._compile_patterns()

    return merged
