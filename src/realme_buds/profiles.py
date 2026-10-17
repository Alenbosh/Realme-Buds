from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Literal, cast


CompatibilityState = Literal["verified", "community_tested", "experimental"]


@dataclass(frozen=True)
class AncProfile:
    write_indices: dict[str, int]
    read_modes: dict[int, str]
    read_levels: dict[int, str]
    sequences: dict[str, int]

    def payload_for(self, mode: str) -> bytes:
        try:
            index = self.write_indices[mode]
        except KeyError as error:
            raise ValueError(f"ANC mode {mode!r} is not supported by this device profile") from error
        bitmap = 1 << index
        width = index // 8 + 1
        return b"\x01\x01" + bitmap.to_bytes(width, "little")

    def sequence_for(self, mode: str) -> int:
        return self.sequences.get(mode, 0x42)


@dataclass(frozen=True)
class EqPresetProfile:
    eq_id: int
    key: str
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class EqProfile:
    presets: tuple[EqPresetProfile, ...]
    supports_custom: bool
    write_verified: bool
    custom_write_verified: bool

    def preset_for(self, value: str) -> EqPresetProfile | None:
        normalized = value.strip().lower()
        return next((preset for preset in self.presets
                     if normalized in (preset.key, str(preset.eq_id), *preset.aliases)), None)


PRO_EQ_PRESETS = (
    EqPresetProfile(0, "balanced", "Balanced"),
    EqPresetProfile(1, "deep-sea-bass", "Deep Sea Bass"),
    EqPresetProfile(2, "pure-vocals", "Pure Vocals"),
    EqPresetProfile(3, "bright-and-crisp", "Bright & Crisp"),
)

PRO_2_EQ_PRESETS = (
    EqPresetProfile(0, "balanced", "Balanced"),
    EqPresetProfile(1, "bass", "Bass", ("deep-sea-bass",)),
    EqPresetProfile(2, "serenade", "Serenade", ("pure-vocals",)),
    EqPresetProfile(3, "bold", "Bold", ("bright-and-crisp",)),
    EqPresetProfile(7, "hans-zimmer-soundscape-tuning", "Hans Zimmer Soundscape Tuning"),
)

T310_EQ_PRESETS = (
    EqPresetProfile(0, "balanced", "Balanced"),
    EqPresetProfile(1, "bass", "Clear Bass", ("bass-boost", "deep-sea-bass")),
    EqPresetProfile(2, "vocals", "Clear Vocals", ("pure-vocals", "serenade")),
    EqPresetProfile(3, "bright", "Bright", ("bold", "bright-and-crisp")),
)


@dataclass(frozen=True)
class DeviceProfile:
    product_id: str
    name: str
    service_uuid: str
    anc: AncProfile
    eq: EqProfile | None
    capabilities: frozenset[str]
    compatibility: CompatibilityState
    channel: int = 15
    transport_type: str = "rfcomm"

    @property
    def verified(self) -> bool:
        """Keep hardware write gates explicit and backwards compatible."""
        return self.compatibility == "verified"

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceProfile:
        product_id = data.get("product_id")
        if not product_id or not isinstance(product_id, str):
            raise ValueError("DeviceProfile requires a valid string 'product_id'")

        name = data.get("name")
        if not name or not isinstance(name, str):
            raise ValueError("DeviceProfile requires a valid string 'name'")

        service_uuid = data.get("service_uuid")
        if not service_uuid or not isinstance(service_uuid, str):
            raise ValueError("DeviceProfile requires a valid string 'service_uuid'")

        anc_data = data.get("anc")
        if not isinstance(anc_data, dict):
            raise ValueError("DeviceProfile requires an 'anc' mapping")

        anc = AncProfile(
            write_indices=dict(anc_data.get("write_indices", {})),
            read_modes={int(k): v for k, v in anc_data.get("read_modes", {}).items()},
            read_levels={int(k): v for k, v in anc_data.get("read_levels", {}).items()},
            sequences=dict(anc_data.get("sequences", {})),
        )

        eq_data = data.get("eq")
        eq: EqProfile | None = None
        if eq_data is not None:
            if not isinstance(eq_data, dict):
                raise ValueError("DeviceProfile 'eq' must be a mapping or null")
            presets = tuple(
                EqPresetProfile(
                    eq_id=int(p["id"]),
                    key=str(p["key"]),
                    name=str(p["name"]),
                    aliases=tuple(p.get("aliases", ())),
                )
                for p in eq_data.get("presets", [])
            )
            eq = EqProfile(
                presets=presets,
                supports_custom=bool(eq_data.get("supports_custom", False)),
                write_verified=bool(eq_data.get("write_verified", False)),
                custom_write_verified=bool(eq_data.get("custom_write_verified", False)),
            )

        return cls(
            product_id=product_id.upper(),
            name=name,
            service_uuid=service_uuid.lower(),
            channel=int(data.get("channel", 15)),
            transport_type=str(data.get("transport_type", "rfcomm")),
            compatibility=cast(CompatibilityState, data.get("compatibility", "experimental")),
            capabilities=frozenset(data.get("capabilities", ())),
            anc=anc,
            eq=eq,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "product_id": self.product_id,
            "name": self.name,
            "service_uuid": self.service_uuid,
            "channel": self.channel,
            "transport_type": self.transport_type,
            "compatibility": self.compatibility,
            "capabilities": sorted(self.capabilities),
            "anc": {
                "write_indices": dict(self.anc.write_indices),
                "read_modes": {str(k): v for k, v in self.anc.read_modes.items()},
                "read_levels": {str(k): v for k, v in self.anc.read_levels.items()},
                "sequences": dict(self.anc.sequences),
            },
            "eq": None,
        }
        if self.eq is not None:
            result["eq"] = {
                "supports_custom": self.eq.supports_custom,
                "write_verified": self.eq.write_verified,
                "custom_write_verified": self.eq.custom_write_verified,
                "presets": [
                    {
                        "id": p.eq_id,
                        "key": p.key,
                        "name": p.name,
                        "aliases": list(p.aliases),
                    }
                    for p in self.eq.presets
                ],
            }
        return result


