from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from realme_buds.profiles import (
    AncProfile,
    DeviceProfile,
    DeviceRegistry,
    EqPresetProfile,
    EqProfile,
    PROFILES,
    REGISTRY,
    compatibility_for_product,
    profile_for_product,
)


class DeviceRegistryTests(unittest.TestCase):
    def test_builtin_profiles_loaded(self):
        self.assertIn("063C12", REGISTRY.profiles)

        t310 = REGISTRY.get("063C12")
        self.assertIsNotNone(t310)
        self.assertEqual(t310.name, "realme Buds T310")
        self.assertEqual(t310.channel, 1)
        self.assertEqual(t310.compatibility, "verified")
        self.assertTrue(t310.has_capability("battery"))
        self.assertTrue(t310.has_capability("anc"))
        self.assertFalse(t310.has_capability("spatial_audio"))

    def test_registry_lookup_case_insensitivity(self):
        self.assertEqual(REGISTRY.get("063c12"), REGISTRY.get("063C12"))
        self.assertIsNone(REGISTRY.get(None))
        self.assertIsNone(REGISTRY.get(""))
        self.assertIsNone(REGISTRY.get("NONEXISTENT"))

    def test_registry_all_and_supported_product_ids(self):
        all_profiles = REGISTRY.all()
        ids = REGISTRY.supported_product_ids()
        self.assertGreaterEqual(len(all_profiles), 1)
        self.assertIn("063C12", ids)

    def test_device_profile_from_dict_and_to_dict_roundtrip(self):
        raw = {
            "product_id": "0699AA",
            "name": "realme Buds Test",
            "service_uuid": "0000079a-d102-11e1-9b23-00025b00a5a5",
            "channel": 1,
            "transport_type": "rfcomm",
            "compatibility": "verified",
            "capabilities": ["anc", "battery", "low_latency"],
            "anc": {
                "write_indices": {"off": 0, "on": 1},
                "read_modes": {"0": "off", "1": "on"},
                "read_levels": {},
                "sequences": {"off": 64},
            },
            "eq": {
                "supports_custom": False,
                "write_verified": True,
                "custom_write_verified": False,
                "presets": [
                    {"id": 0, "key": "balanced", "name": "Balanced", "aliases": []},
                    {"id": 1, "key": "bass", "name": "Bass", "aliases": ["deep-bass"]},
                ],
            },
        }
        profile = DeviceProfile.from_dict(raw)
        self.assertEqual(profile.product_id, "0699AA")
        self.assertEqual(profile.name, "realme Buds Test")
        self.assertEqual(profile.channel, 1)
        self.assertEqual(profile.transport_type, "rfcomm")
        self.assertTrue(profile.has_capability("low_latency"))
        self.assertFalse(profile.has_capability("multipoint"))
        self.assertEqual(profile.anc.write_indices["off"], 0)
        self.assertEqual(profile.anc.read_modes[1], "on")
        self.assertIsNotNone(profile.eq)
        self.assertEqual(len(profile.eq.presets), 2)
        self.assertEqual(profile.eq.presets[1].aliases, ("deep-bass",))

        exported = profile.to_dict()
        self.assertEqual(exported["product_id"], "0699AA")
        self.assertEqual(exported["capabilities"], ["anc", "battery", "low_latency"])
        self.assertEqual(exported["anc"]["write_indices"], {"off": 0, "on": 1})
        self.assertEqual(exported["anc"]["read_modes"], {"0": "off", "1": "on"})

    def test_device_profile_validation_errors(self):
        base = {
            "product_id": "060000",
            "name": "Test",
            "service_uuid": "0000079a-d102-11e1-9b23-00025b00a5a5",
            "anc": {
                "write_indices": {},
                "read_modes": {},
                "read_levels": {},
                "sequences": {},
            },
        }

        # Missing product_id
        data = dict(base)
        data.pop("product_id")
        with self.assertRaises(ValueError):
            DeviceProfile.from_dict(data)

        # Missing name
        data = dict(base)
        data.pop("name")
        with self.assertRaises(ValueError):
            DeviceProfile.from_dict(data)

        # Missing service_uuid
        data = dict(base)
        data.pop("service_uuid")
        with self.assertRaises(ValueError):
            DeviceProfile.from_dict(data)

        # Missing anc
        data = dict(base)
        data.pop("anc")
        with self.assertRaises(ValueError):
            DeviceProfile.from_dict(data)

        # Invalid eq
        data = dict(base)
        data["eq"] = "not a dict"
        with self.assertRaises(ValueError):
            DeviceProfile.from_dict(data)

    def test_load_directory_and_load_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            valid_file = temp_path / "valid.json"
            valid_file.write_text(
                json.dumps({
                    "product_id": "06AAAA",
                    "name": "Temp Earbuds",
                    "service_uuid": "0000079a-d102-11e1-9b23-00025b00a5a5",
                    "anc": {"write_indices": {}, "read_modes": {}, "read_levels": {}, "sequences": {}},
                })
            )
            invalid_file = temp_path / "invalid.json"
            invalid_file.write_text("{ broken json }")

            registry = DeviceRegistry()
            loaded = registry.load_directory(temp_path)
            self.assertEqual(loaded, 1)
            self.assertIsNotNone(registry.get("06AAAA"))
            self.assertEqual(registry.get("06AAAA").name, "Temp Earbuds")

            # Nonexistent dir returns 0
            self.assertEqual(registry.load_directory(temp_path / "nonexistent"), 0)

    def test_backward_compatibility_profiles_and_patching(self):
        self.assertIn("063C12", PROFILES)
        self.assertEqual(profile_for_product("063C12"), REGISTRY.get("063C12"))
        self.assertEqual(profile_for_product("063c12"), REGISTRY.get("063C12"))
        self.assertEqual(compatibility_for_product("063C12"), "verified")
        self.assertEqual(compatibility_for_product("UNKNOWN_ID"), "experimental")

        dummy_profile = DeviceProfile(
            product_id="999999",
            name="Mocked Bud",
            service_uuid="0000079a-d102-11e1-9b23-00025b00a5a5",
            anc=AncProfile({}, {}, {}, {}),
            eq=None,
            capabilities=frozenset(),
            compatibility="community_tested",
        )
        with patch.dict(PROFILES, {"999999": dummy_profile}):
            self.assertEqual(profile_for_product("999999"), dummy_profile)
            self.assertEqual(compatibility_for_product("999999"), "community_tested")
            self.assertEqual(REGISTRY.get("999999"), dummy_profile)


if __name__ == "__main__":
    unittest.main()
