# HACS Private Token Manager

A small Home Assistant integration that lets **HACS install and update your
private GitHub repositories** — through the normal HACS UI, with no fork and no
patching of HACS.

Install it via HACS, **authorize with GitHub in the browser** (the same
device-flow login HACS itself uses — no token to create by hand), and it keeps
HACS authenticated with that token. The token can read **every private
repository the authorizing user has access to**. It also **self-heals** when
HACS quietly reverts to its own public-only token, and raises a Home Assistant
**Repair** when the token itself expires.

---

## Why this exists

HACS officially [cannot use private repositories](https://www.hacs.xyz/docs/faq/private_repositories/).
Reading the HACS source shows *why*, and it is narrower than it sounds:

- HACS authenticates through its own GitHub device-OAuth flow, which mints a
  token with **zero scopes** — public data only.
- That token is stored in HACS's config entry and handed verbatim to HACS's
  GitHub clients.
- There is **no private-repo check anywhere in HACS's code.** The string
  `private` does not appear in the integration. A private repo fails simply
  because the public-only token gets a `404` from GitHub during validation.

So the block is entirely the **token's scope**, not HACS logic. Give HACS's
config entry a token that *can* read private repos and private custom
repositories just work — nothing in HACS objects.

This integration automates exactly that, safely:

1. You give it a capable GitHub token.
2. It writes that token into HACS's config entry and reloads HACS — the same
   two public Home Assistant APIs (`async_update_entry` + `async_reload`) that
   HACS itself uses in its re-auth path. **It never touches HACS internals.**
3. It watches for the token drifting back to the public-only one (which happens
   whenever HACS re-authenticates) and re-injects automatically.
4. If your token expires or is revoked, it raises a fixable Repair so you can
   paste a new one.

---

## Requirements

- Home Assistant **2024.11** or newer
- HACS installed and set up

## Installation

1. In HACS → **⋮** → **Custom repositories**, add
   `jetsoncontrols/ha-hacs-token-manager`, category **Integration**.
2. Install **HACS Private Token Manager** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → HACS Private Token
   Manager**, then choose one of the two setup paths below.

## Setup

### Option 1 — Authorize with GitHub (browser login, recommended)

Pick **Authorize with GitHub**. You'll see a code and a link
(`github.com/login/device`); open it, enter the code, and approve. That's it —
the resulting token can read **any private repository your GitHub account has
access to**, and the integration injects it into HACS for you. This is the same
device-flow login HACS uses; no personal access token to create or store.

> This path requires the maintainer to have configured an OAuth App Client ID
> in the build (see *Maintainer notes*). If it isn't configured, use Option 2.

### Option 2 — Enter a token manually (headless / automated setup)

Pick **Enter a token manually** and paste a token that can read your private
repos:

- a **classic PAT** with the `repo` scope (access to every private repo the
  account can reach), or
- a **fine-grained PAT** with Repository permissions → **Contents: Read-only**
  on the repos you want (least-privilege).

Use this path for scripted/Ansible deploys where a browser login isn't
practical. You can optionally provide a **Test repository** (`owner/name`) to
verify the token can actually read a private repo, not just authenticate.

## Maintainer notes — the OAuth App

Browser login uses a GitHub **OAuth App** owned by the org. To enable it:

1. Org → **Settings → Developer settings → OAuth Apps → New OAuth App**.
2. Name it (e.g. *Jetson HACS Private Token Manager*); Homepage URL = this repo;
   Authorization callback URL = this repo (unused by the device flow, but the
   field is required).
3. **Check “Enable Device Flow.”**
4. Copy the **Client ID** into `CLIENT_ID` in
   `custom_components/hacs_token_manager/const.py` and release. The Client ID is
   a public value; no client secret is needed for the device flow.

The `repo` scope is intentional: it gives the token access to every private
repository the authorizing user can reach, with no per-repo restriction.

---

## How it behaves

| Situation | What happens |
|-|-|
| First setup | Token is validated and written into HACS's entry (without disturbing HACS), then a Repair asks you to **restart Home Assistant** to apply it. After the restart, private custom repos resolve. |
| HACS re-authenticates (reverts to a public-only token) | Detected within ~15 min (and on restart); the capable token is re-injected and a restart Repair is raised. |
| Your token expires or is revoked | A **Repair** appears ("GitHub token for private HACS repos is invalid") — click *Fix* and paste a new token. |
| HACS not installed | An informational Repair reminds you to install HACS. |

A `binary_sensor` (**Private repo access**, device class *connectivity*)
reflects current health, with `reason` and `heal_count` attributes.

You can rotate the token proactively at any time via the integration's
**Reconfigure** option.

---

## Caveats & design notes

- **HACS reads its token once, at entry setup, and a restart is required to
  apply a new one.** HACS reloads itself on any config-entry change, and that
  reload is unsafe (it forwards its `switch`/`update` platforms in a deferred
  startup stage, so an externally-triggered reload leaves HACS in
  `FAILED_UNLOAD`). So this integration writes the token into HACS's entry with
  HACS's own update listener suppressed — HACS keeps running untouched on its
  old token — and asks for a restart, which is the only reliable way to apply
  it. This also makes a *static* long-lived token the right fit: a rotating
  token (e.g. an hourly GitHub App installation token) would demand a restart
  on every rotation, so it is intentionally not used.
- **Re-auth reverts the token.** If HACS's token ever goes invalid, HACS's
  re-auth writes a fresh public-only device token over yours. This integration
  detects that drift and re-injects — but keep your token long-lived so
  re-auth isn't triggered in the first place.
- **The token lives in two places** once injected: this integration's config
  entry and HACS's. Both are inside Home Assistant's `.storage`.
- **Officially unsupported by HACS, but not blocked.** Nothing in HACS
  prohibits a capable token; you are simply supplying one HACS wasn't designed
  to be given. A future HACS release *could* add a visibility or token-origin
  check — re-verify after major HACS updates.
- Private repos still must be **valid HACS repositories** (correct structure /
  `hacs.json` / releases). Being private changes none of that.

## License

MIT © Jetson Controls
