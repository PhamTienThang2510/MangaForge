#!/bin/sh
set -e

app_dir='/opt/${sanitizedProductName}'
executable='${executable}'

# Ubuntu 24.04 hạn chế user namespace. Dùng Chrome sandbox do root sở hữu.
chown root:root "$app_dir/chrome-sandbox"
chmod 4755 "$app_dir/chrome-sandbox"
update-alternatives --install "/usr/bin/$executable" "$executable" "$app_dir/$executable" 100
