"""Device management subsystem for physical and virtual Android devices."""

from droiddesk.device.discovery import DeviceDiscoveryService
from droiddesk.device.models import DeviceType, ManagedDevice

__all__ = ["DeviceDiscoveryService", "DeviceType", "ManagedDevice"]
