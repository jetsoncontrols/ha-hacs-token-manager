# CLAUDE.md

Guidance for Claude Code when working in this repo.

## ha-hacs-token-manager — notes

- [notes](docs/notes.md) — HA integration that lets HACS install private GitHub repos across the fleet; created 2026-07-21, current v0.2.5. Per-site deployment status is deliberately NOT tracked here — read it off the site's `binary_sensor.hacs_private_token_manager_private_repo_access`.

## Before a release: profile it

Every release that changes how this integration runs (update or push paths, coordinators, entity creation or fan-out, polling, timers, new I/O) is profiled on a real HA system before the fleet updates: HA's `profiler` for 2 minutes with asyncio debug on, then the deployment repo's `tools/host/ha_profile_report.py` inside the HA container. No event-loop stall over 100 ms and no "Detected blocking call" may be blamed on this integration (the report exits `2`), call counts must scale with changes rather than with entity count, and the before/after numbers go in the release commit. Unit tests do not catch this: ha-monitoring 0.41.0 passed all of them while stalling Oak Forest's event loop every 3-4 s. Procedure, pass bar and traps: the deployment repo's `homeassistant/standards/integration-profiling.md`.
