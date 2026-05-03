from __future__ import annotations


def build_diagnostic_messages(summary: dict[str, object]) -> list[str]:
    messages = [str(summary.get("channel_health_summary", "No network summary available."))]
    if summary.get("offline_nodes"):
        messages.append(f"Offline nodes: {', '.join(summary['offline_nodes'])}")
    if summary.get("low_signal_nodes"):
        messages.append(f"Low-signal nodes: {', '.join(summary['low_signal_nodes'])}")
    return messages
