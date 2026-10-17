"""Generate a NEW ignored, local deployment key bundle; never echo secret values."""

import hashlib
import json
import secrets
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / "work" / "deployment-secrets"
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / f"keys-{secrets.token_hex(8)}.json"
    operator, backend, session = (secrets.token_urlsafe(32) for _ in range(3))
    values = {
        "operator_access_key": operator,
        "RELIABILITY_OPERATOR_KEY_SHA256": hashlib.sha256(operator.encode()).hexdigest(),
        "RELIABILITY_SESSION_KEY": session,
        "API_ACCESS_TOKEN": backend,
        "RELIABILITY_BACKEND_TOKEN": backend,
    }
    with output.open("x", encoding="utf-8") as handle:
        json.dump(values, handle, indent=2)
    output.chmod(0o600)
    # Local OS ACLs still govern Windows access. Store the bundle in a password manager.
    print("New keys saved to " + str(output.relative_to(root)))
    print("Secret values were not printed. Existing .env and deployed keys were not changed.")


if __name__ == "__main__":
    main()
