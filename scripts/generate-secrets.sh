#!/usr/bin/env bash
# =============================================================================
# scripts/generate-secrets.sh
# Copies .env.example → .env (if not present) and replaces all CHANGE_ME_*
# tokens with secure random values.  Safe to re-run: skips existing .env.
# =============================================================================
set -euo pipefail

ROTATE_S3=false
if [[ "${1:-}" == "--rotate-s3" ]]; then
  ROTATE_S3=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--rotate-s3]" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env"
EXAMPLE="${ROOT}/.env.example"

if [[ ! -f "${EXAMPLE}" ]]; then
  echo "ERROR: .env.example not found at ${EXAMPLE}" >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  echo ".env already exists — skipping copy. To regenerate, delete .env first."
else
  cp "${EXAMPLE}" "${ENV_FILE}"
  echo "Copied .env.example → .env"
fi

# Replace each CHANGE_ME_* token with a random secret
python3 - "${ENV_FILE}" "${ROTATE_S3}" <<'PYEOF'
import sys, re, secrets, base64, pathlib

env_file = pathlib.Path(sys.argv[1])
rotate_s3 = sys.argv[2].lower() == "true"
text = env_file.read_text()

def rand_b64(n=32):
    return base64.urlsafe_b64encode(secrets.token_bytes(n)).decode().rstrip("=")

def rand_hex(n=32):
    return secrets.token_hex(n)

def rand_fernet():
    # Fernet key: 32 bytes, base64-encoded (must be exactly 44 chars)
    import base64
    key = base64.urlsafe_b64encode(secrets.token_bytes(32))
    return key.decode()

replacements = {
    "CHANGE_ME_AKID":        lambda: "DARLAKE" + secrets.token_hex(8).upper(),
    "CHANGE_ME_SAK":         lambda: rand_hex(20),
    "CHANGE_ME_PG_META":     lambda: rand_b64(16),
    "CHANGE_ME_LK":          lambda: rand_b64(16),
    "CHANGE_ME_OM":          lambda: rand_b64(16),
    "CHANGE_ME_AF":          lambda: rand_b64(16),
    "CHANGE_ME_FERNET_32B":  rand_fernet,
    "CHANGE_ME_WS_SECRET":   lambda: rand_hex(32),
    "CHANGE_ME_OS_ADMIN":    lambda: "Dar@" + rand_hex(8),
    "CHANGE_ME_KC_ADMIN":    lambda: rand_b64(12),
    "CHANGE_ME_LK_OIDC":     lambda: rand_b64(20),
    "CHANGE_ME_SS_SECRET":   lambda: rand_hex(32),
    "CHANGE_ME_SS_ADMIN":    lambda: rand_b64(12),
    "CHANGE_ME_GF_ADMIN":    lambda: rand_b64(12),
    "CHANGE_ME_GITEA":       lambda: rand_b64(12),
}

for token, gen_fn in replacements.items():
    if token in text:
        text = text.replace(token, gen_fn(), 1)

if rotate_s3:
    text, access_count = re.subn(r"^S3_ACCESS_KEY=.*$", "S3_ACCESS_KEY=DARLAKE" + secrets.token_hex(8).upper(), text, flags=re.MULTILINE)
    text, secret_count = re.subn(r"^S3_SECRET_KEY=.*$", "S3_SECRET_KEY=" + rand_hex(20), text, flags=re.MULTILINE)
    if access_count != 1 or secret_count != 1:
        raise SystemExit("S3_ACCESS_KEY and S3_SECRET_KEY must each appear exactly once")

env_file.write_text(text)
print(f"✓ {'S3 identity rotated in' if rotate_s3 else 'Secrets written to'} {env_file}")
PYEOF
