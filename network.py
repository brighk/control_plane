"""Router and device info from archer-monitor's Prometheus endpoint.

archer-monitor is the only thing that logs in to the router (it allows one admin
session). This module just reads the metrics it already publishes.
"""

import threading
import time
from dataclasses import dataclass

import httpx
from prometheus_client.parser import text_string_to_metric_families
from pydantic import BaseModel


class Device(BaseModel):
    mac: str
    name: str
    ip: str
    connection: str
    online: bool
    download_bytes_per_second: float | None = None
    upload_bytes_per_second: float | None = None
    tx_rate_mbps: float | None = None
    rx_rate_mbps: float | None = None
    signal: float | None = None


class NetworkStatus(BaseModel):
    enabled: bool
    # False when the exporter's last router poll failed; devices are then last known values.
    router_reachable: bool = False
    last_success: float | None = None  # unix time of the exporter's last good poll
    wan_up: bool | None = None
    wan_uptime_seconds: float | None = None
    # Computed from the byte counters between two of our fetches; None on the first one.
    wan_download_bytes_per_second: float | None = None
    wan_upload_bytes_per_second: float | None = None
    devices: list[Device] = []


# Exporter metric name -> Device field.
_DEVICE_GAUGES = {
    "archer_client_download_bytes_per_second": "download_bytes_per_second",
    "archer_client_upload_bytes_per_second": "upload_bytes_per_second",
    "archer_client_wifi_tx_rate_mbps": "tx_rate_mbps",
    "archer_client_wifi_rx_rate_mbps": "rx_rate_mbps",
    "archer_client_wifi_signal": "signal",
}


def parse_metrics(text: str) -> tuple[NetworkStatus, dict[str, float]]:
    """Returns the status (without WAN rates) and the raw WAN byte counters."""
    scalars: dict[str, float] = {}
    devices: dict[str, Device] = {}
    per_device: list[tuple[str, dict[str, str], float]] = []

    for family in text_string_to_metric_families(text):
        for s in family.samples:
            if "mac" in s.labels:
                per_device.append((s.name, s.labels, s.value))
            elif not s.labels:
                scalars[s.name] = s.value

    # archer_client_online lists every known device; the others only online ones.
    for name, labels, value in per_device:
        if name == "archer_client_online":
            devices[labels["mac"]] = Device(
                mac=labels["mac"],
                name=labels.get("name", "unknown"),
                ip=labels.get("ip", ""),
                connection=labels.get("connection", "unknown"),
                online=value == 1,
            )
    for name, labels, value in per_device:
        field = _DEVICE_GAUGES.get(name)
        device = devices.get(labels["mac"])
        if field and device:
            setattr(device, field, value)

    wan_up = scalars.get("archer_wan_up")
    status = NetworkStatus(
        enabled=True,
        router_reachable=scalars.get("archer_up") == 1,
        last_success=scalars.get("archer_last_success_timestamp_seconds") or None,
        wan_up=None if wan_up is None else wan_up == 1,
        wan_uptime_seconds=scalars.get("archer_wan_uptime_seconds"),
        devices=sorted(
            devices.values(), key=lambda d: (not d.online, d.name.lower(), d.mac)
        ),
    )
    counters = {
        k: scalars[k]
        for k in ("archer_wan_receive_bytes_total", "archer_wan_transmit_bytes_total")
        if k in scalars
    }
    return status, counters


@dataclass
class _Sample:
    at: float
    counters: dict[str, float]


class NetworkReader:
    """Fetches the exporter's metrics and turns WAN byte counters into rates."""

    def __init__(self, url: str, timeout: float = 3.0) -> None:
        self.url = url
        self.timeout = timeout
        self._prev: _Sample | None = None
        self._lock = threading.Lock()

    def read(self) -> NetworkStatus:
        resp = httpx.get(self.url, timeout=self.timeout)
        resp.raise_for_status()
        now = time.monotonic()
        status, counters = parse_metrics(resp.text)

        with self._lock:
            prev, self._prev = self._prev, _Sample(now, counters)
        if prev is not None:
            dt = now - prev.at
            status.wan_download_bytes_per_second = _rate(
                prev, counters, "archer_wan_receive_bytes_total", dt
            )
            status.wan_upload_bytes_per_second = _rate(
                prev, counters, "archer_wan_transmit_bytes_total", dt
            )
        return status


def _rate(
    prev: _Sample, counters: dict[str, float], key: str, dt: float
) -> float | None:
    # Too-close samples give noisy rates; a counter that went down was reset/wrapped.
    if dt < 1 or key not in counters or key not in prev.counters:
        return None
    delta = counters[key] - prev.counters[key]
    return delta / dt if delta >= 0 else None
