# devbox - a remote development container you reach over SSH.
#
# Defaults build a CPU image on ubuntu:24.04. For NVIDIA GPUs, pass a CUDA
# devel base and the matching torch wheel index, e.g.
#   --build-arg BASE_IMAGE=nvidia/cuda:12.8.0-devel-ubuntu24.04
#   --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128
# Expect a large image (~15 GB with CUDA) and a long first build.
#
# Runtime contract (see README.md): /etc/ssh/authorized_keys.d/dev must hold
# at least one public key, and /work must be a mount.

ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}

ARG DEV_UID=1000
ARG DEV_GID=1000
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG NODE_MAJOR=22

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    DEV_UID=${DEV_UID} \
    DEV_GID=${DEV_GID} \
    VIRTUAL_ENV=/opt/venv \
    PATH=/home/dev/.local/bin:/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# One apt layer. Splitting `apt-get update` into its own layer is what
# makes these images fail months later with stale-index errors.
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-server sudo ca-certificates curl wget gnupg \
      git git-lfs build-essential pkg-config \
      python3 python3-venv python3-dev \
      unzip zip jq ripgrep fd-find tmux htop vim nano less rsync \
      netcat-openbsd util-linux locales tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd

# Python in a venv owned by dev, so plain `pip install` works as the dev
# user instead of --break-system-packages fighting the distro packages.
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools

RUN /opt/venv/bin/pip install --no-cache-dir torch torchvision torchaudio \
      --index-url ${TORCH_INDEX_URL}

RUN /opt/venv/bin/pip install --no-cache-dir \
      numpy pandas polars pyarrow \
      matplotlib seaborn \
      anthropic openai tiktoken sentence-transformers \
      httpx aiohttp pydantic python-dotenv \
      jupyterlab ipykernel \
      ruff pytest

RUN curl -fsSL https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
    && curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 - \
    && ln -sf /opt/poetry/bin/poetry /usr/local/bin/poetry

RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code

# Docker CLI only. Do not mount the host's docker socket: with passwordless
# sudo below, that would hand container users root on the host.
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
       | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI. Its login lives in ~/.config/gh, so it survives rebuilds when
# /home/dev is a volume - but the binary must come from the image, or git's
# `gh auth git-credential` helper breaks on the next redeploy.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# No password is ever set - the account is locked and only key auth works.
# Passwordless sudo is acceptable precisely because the docker socket is not
# mounted, so there is no path from container root to host root.
# Ubuntu 24.04 images (including the CUDA ones built on them) ship a
# default 'ubuntu' user at uid/gid 1000, so creating dev at 1000 fails
# with "UID already in use" until that one is removed.
RUN userdel -r ubuntu 2>/dev/null || true \
    && groupdel ubuntu 2>/dev/null || true \
    && groupadd -g ${DEV_GID} dev \
    && useradd -m -s /bin/bash -u ${DEV_UID} -g ${DEV_GID} dev \
    && usermod -L dev \
    && echo 'dev ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/dev \
    && chmod 0440 /etc/sudoers.d/dev \
    && chown -R ${DEV_UID}:${DEV_GID} /opt/venv

# Shell setup is stored in the image and applied by the entrypoint, not
# written into /home/dev at build time. /home/dev is usually a volume, and
# whether docker seeds a volume from the image depends on how it is backed -
# the entrypoint makes it deterministic instead.
# Only a shell that starts in $HOME (a plain `ssh` login) moves to /work; an
# editor terminal opened in a project folder must stay where it was opened.
RUN mkdir -p /etc/devbox /work \
    && printf '%s\n' \
      '# devbox-shell-setup (marker: do not remove, prevents re-appending)' \
      "alias ll='ls -la'" \
      "alias la='ls -A'" \
      "alias l='ls -CF'" \
      "alias gpus='nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv'" \
      "alias gpuwho='nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory,process_name --format=csv'" \
      'export VIRTUAL_ENV=/opt/venv' \
      '[ "$PWD" = "$HOME" ] && cd /work 2>/dev/null || true' \
      '[ -t 1 ] && command -v nvidia-smi >/dev/null && echo "GPUs may be shared with other workloads on this host - run gpus before you grab one." || true' \
      > /etc/devbox/bashrc.append \
    && chown -R ${DEV_UID}:${DEV_GID} /home/dev

