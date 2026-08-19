#!/usr/bin/env python3
"""
Updates the GitHub Release target_commitish to 'main' and injects the release notes.
Usage: python scripts/update_release.py <YOUR_GITHUB_PAT>
"""
import sys
import os
import requests
from pathlib import Path

OWNER = "anandkrshnn-ai"
REPO = "semantic-reliability-engine"
TAG = "v1.0.0-phase7"
TARGET_BRANCH = "main"
RELEASE_NOTES_PATH = Path("docs/RELEASE_NOTES_v1.0.0-phase7.md")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/update_release.py <GITHUB_PAT>")
        print("  (Personal Access Token needs 'repo' scope)")
        sys.exit(1)

    token = sys.argv[1]
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    # 1. Load Release Notes
    if not RELEASE_NOTES_PATH.exists():
        print(f"❌ Error: Release notes not found at {RELEASE_NOTES_PATH}")
        print("   Please save the markdown content to that file first.")
        sys.exit(1)
        
    body_content = RELEASE_NOTES_PATH.read_text(encoding="utf-8")
    print(f"✅ Loaded release notes ({len(body_content)} chars)")

    # 2. Fetch existing release by tag to get its ID
    print(f"🔍 Fetching release for tag '{TAG}'...")
    get_url = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/tags/{TAG}"
    response = requests.get(get_url, headers=headers)

    if response.status_code == 404:
        print(f"❌ Release '{TAG}' not found. Creating a new pre-release instead...")
        create_url = f"https://api.github.com/repos/{OWNER}/{REPO}/releases"
        payload = {
            "tag_name": TAG,
            "target_commitish": TARGET_BRANCH,
            "name": TAG,
            "body": body_content,
            "draft": False,
            "prerelease": True
        }
        res = requests.post(create_url, headers=headers, json=payload)
        if res.status_code in (200, 201):
            print(f"🎉 Successfully created release {TAG}!")
            print(f"🔗 {res.json().get('html_url')}")
        else:
            print(f"❌ Failed to create release: {res.status_code} - {res.text}")
        return

    elif response.status_code != 200:
        print(f"❌ Failed to fetch release: {response.status_code} - {response.text}")
        sys.exit(1)

    release_data = response.json()
    release_id = release_data["id"]
    print(f"✅ Found Release ID: {release_id}")

    # 3. Update the release (target_commitish and body)
    print(f"🔄 Updating target_commitish to '{TARGET_BRANCH}' and injecting release notes...")
    patch_url = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/{release_id}"
    payload = {
        "target_commitish": TARGET_BRANCH,
        "body": body_content,
        "prerelease": True
    }
    
    patch_response = requests.patch(patch_url, headers=headers, json=payload)

    if patch_response.status_code == 200:
        html_url = patch_response.json().get("html_url")
        print("🎉 Successfully updated release!")
        print(f"🔗 View here: {html_url}")
    else:
        print(f"❌ Failed to update release: {patch_response.status_code}")
        print(patch_response.text)
        sys.exit(1)


if __name__ == "__main__":
    main()
