"""CertStream WebSocket client for real-time Certificate Transparency monitoring.

Connects to the CertStream server and filters for .br domains.
Uses websocket-client (sync) with auto-reconnect and exponential backoff.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Callable

import websocket

from app.core.config import settings

logger = logging.getLogger(__name__)


class CertStreamClient:
    """Persistent WebSocket client that streams CT Log events filtered by suffix."""

    def __init__(
        self,
        on_domains_callback: Callable[[list[str]], None],
        *,
        filter_suffix: str = ".br",
        url: str | None = None,
        max_backoff: int | None = None,
    ) -> None:
        self._callback = on_domains_callback
        self._filter_suffix = filter_suffix
        self._url = url or settings.CT_CERTSTREAM_URL
        self._max_backoff = max_backoff or settings.CT_CERTSTREAM_RECONNECT_MAX_BACKOFF
        self._ws_app: websocket.WebSocketApp | None = None
        self._running = True
        self._backoff = 1

    def start(self) -> None:
        """Connect and listen. Blocks the calling thread. Auto-reconnects on failure."""
        logger.info(
            "CertStream client starting: url=%s filter=%s",
            self._url, self._filter_suffix,
        )

        while self._running:
            try:
                self._ws_app = websocket.WebSocketApp(
                    self._url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open,
                )
                self._ws_app.run_forever(
                    ping_interval=15,
                    ping_timeout=10,
                )
            except Exception:
                logger.exception("CertStream connection error")

            if not self._running:
                break

            logger.info(
                "CertStream reconnecting in %ds...", self._backoff,
            )
            time.sleep(self._backoff)
            self._backoff = min(self._backoff * 2, self._max_backoff)

    def stop(self) -> None:
        """Signal the client to stop and close the connection."""
        self._running = False
        if self._ws_app:
            self._ws_app.close()

    def _on_open(self, ws) -> None:
        logger.info("CertStream connected to %s", self._url)
        self._backoff = 1  # Reset backoff on successful connection

    def _on_message(self, ws, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        if data.get("message_type") != "certificate_update":
            return

        leaf_cert = data.get("data", {}).get("leaf_cert", {})
        all_domains = leaf_cert.get("all_domains", [])

        if not all_domains:
            return

        # Filter for .br domains at the earliest stage
        br_domains = [
            d for d in all_domains
            if isinstance(d, str) and d.lower().endswith(self._filter_suffix)
        ]

        if br_domains:
            self._callback(br_domains)

    def _on_error(self, ws, error) -> None:
        logger.warning("CertStream error: %s", error)

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        logger.info(
            "CertStream closed: status=%s msg=%s",
            close_status_code, close_msg,
        )
