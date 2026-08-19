"""Publishes the v1.0.0-phase7 Pre-Release to GitHub via REST API."""
import os
import sys
import json
import urllib.request
from pathlib import Path

OWNER = "anandkrshnn-ai"
REPO = "semantic-reliability-engine"
TAG_NAME = "v1.0.0-phase7"
RELEASE_TITLE = "v1.0.0-phase7: Semantic Mutation Testing & Holdout Benchmark for Analytics"
RELEASE_NOTES_PATH = Path(__file__).resolve().parent.parent / "docs" / "RELEASE_NOTES_v1.0.0-phase7.md"


def publish_release(token: str):
    if not RELEASE_NOTES_PATH.exists():
        print(f"Error: Release notes not found at {RELEASE_NOTES_PATH}")
        sys.exit(1)

    body_text = RELEASE_NOTES_PATH.read_text(encoding="utf-8")

    payload = {
        "tag_name": TAG_NAME,
        "name": RELEASE_TITLE,
        "body": body_text,
        "draft": False,
        "prerelease": True
    }

    url = f"https://api.github.com/repos/{OWNER}/{REPO}/releases"
    data = json.dumps(payload).encode("utf-8")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "SemanticReliabilityEngine-Publisher",
        "Content-Type": "application/json"
    }

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            print(f"✅ Successfully created GitHub Release!")
            print(f"🔗 Release URL: {res_data.get('html_url')}")
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        print(f"❌ GitHub API Error ({e.code}): {err_msg}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not token:
        print("Usage: python scripts/create_release.py <GITHUB_TOKEN>")
        print("Or set GITHUB_TOKEN environment variable.")
        sys.exit(1)

    publish_release(token)
