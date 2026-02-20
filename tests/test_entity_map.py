"""Tests for gcgaap.entity_map."""

import json
import logging

import pytest

from gcgaap.entity_map import EntityDefinition, EntityMap


# ---------------------------------------------------------------------------
# EntityDefinition
# ---------------------------------------------------------------------------


class TestEntityDefinition:
    def test_individual_type(self):
        ed = EntityDefinition(key="personal", label="Personal", type="individual")
        assert ed.key == "personal"
        assert ed.label == "Personal"
        assert ed.type == "individual"

    def test_business_type(self):
        ed = EntityDefinition(key="my_llc", label="My LLC", type="business")
        assert ed.type == "business"

    def test_structural_type(self):
        ed = EntityDefinition(key="placeholder", label="Placeholder", type="structural")
        assert ed.type == "structural"

    def test_unknown_type_logs_warning_and_does_not_raise(self, caplog):
        with caplog.at_level(logging.WARNING, logger="gcgaap.entity_map"):
            ed = EntityDefinition(key="x", label="X", type="weird_type")

        assert "unexpected type" in caplog.text
        assert ed.type == "weird_type"  # object is still created


# ---------------------------------------------------------------------------
# EntityMap construction
# ---------------------------------------------------------------------------


class TestEntityMapConstruction:
    def test_empty_map_creates_unassigned_entity(self):
        """An empty EntityMap always gets an 'unassigned' entity via __post_init__."""
        em = EntityMap()
        assert "unassigned" in em.entities
        assert em.default_entity == "unassigned"
        assert em.account_entities == {}

    def test_unassigned_entity_type_is_individual(self):
        em = EntityMap()
        assert em.entities["unassigned"].type == "individual"

    def test_default_entity_added_when_absent(self):
        """If entities dict is provided but default_entity key is missing, it is added."""
        entities = {"personal": EntityDefinition("personal", "Personal", "individual")}
        em = EntityMap(entities=entities)
        assert "unassigned" in em.entities

    def test_existing_entities_preserved(self):
        entities = {
            "personal": EntityDefinition("personal", "Personal", "individual"),
            "unassigned": EntityDefinition("unassigned", "Unassigned", "individual"),
        }
        em = EntityMap(entities=entities)
        assert "personal" in em.entities
        assert "unassigned" in em.entities

    def test_account_entities_mapping(self):
        em = EntityMap(account_entities={"guid-abc": "personal"})
        assert em.account_entities["guid-abc"] == "personal"


# ---------------------------------------------------------------------------
# EntityMap.resolve_entity_for_account
# ---------------------------------------------------------------------------


class TestResolveEntityForAccount:
    def test_returns_mapped_entity(self):
        em = EntityMap(
            entities={
                "personal": EntityDefinition("personal", "Personal", "individual"),
                "unassigned": EntityDefinition("unassigned", "Unassigned", "individual"),
            },
            account_entities={"guid-001": "personal"},
        )
        assert em.resolve_entity_for_account("guid-001", "Assets:Checking") == "personal"

    def test_falls_back_to_default_entity(self):
        em = EntityMap()
        result = em.resolve_entity_for_account("unknown-guid", "Income:Other")
        assert result == "unassigned"

    def test_different_entities_resolved_correctly(self):
        em = EntityMap(
            entities={
                "personal": EntityDefinition("personal", "Personal", "individual"),
                "business": EntityDefinition("business", "Business", "business"),
                "unassigned": EntityDefinition("unassigned", "Unassigned", "individual"),
            },
            account_entities={
                "guid-pers": "personal",
                "guid-biz": "business",
            },
        )
        assert em.resolve_entity_for_account("guid-pers", "Assets:Personal") == "personal"
        assert em.resolve_entity_for_account("guid-biz", "Assets:Business") == "business"
        assert em.resolve_entity_for_account("guid-other", "Assets:Other") == "unassigned"


# ---------------------------------------------------------------------------
# EntityMap.is_explicitly_mapped
# ---------------------------------------------------------------------------


