from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IngestionError:
    packet_id: str
    message: str


def format_ingestion_error(packet_id: str, message: str) -> str:
    return f"[{packet_id}] {message}"
