#!/usr/bin/env bash
set -euo pipefail
# Run as the NAS account whose shell the terminal should expose.
[[ $(id -u) != 0 ]] || { echo 'Run as a normal NAS user, not root.'; exit 1; }
command -v tmux >/dev/null || { echo 'Install tmux first.'; exit 1; }
command -v python3 >/dev/null
mountpoint -q /vol1 || { echo '/vol1 is not mounted; refusing to install on root disk.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
install_dir="/vol1/homepage-terminal-$(id -un)"
[[ "$install_dir" =~ ^/[a-zA-Z0-9/_-]+$ ]] || exit 1
[[ ! -L "$install_dir" ]] || exit 1
mkdir -p "$install_dir"
[[ -O "$install_dir" ]] || { echo 'Install directory is not owned by this user.'; exit 1; }
chmod 700 "$install_dir"
python3 -m venv "$install_dir/venv"
"$install_dir/venv/bin/pip" install --disable-pip-version-check -r "$source_dir/requirements.txt"
install -m 600 "$source_dir/agent.py" "$install_dir/agent.py"
install -m 600 "$source_dir/duplicates.py" "$install_dir/duplicates.py"
install -m 600 "$source_dir/cloud_cleanup.py" "$install_dir/cloud_cleanup.py"
config_dir="$HOME/.config/homepage-terminal"
mkdir -p "$config_dir"
chmod 700 "$config_dir"
if [[ ! -f "$config_dir/config.json" ]]; then
 "$install_dir/venv/bin/python" "$source_dir/setup_config.py" "$config_dir/config.json"
fi
mkdir -p "$HOME/.config/systemd/user"
unit="$HOME/.config/systemd/user/homepage-terminal.service"
if [[ -f "$unit" ]]; then cp -p "$unit" "$unit.before-update"; fi
cat > "$unit" <<UNIT
[Unit]
Description=Homepage NAS outbound terminal agent
After=network-online.target
[Service]
Type=simple
ExecStartPre=/usr/bin/mountpoint -q /vol1
ExecStart=$install_dir/venv/bin/python $install_dir/agent.py %h/.config/homepage-terminal/config.json
KillMode=process
TimeoutStopSec=10
Restart=on-failure
RestartSec=10
UMask=0077
NoNewPrivileges=true
[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now homepage-terminal.service
# Restart only this new agent on subsequent installs. tmux shells survive.
systemctl --user restart homepage-terminal.service
systemctl --user is-active homepage-terminal.service
