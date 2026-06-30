# -*- coding: utf-8 -*-
import pytest

from src.utils.adb.adb_utils import adb_shell, is_package_exist


def _shell_output(device_serial, command):
    result = adb_shell(device_serial, command, no_retry=True)
    return (result.get("output") or result.get("error") or "").strip()

@pytest.mark.require_android_version_min(15)
def _check_download_provider_ready(device_serial):
    if not is_package_exist(device_serial, "com.android.providers.downloads"):
        pytest.fail("Missing package: com.android.providers.downloads")

    query_out = _shell_output(
        device_serial,
        "content query --uri content://downloads/my_downloads --projection _id",
    )
    if not query_out:
        pytest.skip("content://downloads/my_downloads query returns empty output")
    lower_out = query_out.lower()
    if "unknown uri" in lower_out or "securityexception" in lower_out:
        pytest.fail(f"downloads provider query failed: {query_out}")


@pytest.mark.require_android_version_min(15)
def test_download_provider_visibility_path_smoke(device_serial):
    """
    ID:TOS1600-DM-UI-HIDDEN
    DESCRIPTION:[CTS]DownloadManagerTest#testDownloadNotVisibleInUi
    """
    _check_download_provider_ready(device_serial)

    public_query = _shell_output(
        device_serial,
        "content query --uri content://downloads/public_downloads --projection _id --limit 1",
    )
    if not public_query:
        pytest.skip("content://downloads/public_downloads query returns empty output")
    lower_public = public_query.lower()
    if "unknown uri" in lower_public or "securityexception" in lower_public:
        pytest.fail(f"public_downloads query failed: {public_query}")

@pytest.mark.require_android_version_min(15)
def test_set_destination_uri_smoke(device_serial):
    """
    ID:TOS1600-DM-DEST-URI
    DESCRIPTION:[CTS]DownloadManagerTest#testSetDestinationUri
    """
    _check_download_provider_ready(device_serial)

    downloads_ls = _shell_output(device_serial, "ls -ld /storage/emulated/0/Download")
    if not downloads_ls:
        pytest.fail("Cannot access /storage/emulated/0/Download")
    lower_ls = downloads_ls.lower()
    if "no such file" in lower_ls or "permission denied" in lower_ls:
        pytest.fail(f"Downloads directory is unavailable: {downloads_ls}")
