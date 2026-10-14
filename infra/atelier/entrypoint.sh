#!/bin/sh
# Persistent host key (generated once in the mounted volume), then sshd in the foreground.
set -eu
if [ ! -f /etc/ssh/host/ssh_host_ed25519_key ]; then
    ssh-keygen -q -t ed25519 -N '' -f /etc/ssh/host/ssh_host_ed25519_key
fi
chmod 600 /etc/ssh/host/ssh_host_ed25519_key
exec /usr/sbin/sshd -D -e