class TestIsExplicitlyMapped:
    def test_mapped_guid_returns_true(self):
        em = EntityMap(account_entities={"guid-mapped": "personal"})
        assert em.is_explicitly_mapped("guid-mapped", "Assets:Checking") is True

    def test_unmapped_guid_returns_false(self):
        em = EntityMap()
        assert em.is_explicitly_mapped("guid-unmapped", "Assets:Checking") is False

    def test_full_name_not_used_for_lookup(self):
        """is_explicitly_mapped checks GUID only; full_name is ignored."""
        em = EntityMap(account_entities={"guid-x": "personal"})
        # Same GUID, different full_name → still True
        assert em.is_explicitly_mapped("guid-x", "Completely Different Name") is True


# ---------------------------------------------------------------------------
# EntityMap.load
# ---------------------------------------------------------------------------


class TestEntityMapLoad:
    def test_returns_empty_map_when_file_missing(self, tmp_path):
        """Missing file produces an empty EntityMap rather than raising."""
        em = EntityMap.load(tmp_path / "nonexistent.json")
        assert "unassigned" in em.entities
        assert em.account_entities == {}

    def test_loads_entities_and_account_mappings(self, tmp_path):
        data = {
            "summary": {
                "entity_labels": {
                    "personal": "Personal Accounts",
                    "alpha_llc": "Alpha LLC",
                },
                "entity_counts": {"personal": 2, "alpha_llc": 1},
            },
            "entities": {
                "personal": [
                    {"guid": "acc-001", "name": "Assets:Checking"},
                    {"guid": "acc-002", "name": "Income:Salary"},
                ],
                "alpha_llc": [
                    {"guid": "acc-003", "name": "Assets:Business"},
                ],
            },
        }
        json_path = tmp_path / "entity_account_map.json"
        json_path.write_text(json.dumps(data))

        em = EntityMap.load(json_path)

        assert "personal" in em.entities
        assert "alpha_llc" in em.entities
        assert em.entities["personal"].label == "Personal Accounts"
        assert em.entities["alpha_llc"].label == "Alpha LLC"

        assert em.account_entities["acc-001"] == "personal"
        assert em.account_entities["acc-002"] == "personal"
        assert em.account_entities["acc-003"] == "alpha_llc"

    def test_entity_types_inferred_from_key(self, tmp_path):
        """'personal' → individual, others → business, 'placeholder_only_acct' → structural."""
        data = {
            "summary": {
                "entity_labels": {
                    "personal": "Personal",
                    "my_corp": "My Corp",
                    "placeholder_only_acct": "Placeholder",
                },
                "entity_counts": {},
            },
            "entities": {
                "personal": [],
                "my_corp": [],
                "placeholder_only_acct": [],
            },
        }
        json_path = tmp_path / "map.json"
        json_path.write_text(json.dumps(data))

        em = EntityMap.load(json_path)

        assert em.entities["personal"].type == "individual"
        assert em.entities["my_corp"].type == "business"
        assert em.entities["placeholder_only_acct"].type == "structural"

    def test_default_entity_is_unassigned_when_present(self, tmp_path):
        """When 'unassigned' key is in the data, it becomes default_entity."""
        data = {
            "summary": {
                "entity_labels": {"unassigned": "Unassigned"},
                "entity_counts": {},
            },
            "entities": {
                "unassigned": [{"guid": "acc-x", "name": "Some Account"}],
            },
        }
        json_path = tmp_path / "map.json"
        json_path.write_text(json.dumps(data))

        em = EntityMap.load(json_path)
        assert em.default_entity == "unassigned"

    def test_label_defaults_to_title_cased_key(self, tmp_path):
        """When a key has no label in entity_labels, the key is title-cased."""
        data = {
            "summary": {
                "entity_labels": {},  # no labels provided
                "entity_counts": {},
            },
            "entities": {
                "my_business": [],
            },
        }
        json_path = tmp_path / "map.json"
        json_path.write_text(json.dumps(data))

        em = EntityMap.load(json_path)
        # key "my_business" → label "My Business"
        assert em.entities["my_business"].label == "My Business"
