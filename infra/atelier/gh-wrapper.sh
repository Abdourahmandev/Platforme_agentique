#!/bin/sh
# Paperclip runs may override XDG_CONFIG_HOME, hiding the atelier's GitHub
# credential from gh (and from git, which authenticates through gh).
# Pin gh to the mounted credential unless a caller sets GH_CONFIG_DIR itself.
export GH_CONFIG_DIR="${GH_CONFIG_DIR:-/home/node/.config/gh}"
exec /usr/local/libexec/gh "$@"
