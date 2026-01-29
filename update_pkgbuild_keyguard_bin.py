#!/usr/bin/env python3
"""Update PKGBUILD with latest Keyguard release from GitHub.

This script fetches the latest release information from GitHub API,
extracts SHA256 hashes for Linux artifacts, and updates the PKGBUILD
file with the new values.

Usage:
    python update_pkgbuild.py <input-pkgbuild> <output-pkgbuild>

Example:
    python update_pkgbuild.py PKGBUILD PKGBUILD.new
    python update_pkgbuild.py PKGBUILD PKGBUILD  # update in-place
"""

import argparse
import json
import re
import sys
import urllib.request
from urllib.error import URLError

GITHUB_API_URL = "https://api.github.com/repos/AChep/keyguard-app/releases/latest"


def fetch_latest_release() -> dict:
    """Fetch the latest release information from GitHub API.

    Returns:
        dict: The JSON response from GitHub API.

    Raises:
        URLError: If the network request fails.
        ValueError: If the response is not valid JSON.
    """
    request = urllib.request.Request(
        GITHUB_API_URL,
        headers={
            "Accept": "application/vnd.github.v3+json",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read().decode("utf-8")
        return json.loads(data)


def extract_release_info(release: dict) -> tuple[str, str, str, str]:
    """Extract version, release tag, and SHA256 hashes from release data.

    Args:
        release: The release data from GitHub API.

    Returns:
        A tuple of (version, release_tag, sha256_x86_64, sha256_aarch64).

    Raises:
        ValueError: If required assets or data are missing.
    """
    release_tag = release.get("tag_name")
    if not release_tag:
        raise ValueError("Release tag not found in API response")

    assets = release.get("assets", [])
    if not assets:
        raise ValueError("No assets found in release")

    # Find the Linux artifacts
    x86_64_asset = None
    aarch64_asset = None

    for asset in assets:
        name = asset.get("name", "")
        if name.endswith("-linux-x86_64.tar.gz"):
            x86_64_asset = asset
        elif name.endswith("-linux-aarch64.tar.gz"):
            aarch64_asset = asset

    if not x86_64_asset:
        raise ValueError("Linux x86_64 artifact not found in release")
    if not aarch64_asset:
        raise ValueError("Linux aarch64 artifact not found in release")

    # Extract version from asset name (e.g., "Keyguard-2.3.3-linux-x86_64.tar.gz")
    version_match = re.search(r"Keyguard-(\d+\.\d+\.\d+)-linux", x86_64_asset["name"])
    if not version_match:
        raise ValueError(f"Could not extract version from asset name: {x86_64_asset['name']}")
    version = version_match.group(1)

    # Extract SHA256 hashes from digest field (format: "sha256:<hash>")
    def extract_sha256(asset: dict) -> str:
        digest = asset.get("digest", "")
        if not digest.startswith("sha256:"):
            raise ValueError(f"SHA256 digest not found for asset: {asset['name']}")
        return digest[7:]  # Remove "sha256:" prefix

    sha256_x86_64 = extract_sha256(x86_64_asset)
    sha256_aarch64 = extract_sha256(aarch64_asset)

    return version, release_tag, sha256_x86_64, sha256_aarch64


def update_pkgbuild(
    content: str,
    version: str,
    release_tag: str,
    sha256_x86_64: str,
    sha256_aarch64: str,
) -> str:
    """Update PKGBUILD content with new release information.

    Args:
        content: The original PKGBUILD content.
        version: The new package version.
        release_tag: The GitHub release tag.
        sha256_x86_64: SHA256 hash for x86_64 artifact.
        sha256_aarch64: SHA256 hash for aarch64 artifact.

    Returns:
        The updated PKGBUILD content.

    Raises:
        ValueError: If required fields are not found in PKGBUILD.
    """
    # Extract current version to determine if pkgrel should be reset
    current_version_match = re.search(r"^pkgver=(.+)$", content, re.MULTILINE)
    if not current_version_match:
        raise ValueError("pkgver not found in PKGBUILD")
    current_version = current_version_match.group(1)

    # Update pkgver
    new_content, count = re.subn(
        r"^pkgver=.+$",
        f"pkgver={version}",
        content,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise ValueError("pkgver not found in PKGBUILD")

    # Update pkgrel: reset to 1 if version changed, otherwise keep as-is
    if current_version != version:
        new_content, count = re.subn(
            r"^pkgrel=.+$",
            "pkgrel=1",
            new_content,
            flags=re.MULTILINE,
        )
        if count == 0:
            raise ValueError("pkgrel not found in PKGBUILD")

    # Update _releaseTag
    new_content, count = re.subn(
        r"^_releaseTag=.+$",
        f"_releaseTag='{release_tag}'",
        new_content,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise ValueError("_releaseTag not found in PKGBUILD")

    # Update sha256sums_x86_64
    new_content, count = re.subn(
        r"^sha256sums_x86_64=\(.+\)$",
        f"sha256sums_x86_64=('{sha256_x86_64}')",
        new_content,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise ValueError("sha256sums_x86_64 not found in PKGBUILD")

    # Update sha256sums_aarch64
    new_content, count = re.subn(
        r"^sha256sums_aarch64=\(.+\)$",
        f"sha256sums_aarch64=('{sha256_aarch64}')",
        new_content,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise ValueError("sha256sums_aarch64 not found in PKGBUILD")

    return new_content


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Update PKGBUILD with latest Keyguard release from GitHub.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s PKGBUILD PKGBUILD.new    # Create updated copy
    %(prog)s PKGBUILD PKGBUILD        # Update in-place
        """,
    )
    parser.add_argument(
        "input",
        help="Path to the input PKGBUILD file",
    )
    parser.add_argument(
        "output",
        help="Path to save the updated PKGBUILD file",
    )

    args = parser.parse_args()

    # Read input PKGBUILD
    print(f"Reading PKGBUILD from: {args.input}")
    with open(args.input, "r", encoding="utf-8") as f:
        content = f.read()

    # Fetch latest release from GitHub
    print(f"Fetching latest release from GitHub...")
    release = fetch_latest_release()

    # Extract release information
    version, release_tag, sha256_x86_64, sha256_aarch64 = extract_release_info(release)

    print(f"  Version: {version}")
    print(f"  Release tag: {release_tag}")
    print(f"  SHA256 (x86_64): {sha256_x86_64}")
    print(f"  SHA256 (aarch64): {sha256_aarch64}")

    # Update PKGBUILD
    print("Updating PKGBUILD...")
    updated_content = update_pkgbuild(
        content,
        version,
        release_tag,
        sha256_x86_64,
        sha256_aarch64,
    )

    # Write output PKGBUILD
    print(f"Writing updated PKGBUILD to: {args.output}")
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
