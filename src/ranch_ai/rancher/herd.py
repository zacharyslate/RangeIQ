"""Herd ledger: how many cattle are in each pasture, by class, worked out from what the crew logged.

Nothing here stores a running total. Every change is a log entry (they sync from phones without signal), and the
counts are recomputed from the whole ledger in the order things happened in the field:

  move   {pasture_id: to, lines: [{from: <pasture id> | "unknown", all: bool, counts: {class: n}}]}
         Several "from" lines when cattle come from more than one pasture. "all" = everything that was in that
         pasture went (the amounts come from the ledger when the pasture has been counted). "unknown" = found loose
         or not sure where they came from. Older moves (from_pasture_id + head, no classes) only move the herd's
         days in / days rested, as before.
  count  {pasture_id, counts}       what someone actually saw: replaces what the ledger thought for that pasture.
  herd   {pasture_id, event, counts} born / bought (in), died / sold (out), wean (calves become heifers and steers).

A pasture that goes below zero, or took cattle from "not sure", or hasn't been counted for RECOUNT_DAYS, is flagged
for a count. The app never refuses an entry because the numbers don't add up: the cattle in front of the crew are
the truth, the ledger is a belief."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

CLASSES = ("cows", "bulls", "calves", "heifers", "steers")
EVENTS = {"born": 1, "bought": 1, "died": -1, "sold": -1, "wean": 0}
HERD_KINDS = {"move", "count", "herd"}
UNKNOWN = "unknown"
RECOUNT_DAYS = 30
MAX_HEAD = 100000


def _when(value: Any) -> datetime:
    when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def clean_counts(raw: Any) -> dict[str, int]:
    """{class: whole number >= 0} for the known classes; anything else is dropped."""
    out: dict[str, int] = {}
    if not isinstance(raw, dict):
        return out
    for cls in CLASSES:
        try:
            n = int(float(raw.get(cls) or 0))
        except (TypeError, ValueError):
            raise ValueError("Head counts must be whole numbers.") from None
        if n < 0 or n > MAX_HEAD:
            raise ValueError("Head counts must be between 0 and 100,000.")
        if n:
            out[cls] = n
    return out


def clean_entry(kind: str, payload: dict[str, Any], pasture_id: Any) -> dict[str, Any]:
    """Check and tidy a herd entry's payload (the fields other than client_id, kind, logged_at, pasture_id)."""
    if kind == "move":
        if "lines" not in payload:               # an older phone: Into / Out of / head
            return payload
        if not pasture_id:
            raise ValueError("Pick the pasture the cattle went to.")
        lines = payload.get("lines")
        if not isinstance(lines, list) or not 1 <= len(lines) <= 20:
            raise ValueError("A move needs at least one pasture they came from.")
        clean = []
        for line in lines:
            if not isinstance(line, dict):
                raise ValueError("A move needs at least one pasture they came from.")
            src = str(line.get("from") or UNKNOWN)[:64]
            if src == str(pasture_id):
                raise ValueError("Cattle can't move into the pasture they came from.")
            counts, everything = clean_counts(line.get("counts")), bool(line.get("all"))
            if not counts and not (everything and src != UNKNOWN):
                raise ValueError("Say how many head moved, or tick All.")
            clean.append({"from": src, "all": everything and src != UNKNOWN, "counts": counts})
        return {**payload, "lines": clean}
    if kind == "count":
        if not pasture_id:
            raise ValueError("Pick the pasture that was counted.")
        return {**payload, "counts": clean_counts(payload.get("counts"))}
    if kind == "herd":
        if not pasture_id:
            raise ValueError("Pick the pasture.")
        event = str(payload.get("event") or "")
        if event not in EVENTS:
            raise ValueError("Pick what happened: born, bought, sold, died or weaned.")
        counts = clean_counts(payload.get("counts"))
        if event == "wean":
            counts = {k: v for k, v in counts.items() if k in ("heifers", "steers")}
        if not counts:
            raise ValueError("Say how many head.")
        return {**payload, "event": event, "counts": counts}
    return payload


