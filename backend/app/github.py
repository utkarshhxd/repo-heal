from urllib.parse import urlencode

import httpx

from .config import get_settings


settings = get_settings()
GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_BASE = "https://github.com/login/oauth"


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def build_authorize_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_callback_url,
            "scope": "repo user:email",
            "state": state,
            "allow_signup": "true",
        }
    )
    return f"{GITHUB_OAUTH_BASE}/authorize?{query}"


async def exchange_code_for_token(code: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{GITHUB_OAUTH_BASE}/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_callback_url,
            },
        )
        response.raise_for_status()
        payload = response.json()

    if "error" in payload:
        raise RuntimeError(payload["error_description"])
    return str(payload["access_token"])


async def get_authenticated_user(token: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{GITHUB_API_BASE}/user", headers=_headers(token))
        response.raise_for_status()
        return response.json()


async def list_repositories(token: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{GITHUB_API_BASE}/user/repos",
            headers=_headers(token),
            params={
                "sort": "updated",
                "per_page": 100,
                "affiliation": "owner,collaborator,organization_member",
            },
        )
        response.raise_for_status()
        return response.json()


async def list_branches(token: str, repo_full_name: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{GITHUB_API_BASE}/repos/{repo_full_name}/branches",
            headers=_headers(token),
            params={"per_page": 100},
        )
        response.raise_for_status()
        return response.json()


async def create_pull_request(token: str, repo_full_name: str, *, title: str, body: str, head: str, base: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls",
            headers=_headers(token),
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        )
        response.raise_for_status()
        return response.json()


async def merge_pull_request(token: str, repo_full_name: str, pull_number: int, *, merge_method: str = "squash") -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.put(
            f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pull_number}/merge",
            headers=_headers(token),
            json={"merge_method": merge_method},
        )
        response.raise_for_status()
        return response.json()
