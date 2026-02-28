"""
GitHub Storage Helper
=====================
Reads and writes files to the versuni-ms-wave3 GitHub repo via the REST API.
Used by questionnaire_manager.py and data_hub.py to persist uploaded files
without needing external object storage.

Required Streamlit secret:
    GITHUB_TOKEN  — a Personal Access Token with repo write scope

Repo is inferred from the Git remote URL but can be overridden via secrets:
    GITHUB_OWNER = "nijhuis777"
    GITHUB_REPO  = "versuni-ms-wave3"
    GITHUB_BRANCH = "main"
"""

from __future__ import annotations
import base64
import os
from typing import Optional

import requests


# ─── Config helpers ────────────────────────────────────────────────────────────

def _get_secret(key: str, default: str = "") -> str:
    """Read from env var, then Streamlit secrets — lazy so Cloud works."""
    val = os.getenv(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return str(st.secrets.get(key, default))
    except Exception:
        return default


def _owner()  -> str: return _get_secret("GITHUB_OWNER",  "nijhuis777")
def _repo()   -> str: return _get_secret("GITHUB_REPO",   "versuni-ms-wave3")
def _branch() -> str: return _get_secret("GITHUB_BRANCH", "main")

def _headers() -> dict:
    token = _get_secret("GITHUB_TOKEN")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

def _api(path: str) -> str:
    return f"https://api.github.com/repos/{_owner()}/{_repo()}/contents/{path}"


# ─── Public helpers ────────────────────────────────────────────────────────────

def is_configured() -> bool:
    """Return True if GITHUB_TOKEN is available."""
    return bool(_get_secret("GITHUB_TOKEN"))


def get_file_sha(path: str) -> Optional[str]:
    """Return the blob SHA of an existing file (needed to update it)."""
    resp = requests.get(_api(path), headers=_headers(),
                        params={"ref": _branch()}, timeout=15)
    if resp.status_code == 200:
        return resp.json().get("sha")
    return None


def read_file(path: str) -> Optional[bytes]:
    """Download a file from the repo. Returns raw bytes or None."""
    resp = requests.get(_api(path), headers=_headers(),
                        params={"ref": _branch()}, timeout=15)
    if resp.status_code == 200:
        return base64.b64decode(resp.json()["content"])
    return None


def commit_file(path: str, content: bytes, message: str) -> bool:
    """Create or update a file in the repo. Returns True on success."""
    sha = get_file_sha(path)
    payload: dict = {
        "message": message,
        "content": base64.b64encode(content).decode(),
        "branch": _branch(),
    }
    if sha:
        payload["sha"] = sha
    resp = requests.put(_api(path), headers=_headers(), json=payload, timeout=30)
    return resp.status_code in (200, 201)


def list_files(path: str) -> list[dict]:
    """List files/directories at a given repo path."""
    resp = requests.get(_api(path), headers=_headers(),
                        params={"ref": _branch()}, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        return data if isinstance(data, list) else []
    return []


def delete_file(path: str, message: str) -> bool:
    """Delete a file from the repo. Returns True on success."""
    sha = get_file_sha(path)
    if not sha:
        return False
    resp = requests.delete(
        _api(path), headers=_headers(),
        json={"message": message, "sha": sha, "branch": _branch()},
        timeout=15,
    )
    return resp.status_code == 200
