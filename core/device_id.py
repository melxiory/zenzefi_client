"""
Device ID generation for Zenzefi Desktop Client.

Device ID is based on hardware fingerprint and remains stable across app restarts
on the same computer, but differs between different computers.

This enables "1 token = 1 device" policy enforcement on the backend.
"""

import hashlib
import platform
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_device_id() -> str:
    """
    Generate stable Device ID based on hardware fingerprint.

    Device ID remains the same across app restarts on the same PC,
    but differs on different computers.

    Format: sha256 hash (first 20 chars) of hardware characteristics

    Returns:
        str: Hardware-based Device ID (e.g., "a1b2c3d4e5f6g7h8i9j0")

    Raises:
        RuntimeError: If device ID generation fails (critical error)
    """
    try:
        # Collect hardware characteristics
        hardware_components = [
            platform.node(),        # Computer name
            platform.machine(),     # Machine type (e.g., AMD64, x86_64)
            platform.processor(),   # Processor info
            platform.system(),      # OS name (Windows)
        ]

        # Create string from characteristics
        hardware_string = "-".join(filter(None, hardware_components))

        if not hardware_string:
            raise ValueError("Failed to collect hardware information")

        # Generate SHA256 hash
        device_hash = hashlib.sha256(hardware_string.encode('utf-8')).hexdigest()

        # Take first 20 characters (compact format)
        device_id = device_hash[:20]

        logger.debug(f"Device ID generated: {device_id}")
        logger.debug(f"Hardware: {platform.node()} ({platform.system()} {platform.machine()})")

        return device_id

    except Exception as e:
        error_msg = f"Critical error: failed to generate Device ID - {str(e)}"
        logger.error(f"❌ {error_msg}")
        raise RuntimeError(error_msg) from e


def validate_device_id(device_id: Optional[str]) -> bool:
    """
    Validate device ID format.

    Args:
        device_id: Device ID to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not device_id:
        return False

    if not isinstance(device_id, str):
        return False

    if len(device_id) < 8 or len(device_id) > 255:
        return False

    return True
