"""Compatibility shim for historical license-gating hooks.

This fork currently treats all capabilities as available by default while still
providing the module surface expected by older code and tests.
"""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class LicenseService:
    current_license: Dict[str, Any] = field(default_factory=dict)

    def has_capability(self, capability: str) -> bool:
        capabilities = self.current_license.get("capabilities")
        if isinstance(capabilities, (list, tuple, set, frozenset)):
            return capability in capabilities
        return True


license_service = LicenseService()


def has_capability(capability: str) -> bool:
    return license_service.has_capability(capability)