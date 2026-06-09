"""Canonical Claude model IDs — single source of truth for the Python side.

Importing these instead of hardcoding the literals keeps model upgrades to a
one-line change. Mirror of ``web/lib/models.ts`` on the frontend.
"""

from __future__ import annotations

CLAUDE_SONNET = "claude-sonnet-4-6"
CLAUDE_HAIKU = "claude-haiku-4-5-20251001"
