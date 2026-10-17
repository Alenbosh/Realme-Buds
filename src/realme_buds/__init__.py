"""Native realme earbuds control for Linux & Omarchy."""

__version__ = "0.1.0"


from .api import BudsBackend
from .bridge import BudsFrontendBridge, serialize_snapshot
from .controller import BudsController
from .profiles import (
    DeviceProfile,
    DeviceRegistry,
    PROFILES,
    REGISTRY,
    compatibility_for_product,
    profile_for_product,
)
from .service import BudsServiceRunner, ServiceState
from .transport import RfcommTransport, Transport, create_transport

__all__ = [
    "BudsBackend",
    "BudsController",
    "BudsFrontendBridge",
    "BudsServiceRunner",
    "DeviceProfile",
    "DeviceRegistry",
    "PROFILES",
    "REGISTRY",
    "RfcommTransport",
    "ServiceState",
    "Transport",
    "compatibility_for_product",
    "create_transport",
    "profile_for_product",
    "serialize_snapshot",
    "__version__",
]


