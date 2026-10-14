# Atelier: isolated SSH execution environment for Paperclip coding agents.
# Documented exception to "official images only": no official image ships
# sshd + OpenCode. Base and tool versions are pinned; rebuild to upgrade.
FROM node@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20

ARG OPENCODE_VERSION=1.18.34
# GitHub CLI, pinned and checksum-verified: used by agents for PRs and as git's credential helper.
ARG GH_VERSION=2.102.0

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      openssh-server git ca-certificates curl python3 python3-venv python3-pip tini \
 && rm -rf /var/lib/apt/lists/* \
 && cd /tmp \
 && curl -fsSLO "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
 && curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_checksums.txt" \
      | grep " gh_${GH_VERSION}_linux_amd64.tar.gz\$" | sha256sum -c - \
 && tar -xzf "gh_${GH_VERSION}_linux_amd64.tar.gz" \
 && install -m 755 "gh_${GH_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh \
 && rm -rf /tmp/gh_* \
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
