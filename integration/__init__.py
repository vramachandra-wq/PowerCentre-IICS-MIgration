"""
Compatibility package for IICS integration components.
"""

from integration.iics_adapter import IICSAdapter
from integration.mock_iics_provider import MockIICSProvider
from integration.provider_factory import IICSProviderFactory
from integration.real_iics_provider import RealIICSProvider

__all__ = ["IICSAdapter", "MockIICSProvider", "RealIICSProvider", "IICSProviderFactory"]