# sshd drop-in; Ubuntu's sshd_config Includes this dir first and first
# match wins, so these beat the shipped defaults.
#   - authorized keys come from a root-owned read-only path, which avoids
#     the StrictModes rejections you get when ~/.ssh arrives via a bind
#     mount with the wrong owner or mode
#   - host keys live in /etc/ssh/host_keys, meant to be a volume, so the box
#     keeps one stable SSH identity across rebuilds
RUN printf '%s\n' \
      'PermitRootLogin no' \
      'PasswordAuthentication no' \
      'KbdInteractiveAuthentication no' \
      'PubkeyAuthentication yes' \
      'PermitEmptyPasswords no' \
      'AllowUsers dev' \
      'AuthorizedKeysFile /etc/ssh/authorized_keys.d/%u .ssh/authorized_keys' \
      'HostKey /etc/ssh/host_keys/ssh_host_ed25519_key' \
      'HostKey /etc/ssh/host_keys/ssh_host_rsa_key' \
      'ClientAliveInterval 30' \
      'ClientAliveCountMax 240' \
      'TCPKeepAlive yes' \
      'X11Forwarding no' \
      'PrintMotd no' \
      'AcceptEnv LANG LC_* TERM COLORTERM' \
      > /etc/ssh/sshd_config.d/10-devbox.conf \
    && mkdir -p /etc/ssh/authorized_keys.d /etc/ssh/host_keys

# A docker image's ENV does NOT reach ssh sessions: sshd builds a fresh
# environment and hands out the distro default PATH, so `python` from the
# venv is simply not found over ssh even though ENV PATH lists it. Three
# layers fix it for every shape of session:
#   /etc/environment   - read by pam_env, so it covers `ssh box cmd`
#                        (non-interactive, non-login) which sources nothing
#   /etc/profile.d     - covers interactive and login shells
#   symlink            - last resort if PAM is ever disabled
RUN printf '%s\n' \
      'PATH=/home/dev/.local/bin:/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
      'VIRTUAL_ENV=/opt/venv' \
      'LANG=C.UTF-8' \
      'CUDA_DEVICE_ORDER=PCI_BUS_ID' \
      > /etc/environment \
    && printf '%s\n' \
      'export PATH=/home/dev/.local/bin:/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
      'export VIRTUAL_ENV=/opt/venv' \
      > /etc/profile.d/10-devbox.sh \
    && chmod 0644 /etc/profile.d/10-devbox.sh \
    && ln -sf /opt/venv/bin/python /usr/local/bin/python

RUN printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'mkdir -p /etc/ssh/host_keys' \
      'if [ ! -f /etc/ssh/host_keys/ssh_host_ed25519_key ]; then' \
      "  ssh-keygen -q -t ed25519 -N '' -f /etc/ssh/host_keys/ssh_host_ed25519_key" \
      'fi' \
      'if [ ! -f /etc/ssh/host_keys/ssh_host_rsa_key ]; then' \
      "  ssh-keygen -q -t rsa -b 4096 -N '' -f /etc/ssh/host_keys/ssh_host_rsa_key" \
      'fi' \
      'chmod 600 /etc/ssh/host_keys/*_key' \
      'chmod 644 /etc/ssh/host_keys/*.pub' \
      'chown dev:dev /home/dev 2>/dev/null || true' \
      '' \
      '# Provision the home dir. A fresh home volume may start empty - seed' \
      '# it rather than assume docker did.' \
      'if [ ! -f /home/dev/.bashrc ]; then' \
      '  cp /etc/skel/.bashrc /home/dev/.bashrc' \
      'fi' \
      'if ! grep -q devbox-shell-setup /home/dev/.bashrc; then' \
      '  cat /etc/devbox/bashrc.append >> /home/dev/.bashrc' \
      'fi' \
      'mkdir -p /home/dev/.cache/huggingface /home/dev/.ssh' \
      'chmod 700 /home/dev/.ssh' \
      'chown -R dev:dev /home/dev/.bashrc /home/dev/.cache /home/dev/.ssh' \
      '' \
      '# Password auth is off, so empty authorized_keys means a box nobody' \
      '# can enter. Fail now and loudly, not at connect time.' \
      'if [ ! -s /etc/ssh/authorized_keys.d/dev ]; then' \
      '  echo "FATAL: /etc/ssh/authorized_keys.d/dev is missing or empty." >&2' \
      '  echo "       Mount a file holding your public key there (read-only)." >&2' \
      '  exit 1' \
      'fi' \
      '' \
      '# Refuse to run with /work unmounted. Otherwise a detached network share' \
      '# looks exactly like an empty working directory and work goes missing.' \
      '# To get a shell without it, bypass this entrypoint:' \
      '#   docker compose run --rm --entrypoint sh devbox' \
      'if ! mountpoint -q /work; then' \
      '  echo "FATAL: /work is not a mount point - the work volume is not attached." >&2' \
      '  echo "       Check the volume mounted at /work, then start the container again." >&2' \
      '  exit 1' \
      'fi' \
      '' \
      'exec /usr/sbin/sshd -D -e' \
      > /usr/local/bin/devbox-entrypoint \
    && chmod 0755 /usr/local/bin/devbox-entrypoint

EXPOSE 22 8888
ENTRYPOINT ["/usr/local/bin/devbox-entrypoint"]
