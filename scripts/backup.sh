#!/usr/bin/env bash
# Nightly backup: DB + Graph auth state -> data/backups/ and Google
# Drive (OE-ADR-040). Run from the repo root (systemd sets
# WorkingDirectory=). Fails loudly (set -e) so systemd's OnFailure=
# alert actually triggers when a step breaks.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DATE="$(date +%F)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

BACKUP_NAME="opportunity-engine-backup-${DATE}"
BUNDLE_DIR="${WORKDIR}/${BACKUP_NAME}"
mkdir -p "$BUNDLE_DIR"

# Safe online snapshot + integrity check (system python3, not the venv -
# this script has no dependency on the app's venv being healthy).
python3 scripts/backup_db.py data/opportunity_engine.db "${BUNDLE_DIR}/opportunity_engine.db"

# Graph auth state, if present (harmless if Graph mail isn't configured yet).
[ -f data/graph_token_cache.json ] && cp data/graph_token_cache.json "$BUNDLE_DIR"/
[ -f data/graph_delta_link.txt ] && cp data/graph_delta_link.txt "$BUNDLE_DIR"/
# .env is deliberately excluded - real API keys/tokens don't belong in
# a Google Drive backup by default.

TARBALL="${WORKDIR}/${BACKUP_NAME}.tar.gz"
tar czf "$TARBALL" -C "$WORKDIR" "$BACKUP_NAME"

mkdir -p data/backups
cp "$TARBALL" data/backups/
find data/backups -name 'opportunity-engine-backup-*.tar.gz' -mtime +14 -delete

rclone copy "$TARBALL" gdrive:OpportunityEngine-Backups/
rclone delete gdrive:OpportunityEngine-Backups/ --min-age 14d

echo "Backup complete: ${BACKUP_NAME}.tar.gz"
