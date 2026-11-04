"""Bridge to native Google authorization and device secure storage."""

import flet as ft


@ft.control("TrailManiaDrive")
class GoogleDriveAuth(ft.Service):
    """Keep Google credentials on the device, outside the SQLite database."""

    async def restore(self) -> dict:
        """Read the saved authorization without requiring network access."""
        return await self._invoke_method("restore", timeout=15)

    async def connect(self, server_client_id: str) -> dict:
        """Ask the native Google SDK to authenticate and authorize app data."""
        return await self._invoke_method(
            "connect", {"server_client_id": server_client_id}, timeout=300,
        )

    async def access_token(self, server_client_id: str) -> dict:
        """Get an access token silently; report when consent is required again."""
        return await self._invoke_method(
            "access_token", {"server_client_id": server_client_id}, timeout=30,
        )
