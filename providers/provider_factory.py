"""
Factory for selecting IICS provider implementations.
"""

from __future__ import annotations

import os

from providers.iics_provider import IICSProvider
from providers.mock_iics_provider import MockIICSProvider
from providers.real_iics_provider import RealIICSProvider


class IICSProviderFactory:
    """Creates configured IICS providers."""

    @staticmethod
    def create(provider_name: str | None = None) -> IICSProvider:
        """Return the requested provider, defaulting to mock."""

        selected = (provider_name or os.getenv("IICS_PROVIDER", "mock")).strip().lower()
        if selected == "real":
            return RealIICSProvider()
        return MockIICSProvider()
