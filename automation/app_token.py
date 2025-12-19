from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a GitHub App installation token.")
    parser.add_argument("--app-id", required=True, type=int, help="GitHub App ID")
    parser.add_argument("--key", required=True, help="Path to the GitHub App private key (.pem)")
    parser.add_argument("--repo", default=None, help="Target repo in owner/name form")
    parser.add_argument("--org", default=None, help="Target org name (optional)")
    parser.add_argument("--installation-id", type=int, default=None, help="Known installation ID (optional)")
    parser.add_argument("--json", action="store_true", help="Print JSON with token + expiry")
    parser.add_argument("--export", action="store_true", help="Print export line for GITHUB_TOKEN")
    return parser.parse_args()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _sign_jwt(message: bytes, key_path: Path) -> str:
    result = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(key_path)],
        input=message,
        capture_output=True,
        check=True,
    )
    return _b64url(result.stdout)


def _build_jwt(app_id: int, key_path: Path) -> str:
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": app_id}
    header = {"alg": "RS256", "typ": "JWT"}
    header_b64 = _b64url(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature_b64 = _sign_jwt(signing_input, key_path)
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def _request(url: str, token: str, method: str = "GET") -> dict:
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "runledger-app-token",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _find_installation(jwt_token: str, repo: str | None, org: str | None) -> int:
    if repo:
        url = f"https://api.github.com/repos/{repo}/installation"
    elif org:
        url = f"https://api.github.com/orgs/{org}/installation"
    else:
        raise SystemExit("Provide --repo owner/name or --org org-name.")
    payload = _request(url, jwt_token)
    installation_id = payload.get("id")
    if not installation_id:
        raise SystemExit(f"Unable to locate installation for {repo or org}.")
    return int(installation_id)


def _create_installation_token(jwt_token: str, installation_id: int) -> dict:
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "runledger-app-token",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    args = parse_args()
    key_path = Path(args.key)
    if not key_path.exists():
        raise SystemExit(f"Key not found: {key_path}")

    try:
        jwt_token = _build_jwt(args.app_id, key_path)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Failed to sign JWT (openssl required): {exc}") from exc

    installation_id = args.installation_id or _find_installation(jwt_token, args.repo, args.org)
    token_payload = _create_installation_token(jwt_token, installation_id)
    token = token_payload.get("token")
    expires_at = token_payload.get("expires_at")
    if not token:
        raise SystemExit("Failed to create installation token.")

    if args.json:
        print(json.dumps({"token": token, "expires_at": expires_at}, indent=2))
    elif args.export:
        print(f"export GITHUB_TOKEN=\"{token}\"")
    else:
        print(token)

    if expires_at:
        print(f"Token expires at: {expires_at}", file=sys.stderr)


if __name__ == "__main__":
    main()
