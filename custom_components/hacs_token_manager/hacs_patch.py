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
to authenticate downloads, so there is no other way. It is built to fail SAFE
and LOUD against HACS updates:

  * If HACS's internals moved (import fails, method or ``headers`` kwarg gone),
    the patch is SKIPPED -- downloads behave exactly as they do today, nothing
    breaks -- and ``async_patch_hacs_download`` returns False so the caller can
    surface a Repair instead of failing silently.
  * We only patch when ``async_download_file`` still accepts an explicit
    ``headers`` keyword, so a signature change can never make us break a
    download that would otherwise have worked.
"""

from __future__ import annotations

import inspect
import logging

_LOGGER = logging.getLogger(__name__)

_GITHUB_HOSTS = (
    "raw.githubusercontent.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
    "github.com",
)
_PATCH_MARKER = "_jetson_hacs_auth"

_SKIP_MSG = (
    "HACS download-auth patch could not be applied (%s); HACS may have changed. "
    "Public repos are unaffected, but installing/updating PRIVATE repos will "
    "fail until this is updated."
)


def async_patch_hacs_download() -> bool:
    """Wrap HacsBase.async_download_file to authenticate GitHub downloads.

    Returns True if the patch is active (now or already), False if it had to be
    skipped -- in which case the caller should surface it (private-repo installs
    will not work).
    """
    try:
        from custom_components.hacs.base import HacsBase
    except Exception:  # noqa: BLE001 - HACS absent or internals moved
        _LOGGER.warning(_SKIP_MSG, "hacs.base not importable")
        return False

    original = getattr(HacsBase, "async_download_file", None)
    if original is None:
        _LOGGER.warning(_SKIP_MSG, "async_download_file missing")
        return False
    if getattr(original, _PATCH_MARKER, False):
        return True  # already applied this session

    # Only patch when the method still accepts an explicit `headers` kwarg. If
    # the signature changed, do NOT patch: passing headers= could be silently
    # dropped (auth lost) or raise (breaking EVERY download, public included).
    try:
        if "headers" not in inspect.signature(original).parameters:
            _LOGGER.warning(_SKIP_MSG, "async_download_file no longer accepts headers")
            return False
    except (TypeError, ValueError):
        _LOGGER.warning(_SKIP_MSG, "async_download_file signature not introspectable")
        return False

    async def _authenticated_download_file(self, url, *, headers=None, **kwargs):
        token = getattr(getattr(self, "configuration", None), "token", None)
        if url and token and any(host in url for host in _GITHUB_HOSTS):
            headers = {**(headers or {}), "Authorization": f"token {token}"}
        return await original(self, url, headers=headers, **kwargs)

    setattr(_authenticated_download_file, _PATCH_MARKER, True)
    HacsBase.async_download_file = _authenticated_download_file
    _LOGGER.debug("Patched HACS async_download_file to authenticate GitHub downloads")
    return True
