"""Authenticate HACS's file downloads so private-repo content can be fetched.

The token we inject makes HACS's *API* calls (metadata, releases, file tree)
authenticated, so private repositories become visible and updatable in the HACS
UI. But HACS downloads the actual file *content* from ``raw.githubusercontent``
(and release archives from ``github.com``) via ``HacsBase.async_download_file``
WITHOUT sending its token -- so for a private repo every file 404s and the
install/update fails with "Could not download".

``raw.githubusercontent.com`` does honor ``Authorization: token <token>`` for
private repos (verified), so we wrap ``async_download_file`` to add that header
for GitHub hosts, using HACS's own configured token. Everything else is
untouched.

This is intentionally a narrow, defensive monkey-patch: HACS exposes no config
to authenticate downloads, so there is no other way. If HACS's internals move,
the patch is skipped and downloads behave exactly as they do today (no crash).
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

_GITHUB_HOSTS = (
    "raw.githubusercontent.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
    "github.com",
)
_PATCH_MARKER = "_jetson_hacs_auth"


def async_patch_hacs_download() -> None:
    """Idempotently wrap HacsBase.async_download_file to authenticate GitHub."""
    try:
        from custom_components.hacs.base import HacsBase
    except Exception:  # noqa: BLE001 - HACS absent or internals moved
        _LOGGER.debug("HACS base not importable; download-auth patch skipped")
        return

    original = getattr(HacsBase, "async_download_file", None)
    if original is None:
        _LOGGER.debug("HacsBase.async_download_file missing; patch skipped")
        return
    if getattr(original, _PATCH_MARKER, False):
        return  # already patched this session

    async def _authenticated_download_file(self, url, *, headers=None, **kwargs):
        token = getattr(getattr(self, "configuration", None), "token", None)
        if url and token and any(host in url for host in _GITHUB_HOSTS):
            headers = {**(headers or {}), "Authorization": f"token {token}"}
        return await original(self, url, headers=headers, **kwargs)

    setattr(_authenticated_download_file, _PATCH_MARKER, True)
    HacsBase.async_download_file = _authenticated_download_file
    _LOGGER.debug("Patched HACS async_download_file to authenticate GitHub downloads")