class DeviceRegistry:
    """Extensible registry for OPO-compatible device profiles."""

    def __init__(self) -> None:
        self._profiles: dict[str, DeviceProfile] = {}

    @property
    def profiles(self) -> dict[str, DeviceProfile]:
        return self._profiles

    def register(self, profile: DeviceProfile) -> None:
        self._profiles[profile.product_id.upper()] = profile

    def get(self, product_id: str | None) -> DeviceProfile | None:
        if not product_id:
            return None
        return self._profiles.get(product_id.upper())

    def all(self) -> list[DeviceProfile]:
        return list(self._profiles.values())

    def supported_product_ids(self) -> list[str]:
        return list(self._profiles.keys())

    def load_json(self, path: Path | str) -> DeviceProfile:
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        profile = DeviceProfile.from_dict(data)
        self.register(profile)
        return profile

    def load_directory(self, directory: Path | str) -> int:
        directory = Path(directory)
        count = 0
        if not directory.exists() or not directory.is_dir():
            return count
        for file in sorted(directory.glob("*.json")):
            try:
                self.load_json(file)
                count += 1
            except Exception:
                continue
        return count


REGISTRY = DeviceRegistry()

# Load declarative device profiles from built-in directory
DEVICES_DIR = Path(__file__).resolve().parent / "devices"
if DEVICES_DIR.exists():
    REGISTRY.load_directory(DEVICES_DIR)

# Fallback definitions to guarantee availability even without directory access
if not REGISTRY.get("060C14"):
    REGISTRY.register(
        DeviceProfile(
            product_id="060C14",
            name="OnePlus Buds Pro",
            service_uuid="00001107-d102-11e1-9b23-00025b00a5a5",
            anc=AncProfile(
                write_indices={"off": 0, "transparency": 1, "light": 2, "on": 3, "deep": 3, "smart": 4},
                read_modes={0: "off", 1: "transparency", 2: "on", 3: "on", 4: "on"},
                read_levels={2: "light", 3: "deep", 4: "smart"},
                sequences={"off": 0x40},
            ),
            eq=EqProfile(PRO_EQ_PRESETS, supports_custom=False, write_verified=True, custom_write_verified=False),
            capabilities=frozenset({
                "battery", "case_battery", "firmware", "anc", "transparency", "anc_levels", "smart_anc", "eq",
            }),
            compatibility="verified",
        )
    )

if not REGISTRY.get("062014"):
    REGISTRY.register(
        DeviceProfile(
            product_id="062014",
            name="OnePlus Buds Pro 2",
            service_uuid="0000079a-d102-11e1-9b23-00025b00a5a5",
            anc=AncProfile(
                write_indices={
                    "off": 0, "on": 1, "transparency": 2, "deep": 4, "medium": 5, "light": 6, "smart": 7,
                },
                read_modes={0: "off", 1: "on", 2: "transparency", 3: "off", 8: "transparency"},
                read_levels={4: "deep", 5: "medium", 6: "light", 7: "smart"},
                sequences={"off": 0x40},
            ),
            eq=EqProfile(PRO_2_EQ_PRESETS, supports_custom=True, write_verified=True, custom_write_verified=True),
            capabilities=frozenset({
                "battery", "case_battery", "firmware", "anc", "transparency", "anc_levels", "smart_anc", "eq", "custom_eq",
            }),
            compatibility="verified",
        )
    )

if not REGISTRY.get("063C12"):
    REGISTRY.register(
        DeviceProfile(
            product_id="063C12",
            name="realme Buds T310",
            service_uuid="0000079a-d102-11e1-9b23-00025b00a5a5",
            anc=AncProfile(
                write_indices={"off": 0, "transparency": 1, "on": 2},
                read_modes={0: "off", 1: "transparency", 2: "on", 3: "off"},
                read_levels={},
                sequences={"off": 0x40},
            ),
            eq=EqProfile(T310_EQ_PRESETS, supports_custom=False, write_verified=True, custom_write_verified=False),
            capabilities=frozenset({"battery", "case_battery", "firmware", "anc", "transparency", "eq"}),
            compatibility="verified",
            channel=1,
        )
    )

PROFILES: dict[str, DeviceProfile] = REGISTRY.profiles


def profile_for_product(product_id: str | None) -> DeviceProfile | None:
    if not product_id:
        return None
    return PROFILES.get(product_id) or PROFILES.get(product_id.upper())


def compatibility_for_product(product_id: str | None) -> CompatibilityState:
    profile = profile_for_product(product_id)
    return profile.compatibility if profile else "experimental"

