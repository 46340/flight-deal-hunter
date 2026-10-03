"""Extension points. Notifications (Telegram, email) and exports plug in here later."""

from __future__ import annotations


def on_run_complete(summary: dict) -> None:
    """Called once after every run with the run summary (see data/runs.json)."""
    return None