def _ordered(logs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for log in logs:
        if log.get("kind") not in HERD_KINDS or log.get("deleted"):
            continue
        try:
            _when(log["logged_at"])
        except (KeyError, ValueError):
            continue
        out.append(log)
    return sorted(out, key=lambda l: (_when(l["logged_at"]), str(l.get("received_at") or ""), str(l.get("client_id") or "")))


def inventory(logs: Iterable[dict[str, Any]], today: datetime | None = None) -> dict[str, Any]:
    """Head in each pasture by class, when each was last counted, what needs a recount, and for each count entry
    how far it was from what the ledger expected (count_diffs, by client_id)."""
    today = today or datetime.now(timezone.utc)
    head: dict[str, dict[str, int]] = {}
    counted: dict[str, dict[str, Any]] = {}
    loose: set[str] = set()          # took cattle from "not sure" since the last count
    went_negative: set[str] = set()
    changed: dict[str, str] = {}
    diffs: dict[str, dict[str, int]] = {}

    def add(pid: str, counts: dict[str, int], sign: int, at: str) -> None:
        cur = head.setdefault(pid, {c: 0 for c in CLASSES})
        for cls, n in counts.items():
            cur[cls] += sign * n
            if cur[cls] < 0:
                went_negative.add(pid)
        changed[pid] = at

    for log in _ordered(logs):
        kind, pid, at = log["kind"], log.get("pasture_id"), str(log["logged_at"])
        if not pid:
            continue
        if kind == "move" and isinstance(log.get("lines"), list):
            for line in log["lines"]:
                src, counts = line.get("from") or UNKNOWN, clean_counts(line.get("counts"))
                if line.get("all") and src != UNKNOWN and src in head:
                    counts = {c: n for c, n in head[src].items() if n > 0} or counts
                if src == UNKNOWN:
                    loose.add(pid)
                else:
                    add(src, counts, -1, at)
                    if line.get("all"):
                        head[src] = {c: 0 for c in CLASSES}
                add(pid, counts, 1, at)
        elif kind == "count":
            counts = clean_counts(log.get("counts"))
            before = {c: max(n, 0) for c, n in head.get(pid, {c: 0 for c in CLASSES}).items()}   # as the app showed it
            if pid in counted or any(before.values()):
                diffs[str(log.get("client_id"))] = {c: counts.get(c, 0) - before.get(c, 0) for c in CLASSES
                                                    if counts.get(c, 0) != before.get(c, 0)}
            head[pid] = {c: counts.get(c, 0) for c in CLASSES}
            counted[pid] = {"at": at, "by": log.get("by")}
            loose.discard(pid)
            went_negative.discard(pid)
            changed[pid] = at
        elif kind == "herd":
            event, counts = log.get("event"), clean_counts(log.get("counts"))
            if event == "wean":
                counts = {k: v for k, v in counts.items() if k in ("heifers", "steers")}
                calves = sum(counts.values())
                add(pid, {"calves": calves}, -1, at)
                add(pid, counts, 1, at)
            elif event in EVENTS:
                add(pid, counts, EVENTS[event], at)

    pastures: dict[str, Any] = {}
    for pid, cur in head.items():
        shown = {c: max(n, 0) for c, n in cur.items()}
        total = sum(shown.values())
        flags = []
        if pid in went_negative or any(n < 0 for n in cur.values()):
            flags.append("negative")
        if pid in loose:
            flags.append("unknown_source")
        if pid not in counted:
            flags.append("not_counted")
        elif total and (today - _when(counted[pid]["at"])).days >= RECOUNT_DAYS:
            flags.append("stale")
        pastures[pid] = {"counts": {c: n for c, n in shown.items() if n}, "total": total,
                         "counted_at": (counted.get(pid) or {}).get("at"), "counted_by": (counted.get(pid) or {}).get("by"),
                         "changed_at": changed.get(pid), "flags": flags}
    totals = {c: sum(p["counts"].get(c, 0) for p in pastures.values()) for c in CLASSES}
    return {"classes": list(CLASSES), "pastures": pastures, "total": {c: n for c, n in totals.items() if n},
            "head": sum(totals.values()), "count_diffs": diffs}


def herd_days(logs: list[dict[str, Any]], today: datetime | None = None) -> dict[str, dict[str, int]]:
    """Days cattle have been IN each pasture, or days it has RESTED since the last of them left.

    With head counts a pasture is only resting once it's empty: moving 2 cows out of 40 doesn't start its rest.
    An older move without counts (Into / Out of) empties the pasture it came out of, as it always did."""
    today = today or datetime.now(timezone.utc)
    last_in: dict[str, datetime] = {}
    last_out: dict[str, datetime] = {}
    head: dict[str, int] = {}
    known: set[str] = set()            # pastures whose head count the ledger knows

    def fill(pid: str, when: datetime) -> None:
        if pid not in last_in:
            last_in[pid] = when
        last_out.pop(pid, None)

    def empty(pid: str, when: datetime) -> None:
        last_out[pid] = when
        last_in.pop(pid, None)

    ordered = sorted((l for l in logs if l.get("kind") in HERD_KINDS and l.get("logged_at")), key=lambda l: _when(l["logged_at"]))
    for log in ordered:
        when, kind, pid = _when(log["logged_at"]), log["kind"], log.get("pasture_id")
        if not pid:
            continue
        if kind == "move" and not isinstance(log.get("lines"), list):
            src = log.get("from_pasture_id")
            if src:
                empty(src, when)
                head[src] = 0
            last_in[pid] = when
            last_out.pop(pid, None)
            continue
        if kind == "move":
            moved = 0
            for line in log["lines"]:
                src, n = line.get("from") or UNKNOWN, sum(clean_counts(line.get("counts")).values())
                if src != UNKNOWN:
                    if line.get("all") and src in known:
                        n = max(head.get(src, 0), n)
                    head[src] = 0 if line.get("all") else head.get(src, 0) - n
                    if head[src] <= 0 or src not in known:
                        empty(src, when)
                        head[src] = max(head[src], 0)
                moved += n
            head[pid] = head.get(pid, 0) + moved
            known.add(pid)
            if head[pid] > 0:
                fill(pid, when)
        elif kind == "count":
            total = sum(clean_counts(log.get("counts")).values())
            head[pid] = total
            known.add(pid)
            if total:
                fill(pid, when)
            elif pid in last_in:
                empty(pid, when)
        elif kind == "herd":
            counts, event = clean_counts(log.get("counts")), log.get("event")
            n = sum(counts.values()) * EVENTS.get(event, 0)          # weaning doesn't change the head count
            head[pid] = head.get(pid, 0) + n
            known.add(pid)
            if head[pid] > 0:
                fill(pid, when)
            elif pid in last_in and n < 0:
                empty(pid, when)
    out: dict[str, dict[str, int]] = {}
    for pid, when in last_in.items():
        out[pid] = {"days_in": max((today - when).days, 0)}
        if pid in known and head.get(pid):
            out[pid]["head"] = head[pid]
    for pid, when in last_out.items():
        if pid not in last_in:
            out[pid] = {"days_rested": max((today - when).days, 0)}
    return out
