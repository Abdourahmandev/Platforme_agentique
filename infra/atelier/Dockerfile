# Atelier: isolated SSH execution environment for Paperclip coding agents.
# Documented exception to "official images only": no official image ships
# sshd + OpenCode. Base and tool versions are pinned; rebuild to upgrade.
FROM node@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20

ARG OPENCODE_VERSION=1.18.34

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      openssh-server git ca-certificates curl python3 python3-venv python3-pip tini \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g --no-fund --no-audit "opencode-ai@${OPENCODE_VERSION}" \
 && npm cache clean --force \
 && mkdir -p /run/sshd /work /etc/ssh/host \
 && chown node:node /work \
 && usermod -p '*' node \
 && rm -f /etc/ssh/ssh_host_*

COPY sshd_config /etc/ssh/sshd_config
# git authenticates to GitHub through gh (credential read from ~/.config/gh/hosts.yml).
RUN git config --system credential.https://github.com.helper '' \
 && git config --system --add credential.https://github.com.helper '!/usr/local/bin/gh auth git-credential'
# Models through LiteLLM only; each agent's key arrives per run as LITELLM_API_KEY.
COPY --chown=node:node opencode.json /home/node/.config/opencode/opencode.json
COPY entrypoint.sh /usr/local/bin/atelier-entrypoint
RUN chmod 755 /usr/local/bin/atelier-entrypoint

EXPOSE 2222
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/atelier-entrypoint"]
