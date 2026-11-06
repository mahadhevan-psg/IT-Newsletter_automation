#!/bin/sh
# Everything the system changes while running lives on ONE persistent disk (DATA_DIR, /data):
#   the two databases, the Word files and uploaded photos (output/), and the settings edited in the newsletter studio.
# A container's own filesystem is wiped on every deploy, so those places are pointed at the disk here, then the server starts.
set -e

DATA="${DATA_DIR:-/data}"
APP=/app

mkdir -p "$DATA/config" "$DATA/output"

# settings the studio edits (forms, sections, layouts, front pages): start from the shipped copy, then keep the disk's copy forever
for f in form_mappings.json section_categories.json section_layouts.json front_matter.json; do
    if [ ! -e "$DATA/config/$f" ] && [ -f "$APP/config/$f" ]; then
        cp "$APP/config/$f" "$DATA/config/$f"
    fi
    ln -sfn "$DATA/config/$f" "$APP/config/$f"
done

# generated newsletters, cached images, uploaded photos
rm -rf "$APP/output"
ln -sfn "$DATA/output" "$APP/output"

# the databases are found through MASTER_DB_PATH / NEWSLETTER_DB_PATH (set in the Dockerfile and render.yaml), both inside $DATA
chown -R app:app "$DATA"

if [ -z "$MASTER_SECRET" ]; then
    echo "[warning] MASTER_SECRET is not set: sign-in sessions will use a key kept on the disk. Set MASTER_SECRET for a fixed key." >&2
fi
if [ -z "$MASTER_ADMIN_PASSWORD" ] && [ ! -f "$MASTER_DB_PATH" ]; then
    echo "[warning] MASTER_ADMIN_PASSWORD is not set: a first-admin password will be generated and written to $DATA/INITIAL_ADMIN_PASSWORD.txt" >&2
fi

# drop root, then run the server (setpriv is part of util-linux, already in the image)
exec setpriv --reuid=app --regid=app --init-groups "$@"
