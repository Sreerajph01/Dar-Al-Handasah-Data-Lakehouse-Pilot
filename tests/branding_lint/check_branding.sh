#!/usr/bin/env bash
# =============================================================================
# tests/branding_lint/check_branding.sh
# Scans the repository for forbidden branding terms.
# Run by: make lint-branding (inside make verify)
#
# Rules:
#   - Pattern is case-insensitive
#   - Excludes: this script itself, node_modules, .git, .next, target,
#     __pycache__, *.lock files, the M0_PLAN.md planning doc
#   - Exits 1 if any match found
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
THIS_SCRIPT="$(realpath "${BASH_SOURCE[0]}")"
RELATIVE_THIS="${THIS_SCRIPT#${REPO_ROOT}/}"

echo "=== Branding Lint ==="
echo "Scanning: ${REPO_ROOT}"
echo "Forbidden terms: minio (case-insensitive)"
echo ""

FORBIDDEN_PATTERN="[Mm][Ii][Nn][Ii][Oo]"

FOUND=$(grep \
  --recursive \
  --line-number \
  --include="*.yml"  \
  --include="*.yaml" \
  --include="*.py"   \
  --include="*.md"   \
  --include="*.toml" \
  --include="*.json" \
  --include="*.sh"   \
  --include="*.tf"   \
  --include="*.rego" \
  --include="*.sql"  \
  --include="*.properties" \
  --include="*.env"  \
  --include="*.env.example" \
  --include="Makefile" \
  --include="Dockerfile" \
  --exclude-dir=".git" \
  --exclude-dir="node_modules" \
  --exclude-dir=".next" \
  --exclude-dir="target" \
  --exclude-dir="__pycache__" \
  --exclude-dir=".terraform" \
  --exclude="*.lock" \
  --exclude="package-lock.json" \
  --exclude="yarn.lock" \
  --exclude="poetry.lock" \
  -e "${FORBIDDEN_PATTERN}" \
  "${REPO_ROOT}" 2>/dev/null \
  | grep -v "^${THIS_SCRIPT}:" \
  | grep -v "${RELATIVE_THIS}" \
  | grep -v "M0_PLAN.md" \
  | grep -v "LICENSES.md" \
  || true)

if [[ -n "${FOUND}" ]]; then
  echo "❌ BRANDING LINT FAILED — forbidden term found:"
  echo ""
  echo "${FOUND}"
  echo ""
  echo "Remove all references to the forbidden term and re-run."
  exit 1
else
  echo "✅ Branding lint PASSED — no forbidden terms found."
  exit 0
fi
