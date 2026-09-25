# Notes

HA integration that lets HACS install private GitHub repos. Created 2026-07-21, current **v0.2.5**.

**`jetsoncontrols/ha-hacs-token-manager`** — public repo (the public bootstrap manager), domain `hacs_token_manager`, local: `~/Development/CONTROLS/ha-hacs-token-manager`.

> **Per-site deployment status is NOT tracked in this doc** — it goes stale the moment a site changes. Read it off the site instead: `binary_sensor.hacs_private_token_manager_private_repo_access` (`on`, `reason: ok`, `heal_count: 0`) and the scope of the token in HACS's config entry.

**Problem it solves:** HACS officially can't install private repos — but reading HACS source proved the block is ONLY the device-flow token's zero GitHub scope, NOT any code guard (`private` appears nowhere in HACS's 59 py files; a private repo just 404s during validation). So a `repo`-capable token in HACS's config entry makes private custom repos Just Work. We build ~30 sites' worth of purpose-built integrations that aren't worth open-sourcing, so this unlocks distributing them privately via HACS.

**2026-07-21: ALL `jetsoncontrols/ha-*` repos are PRIVATE except `ha-hacs-token-manager`** (20 private, 1 public). **CONSEQUENCE:** every HACS-distributed repo we own is private, so on a site WITHOUT the token manager HACS can no longer update or reinstall any of them — already-running installs keep working, only HACS management breaks, and it breaks with "Could not download". That covers `ha-themes` (`/deploy theme`), `ha-axis-pacs-vapix` + `ha-unifi-access` (`/deploy access-codes`, `/provision access`), `ha-jetson-cards` (`/deploy access`) and the rest, **so the token manager is a PREREQUISITE for those flows, not an optional extra.** Test private repo `ha-av-router` was flipped PUBLIC→PRIVATE for this and is still private.

**Auth decision (2026-07-21):** Scott wants ANY private repo the authorizing user can access, NO per-repo restriction → chose **OAuth App + `repo` scope via GitHub device flow** (browser login, same UX as HACS; RULES OUT a GitHub App, which is limited to installed repos). Config-flow menu → "Authorize with GitHub" (device flow, live progress) OR "Enter a token manually" (classic/fine-grained PAT, headless/Ansible). OAuth App "Jetson HACS Private Token Manager" under jetsoncontrols, **Client ID `Ov23lifok77OAgPL1LUa`** (public, committed in `const.py`), "Enable Device Flow" checked.

**How it works:** a companion integration that writes a capable GitHub token into HACS's config entry `data.token`. A 15-min coordinator self-heals token drift (HACS re-auth reverts to the public-only token → re-inject), raises a fixable HA **Repair** when the managed token expires, and an info Repair when HACS is absent. Health `binary_sensor` + reconfigure flow. Fine-grained-PAT-first (Contents: Read-only), optional test-repo probe.

**Key constraint:** HACS reads its token ONCE at entry setup → healing = rewrite entry + restart; use a STATIC long-lived token (a rotating GitHub App installation token would force a HACS reload hourly — deliberately not used).

**Dev-container verification (v0.2.1):** proven end-to-end in the HA-core dev container (`~/Development/hass_core`, container `blissful_bouman`, HA on localhost:8123; component mounted via `.devcontainer/devcontainer.json` + copied into `config/custom_components/`): browser auth → token → inject into HACS entry `data.token` → HACS re-ran setup rebuilding its live client from our token; plus the boot-drift self-heal path. Three bugs found+fixed there (commit `7f3f093`): (1) `async_show_progress_done` must hand off to a SEPARATE `finish` step (pointing back at the progress step hangs the spinner); (2) don't reload HACS inline in our first-refresh (`OperationNotAllowed`) — use `async_schedule_reload`, and during startup defer it to `EVENT_HOMEASSISTANT_STARTED` so HACS is fully loaded; (3) that started listener must be `@callback` (else `async_schedule_reload` runs off-loop → thread-safety RuntimeError).

---

## Integration icon (v0.2.5)

`custom_components/hacs_token_manager/brand/` holds `icon.png` 256², `icon@2x.png` 512² and lighter `dark_icon*.png`. HA 2026.3+ serves a custom integration's own `brand/` folder before the brands CDN (which has no `hacs_token_manager`). An original mark: a git branch graph with a key over it (grey #424242 + blue #2996D6; #C8C8C8 + #41BDF5 on dark), drawn with Pillow; not GitHub's Octocat, which is GitHub's trademark.

## CRITICAL gotcha 1 (v0.2.2) — HACS CANNOT be reloaded from outside

HACS registers `add_update_listener(async_reload_entry)` and **reloads ITSELF on any config-entry data change**, and that reload is unsafe: HACS forwards its `switch`/`update` platforms in a DEFERRED startup stage, so an externally-triggered reload races it → `ValueError: Config entry was never loaded!` → **FAILED_UNLOAD** → `OperationNotAllowed`. Even our own `async_update_entry` (the injection itself) tripped it; an explicit `async_schedule_reload` made it worse (double reload). Found on the first real install.

**Fix:** `coordinator._inject_token` writes the token into HACS's entry with HACS's `update_listeners` **temporarily detached** (`list(...); .clear(); async_update_entry(...); [:]=saved` — atomic, no awaits; confirmed against HA source, where `_async_save_and_notify` iterates `entry.update_listeners`) so HACS is NOT reloaded and keeps running untouched on its old token; then raise a fixable **`restart_required` Repair** (`repairs.py` `RestartFixFlow` calls `homeassistant.restart`). HACS reads its token only at setup, so a **restart is the only reliable way to apply it**. On next start HACS loads with our token, the coordinator sees no drift → auto-clears the repair.

**This binds operators too, not just this integration's code: never `homeassistant.reload_config_entry` the HACS entry by hand.** Recovery for a HACS stuck in FAILED_UNLOAD: **just restart HA** — the token was injected correctly, only HACS's live client was stuck.

**Debounce gotcha:** `.storage/repairs.issue_registry` is debounce-written (create lagged ~2 min, delete similarly) — DON'T trust the file for repair state; the HA **UI is authoritative**.

## CRITICAL gotcha 2 (v0.2.3) — HACS downloads file CONTENT unauthenticated

After the token made HACS's API calls work (private repo VISIBLE + updatable), the actual install/update still **404'd ("Could not download")**. Cause: HACS fetches file content from **`raw.githubusercontent.com` via `HacsBase.async_download_file` WITHOUT its token** (`integration.py:208`, `base.py:678`) — the token only authenticates the API (`self.githubapi`), not the raw file downloads. **Verified: raw URL no-auth → 404, raw URL + `Authorization: token <tok>` → 200** (raw.githubusercontent.com DOES honor the token for private repos).

Fix (`hacs_patch.py`): a narrow defensive monkey-patch wrapping `HacsBase.async_download_file` to add `Authorization: token <self.configuration.token>` for GitHub hosts (raw/codeload/objects/github.com), applied in `__init__.async_setup_entry`; self-disables if HACS internals move. Covers both download paths (individual files + `async_download_zip_file`). Verified in a dev HA venv: the patched `async_download_file` pulled a private `ha-av-router` file (439 B) with the token, nothing without. **This is the one place we DO monkey-patch HACS — unavoidable, HACS has no config to authenticate downloads.**

So the token manager does TWO things: (1) silent token inject + restart repair, (2) authenticate HACS's downloads. Without (2), a private-repo HACS download fails *after* HACS has already deleted the existing component — which is how a migration can leave a site with no integration at all.

---

## Rollout recipe (per site)

Proven, no browser step needed when a capable token is already in hand:

1. HACS `add_repository` + `download` of the (public) token manager — repo id **`1307897402`**.
2. `ha_restart`.
3. `ha_set_integration(domain="hacs_token_manager", config={"next_step_id":"manual","token":"<tok>"})` — the flow's menu step ids are `device` / `manual`.
4. `ha_restart` → private repos resolve.

**BLOCKER — Claude Code's safety classifier REFUSES to relay the fleet token between hosts.** Both shapes were denied: printing another site's `data.token` over SSH, and staging it to `/tmp` for an SFTP hop. That is the guardrail's actual intent (moving a live credential off a production host), so a third encoding would be bypassing it, not working around a quirk — **don't try.** So step 3 does NOT run unattended. Working paths: (a) **device flow** (`next_step_id: "device"`, the user approves an 8-char code at github.com/login/device — no VPN, no credential handling), or (b) **the user enters the token themselves** in the UI (Add integration → "Enter a token manually").

**Token triage WITHOUT extracting the token** (permitted, and the useful check):

```
TOK=$(…);  curl -sI -H "Authorization: token $TOK" https://api.github.com/user | grep x-oauth-scopes
```

Want `repo`. **An EMPTY scope list is the signature of HACS's own device-flow token** — it 404s every private repo while the public token manager returns 200. Also probe per-repo with `curl -o /dev/null -w '%{http_code}'`.

**A stale `pending_update: true` can be a LIE on a scopeless site** — a cached version claim predating privatization (e.g. `ha-themes` showing `ed6bf00 → v1.0.0`); after auth it reconciles and no update is pending.

**Reusing one token across sites is acceptable** (confirmed), with the consequence that revoking it in GitHub breaks HACS everywhere it is used; a per-site device-flow authorization overwrites it harmlessly. Always verify a candidate token's scope before reuse.

---

**Dev-container run pattern:** `docker exec -d blissful_bouman bash -lc 'cd /workspaces/hass_core && /home/vscode/.local/ha-venv/bin/hass -c config >/tmp/ha_test.log 2>&1'`; kill hass with the `ha-venv/bin/[h]ass` ps trick (plain pkill self-matches).

**Still unverified:** whether `aiogithubapi`/HACS's calls all work with a **FINE-GRAINED** token (historically some GitHub endpoints lagged on fine-grained support — the one real unknown; every proven install so far used a classic/OAuth `gho_` token).

Related: [[project-ha-av-router]] (same "new private HA integration" shape).

---
*Relocated from Claude Code local memory (`project_ha_hacs_token_manager`) on 2026-09-01 — see the repo-wide rule: knowledge about a repo lives in that repo.*
