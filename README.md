# HACS Private Token Manager

A small Home Assistant integration that lets **HACS install and update your
private GitHub repositories** — through the normal HACS UI, with no fork and no
patching of HACS.

Install it via HACS, hand it a GitHub token that can read your private repos,
and it keeps HACS authenticated with that token. It also **self-heals** when
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
- A GitHub token that can read your private repositories

## Installation

1. In HACS → **⋮** → **Custom repositories**, add
   `jetsoncontrols/ha-hacs-token-manager`, category **Integration**.
2. Install **HACS Private Token Manager** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → HACS Private Token
   Manager**, and paste your token.

## Creating the GitHub token (recommended: fine-grained, least-privilege)

Use a **fine-grained personal access token** so the blast radius is minimal:

- **Resource owner:** the org/account that owns your private repos
- **Repository access:** *Only select repositories* → pick just your HACS
  distribution repos
- **Repository permissions → Contents:** *Read-only*
  (Metadata: Read is added automatically — that's all HACS's read calls need)
- **Expiration:** as long-lived as your policy allows (see caveats)

A classic PAT with the `repo` scope also works, but it grants read/write to
**every** repo on the account — prefer fine-grained.

In the integration's setup form you can optionally provide a **Test
repository** (`owner/name`). When set, the token is verified to actually *read
that private repo*, not merely to authenticate — a good guard against a token
with the wrong repository scope.

---

## How it behaves

| Situation | What happens |
|-|-|
| First setup | Token is validated, written into HACS's entry, HACS reloaded. Private custom repos now resolve. |
| HACS re-authenticates (reverts to a public-only token) | Detected within ~15 min (and on restart); the capable token is re-injected and HACS reloaded automatically. No action needed. |
| Your token expires or is revoked | A **Repair** appears ("GitHub token for private HACS repos is invalid") — click *Fix* and paste a new token. |
| HACS not installed | An informational Repair reminds you to install HACS. |

A `binary_sensor` (**Private repo access**, device class *connectivity*)
reflects current health, with `reason` and `heal_count` attributes.

You can rotate the token proactively at any time via the integration's
**Reconfigure** option.

---

## Caveats & design notes

- **HACS reads its token once, at entry setup.** That's why healing = rewrite
  the entry + reload, and why a *static* long-lived token is the right fit. A
  rotating token (e.g. a GitHub App installation token that expires hourly)
  would force a HACS reload on every rotation and is intentionally not used.
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
