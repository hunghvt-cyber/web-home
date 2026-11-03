#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
python3 -m venv "$repo/.schedule-venv"
"$repo/.schedule-venv/bin/pip" install -r "$repo/scripts/schedules/requirements.txt"
# Verify publishing before enabling a timer. No backup/recording service is changed.
"$repo/.schedule-venv/bin/python" "$repo/scripts/schedules/publish_nas.py"
mkdir -p "$HOME/.config/systemd/user"
case "$repo" in *'%'*|*'"'*|*'\\'*) echo 'Unsupported checkout path'; exit 1;; esac
cat > "$HOME/.config/systemd/user/homepage-schedules.service" <<EOF
[Unit]
Description=Read-only NAS schedule metadata publisher
[Service]
Type=oneshot
ExecStart="$repo/.schedule-venv/bin/python" "$repo/scripts/schedules/publish_nas.py"
UMask=0077
TimeoutStartSec=240
EOF
cat > "$HOME/.config/systemd/user/homepage-schedules.timer" <<'EOF'
[Unit]
Description=Refresh homepage schedule inventory
[Timer]
OnBootSec=3min
OnUnitActiveSec=20min
RandomizedDelaySec=60
[Install]
WantedBy=timers.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now homepage-schedules.timer
echo 'NAS_SCHEDULE_INSTALL=PASS'
