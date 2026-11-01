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
    DEVBOX_VENV_HOME=/home/dev/venvs \
    UV_CACHE_DIR=/home/dev/.cache/uv \
    PYTHONPYCACHEPREFIX=/home/dev/.cache/pycache \
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

# uv goes to /usr/local/lib/uv, not onto PATH: the wrapper below takes its
# place at /usr/local/bin/uv.
RUN curl -fsSL https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/lib/uv sh \
    && curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 - \
    && ln -sf /opt/poetry/bin/poetry /usr/local/bin/poetry

# A project on a network share must not keep its virtualenv or tool caches
# there. Two reasons, and neither is fixable with mount options:
#   - correctness: /work is visible to other machines with other interpreters,
#     and one directory cannot be a valid venv for two of them
#   - cost: a venv is tens of thousands of files, and SMB is ~33x slower per
#     read than local disk, so every type-check pays for it
# uv discovers the project root by walking up to the nearest pyproject.toml.
# This wrapper does the same, and for a project under a share it redirects the
# environment and the caches onto local disk. A project already on local disk
# is left alone - the default .venv is right there. Setting these here rather
# than in /etc/environment is deliberate: they must be per-project, and a
# wrapper is the only hook that fires for `ssh box 'cmd'` too, which sources
# no shell files at all.
RUN printf '%s\n' \
      '#!/bin/sh' \
      '# devbox uv wrapper: keeps virtualenvs and caches off network shares.' \
      'set -eu' \
      'REAL_UV=/usr/local/lib/uv/uv' \
      '' \
      '# An explicit choice always wins.' \
      'if [ -n "${UV_PROJECT_ENVIRONMENT:-}" ]; then' \
      '  exec "$REAL_UV" "$@"' \
      'fi' \
      '' \
      'root=$PWD' \
      'while [ "$root" != "/" ] && [ ! -f "$root/pyproject.toml" ]; do' \
      '  root=$(dirname "$root")' \
      'done' \
      '' \
      '# /opt/venv is the image general-purpose environment, not any project one.' \
      '# Left set, uv prints a VIRTUAL_ENV-does-not-match warning on every single' \
      '# project command, in every agent transcript.' \
      'if [ "$root" != "/" ]; then' \
      '  unset VIRTUAL_ENV' \
      'fi' \
      '' \
      'case "$root" in' \
      '  /work/*)' \
      '    # basename alone collides across /work/a/api and /work/b/api.' \
      '    tag=$(printf %s "$root" | md5sum | cut -c1-8)' \
      '    slot="$(basename "$root")-$tag"' \
      '    home="${DEVBOX_VENV_HOME:-/home/dev/venvs}"' \
      '    UV_PROJECT_ENVIRONMENT="$home/$slot"' \
      '    MYPY_CACHE_DIR="$home/.caches/$slot/mypy"' \
      '    RUFF_CACHE_DIR="$home/.caches/$slot/ruff"' \
      '    PYTEST_ADDOPTS="${PYTEST_ADDOPTS:+$PYTEST_ADDOPTS }-o cache_dir=$home/.caches/$slot/pytest"' \
      '    export UV_PROJECT_ENVIRONMENT MYPY_CACHE_DIR RUFF_CACHE_DIR PYTEST_ADDOPTS' \
      '    ;;' \
      'esac' \
      '' \
      'exec "$REAL_UV" "$@"' \
      > /usr/local/bin/uv \
    && chmod 0755 /usr/local/bin/uv

# The same share, the other half of the problem. CIFS cannot store a per-file
# exec bit: it synthesizes one mode for every file from the mount options, so a
# file looks executable to a host mounting with file_mode=0755 and not to this
# container at 0664, and git then reports every file in the tree as modified.
# Scoped to /work with a conditional include rather than set globally - repos
# on local disk have real exec bits and must keep tracking them, or a
# `chmod +x` silently stops being recorded. Nothing is lost on the share
# either: git still stores the bit in the index, so CI on a normal filesystem
# checks out correctly.
# Appended with `git config` rather than written: git-lfs already owns
# /etc/gitconfig. System config rather than /home/dev/.gitconfig, because the
# home volume may start empty.
RUN printf '%s\n' \
      '[core]' \
      '    fileMode = false' \
      > /etc/gitconfig-share \
    && git config --system 'includeIf.gitdir:/work/.path' /etc/gitconfig-share

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

# Local backing services and headless-browser libraries, for projects whose
# tests need a real Postgres or Redis or drive a browser. Installed by hand
# at runtime, these vanish on every recreate, since the container layer is
# not a volume.
# Installed, NOT started: nothing here runs until you start it, so they never
# hold 5432/6379 against a project that brings its own via compose. When you
# need them:  sudo service postgresql start ; sudo service redis-server start
# Their data lives in the container layer and is lost on recreate - these are
# scratch databases for tests, not a place to keep anything.
# The browser list is what Playwright's Chromium needs on noble (the t64
# names are 24.04's); the browser binaries themselves stay per-project.
# Its own layer, late in the file, so changing it does not re-download torch.
#
# cron rides in the same layer. It IS started, by the entrypoint, because a
# schedule that only runs while someone remembers to start it is no schedule.
RUN apt-get update && apt-get install -y --no-install-recommends \
      cron \
      postgresql postgresql-contrib redis-server \
      libasound2t64 libatk-bridge2.0-0t64 libatk1.0-0t64 libatspi2.0-0t64 \
      libcairo2 libcups2t64 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0t64 \
      libnspr4 libnss3 libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 \
      libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 xvfb \
      libfontconfig1 libfreetype6 fonts-liberation fonts-noto-color-emoji \
      fonts-unifont fonts-freefont-ttf fonts-ipafont-gothic fonts-wqy-zenhei \
      fonts-tlwg-loma-otf xfonts-cyrillic xfonts-scalable \
    && rm -rf /var/lib/apt/lists/*

# Herdr, the terminal multiplexer that owns the agent panes. The binary comes
# from the image for the same reason gh does above: /home/dev is a volume, so
# a binary installed only there disappears when the volume is recreated, and
# the agent panes it owns would come back as plain shells.
#
# Pinned to an exact release with its checksum rather than "latest": the
# install script fetches a moving manifest, so an unpinned image build is not
# reproducible and a bad release lands on every box at once. Bump both
# together. The skill below must match this version - it is the CLI surface
# the agents are told to use.
ARG HERDR_VERSION=0.9.5
ARG HERDR_SHA256_LINUX_X86_64=14d9e8bc8b4a9e0118d77c32266f76d461f09b40342eb23752960bd89f59929d
RUN set -eu; \
    url="https://github.com/herdrdev/herdr/releases/download/v${HERDR_VERSION}/herdr-linux-x86_64"; \
    curl -fsSL --retry 3 --connect-timeout 10 --max-time 120 "$url" -o /usr/local/bin/herdr \
    && echo "${HERDR_SHA256_LINUX_X86_64}  /usr/local/bin/herdr" | sha256sum -c - \
    && chmod 0755 /usr/local/bin/herdr \
    && /usr/local/bin/herdr --version

# Herdr's agent skill. The agents use it to spawn sibling agents in their own
# panes, which is the only way a subagent becomes visible as its own agent
# rather than disappearing inside the parent process. The skill is pinned to
# the same release as the binary and verified by checksum, so an agent can
# never be told to call a CLI the installed binary does not have.
#
# Stored under /usr/share, not in the agent config dirs: those live in
# /home/dev, which is a volume, and the volume may be recreated empty. The
# entrypoint links it into each agent's skill directory from here.
ARG HERDR_SKILL_SHA256=fbd9d502767f7dff29c211505a0bd9ba34e980ed4cc456247e2adc1642883984
RUN set -eu; \
    mkdir -p /usr/share/devbox/herdr-skill \
    && curl -fsSL --retry 3 --connect-timeout 10 --max-time 60 \
         "https://raw.githubusercontent.com/herdrdev/herdr/v${HERDR_VERSION}/skills/herdr/SKILL.md" \
         -o /usr/share/devbox/herdr-skill/SKILL.md \
    && echo "${HERDR_SKILL_SHA256}  /usr/share/devbox/herdr-skill/SKILL.md" | sha256sum -c - \
    && chmod 0644 /usr/share/devbox/herdr-skill/SKILL.md \
    && chown -R ${DEV_UID}:${DEV_GID} /usr/share/devbox/herdr-skill

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

# tmux defaults. An SSH session that dies takes the shell's children with it -
# a long build, a test run, an agent mid-task. Claude Code has no detach or
# daemon mode (its own docs say to start it inside tmux or screen), so a
# multiplexer is the only thing between a laptop going to sleep and a lost
# session.
#
# Unlike the bashrc above this needs no entrypoint seeding: tmux reads
# /etc/tmux.conf directly, so the config lives in the image and cannot go
# missing with an empty /home/dev volume. A user's own ~/.tmux.conf still
# overrides it. Settings match cheatsheets/tmux-cheatsheet.md so the docs and
# the image cannot drift apart.
#
# The three non-obvious lines each fix a real full-screen-app failure:
#   allow-passthrough  TUI escape sequences never reach the outer terminal
#                      without it, so desktop notifications silently vanish
#   extended-keys      without it Shift+Enter does not reach the application,
#                      so multi-line input breaks only when inside tmux
#   escape-time 0      the 500ms default reads as laggy, garbled keys
#
# Copying is on demand, never on contact. tmux by default copies the moment a
# mouse drag ends, so every stray drag overwrites the clipboard. Here a drag
# only selects, and Ctrl+Insert - the CUA copy key, which is also what a
# desktop-wide Super+C sends to terminals on some Linux desktops - copies.
# With set-clipboard on the copy leaves as OSC 52, so it lands on the
# clipboard of the machine you are sitting at, not the container's.
#
# Claude Code's fullscreen renderer (see CLAUDE_CODE_NO_FLICKER below) owns
# the mouse and keeps its own selection, so the key has to reach it instead.
# Its keybindings cannot name Insert, so tmux hands it Ctrl+Shift+C as a CSI u
# sequence (1b 5b 39 39 3b 36 75 = ESC [99;6u), its own copy key. That is a
# no-op with nothing selected, never an interrupt.
RUN printf '%s\n' \
      '# devbox tmux defaults. Override per-user in ~/.tmux.conf.' \
      '' \
      '# Mouse on, so the wheel scrolls the application rather than tmux' \
      '# history. Hold SHIFT while dragging to select terminal text instead.' \
      'set -g mouse on' \
      '' \
      '# Copy on demand: a drag only selects, Ctrl+Insert (Super+C) copies.' \
      'unbind -T copy-mode MouseDragEnd1Pane' \
      'unbind -T copy-mode-vi MouseDragEnd1Pane' \
      'bind -T copy-mode C-IC send -X copy-pipe-and-cancel' \
      'bind -T copy-mode-vi C-IC send -X copy-pipe-and-cancel' \
      '# Claude Code fullscreen keeps its own selection: send it Ctrl+Shift+C.' \
      "bind -n C-IC if -F '#{&&:#{alternate_on},#{m/r:^claude([.]exe)?\$,#{pane_current_command}}}' 'send-keys -H 1b 5b 39 39 3b 36 75' 'send-keys C-IC'" \
      '' \
      '# True colour, and a terminal type full-screen apps recognise.' \
      'set -g default-terminal "tmux-256color"' \
      'set -ga terminal-overrides ",*256col*:Tc"' \
      '' \
      '# Let OSC 52 clipboard writes and other escape sequences through.' \
      'set -g set-clipboard on' \
      'set -g allow-passthrough on' \
      '' \
      '# No Escape delay.' \
      'set -sg escape-time 0' \
      '' \
      '# Extended keys, so Shift+Enter reaches the application.' \
      'set -s extended-keys on' \
      "set -as terminal-features 'tmux-256color:extkeys'" \
      'bind-key -n S-Enter send-keys Escape "[13;2u"' \
      '' \
      '# Scrollback worth having when you do drop into copy mode (C-b [).' \
      'set -g history-limit 50000' \
      '' \
      '# Number windows and panes from 1; 0 is a long reach.' \
      'set -g base-index 1' \
      'setw -g pane-base-index 1' \
      '' \
      '# Splits bound to the keys they are drawn with.' \
      'bind | split-window -h' \
      'bind - split-window -v' \
      '' \
      '# Plain-English session commands, so day-to-day use needs no flags:' \
      '#   tmux instance <name>   start a named session, or step back into it' \
      '#   tmux resume <name>     reattach to one, evicting a stale client' \
      '#   tmux sessions          list what is still running' \
      '#   tmux detach            already built in' \
      '# The flags live here once instead of in your muscle memory. -s says the' \
      '# argument is a NAME (without it new-session treats it as a command to' \
      '# run); -A re-enters an existing session instead of erroring; and the -d' \
      '# on attach evicts the dead client a dropped link leaves behind, which' \
      '# otherwise squeezes the window down to that ghost terminal size.' \
      '# Indices start at 100 because tmux fills 0-5 with its own aliases.' \
      "set -s command-alias[100] 'instance=new-session -A -s'" \
      "set -s command-alias[101] 'resume=attach -d -t'" \
      "set -s command-alias[102] 'sessions=list-sessions'" \
      '' \
      'bind r source-file /etc/tmux.conf \; display "tmux config reloaded"' \
      > /etc/tmux.conf

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
# UV_CACHE_DIR and PYTHONPYCACHEPREFIX are the two caches that are safe to
# share across every project, so unlike the per-project ones in the uv wrapper
# they belong here. UV_CACHE_DIR must sit on the same filesystem as the
# virtualenvs it feeds - uv hardlinks wheels out of it, and across a
# filesystem boundary it silently degrades to copying every file.
# PYTHONPYCACHEPREFIX mirrors each source file's full absolute path beneath
# the prefix, so projects cannot collide there.
#
# CLAUDE_CODE_NO_FLICKER selects Claude Code's fullscreen renderer. The
# classic renderer redraws a streaming reply in place, but rows that have
# already scrolled off the top cannot be redrawn: when a long table re-lays
# out its columns mid-stream, scrollback keeps every stale width, which reads
# as garbled output on scroll. Fullscreen re-renders the whole transcript on
# the alternate screen, so scrolling always shows the final layout. Opt out
# per user with `unset CLAUDE_CODE_NO_FLICKER` in ~/.bashrc.
RUN printf '%s\n' \
      'PATH=/home/dev/.local/bin:/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
      'VIRTUAL_ENV=/opt/venv' \
      'LANG=C.UTF-8' \
      'CUDA_DEVICE_ORDER=PCI_BUS_ID' \
      'DEVBOX_VENV_HOME=/home/dev/venvs' \
      'UV_CACHE_DIR=/home/dev/.cache/uv' \
      'PYTHONPYCACHEPREFIX=/home/dev/.cache/pycache' \
      'CLAUDE_CODE_NO_FLICKER=1' \
      > /etc/environment \
    && printf '%s\n' \
      'export PATH=/home/dev/.local/bin:/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
      'export VIRTUAL_ENV=/opt/venv' \
      'export DEVBOX_VENV_HOME=/home/dev/venvs' \
      'export UV_CACHE_DIR=/home/dev/.cache/uv' \
      'export PYTHONPYCACHEPREFIX=/home/dev/.cache/pycache' \
      'export CLAUDE_CODE_NO_FLICKER=1' \
      '[ -r /etc/devbox/tmux-commands.sh ] && . /etc/devbox/tmux-commands.sh' \
      '# Start the Herdr server on login. It owns the agent panes, so it must be' \
      '# running before an agent starts, and it dies with the container.' \
      '# Ask the server, do not look for it. pgrep -x herdr also matches herdr' \
      '# remote-client-bridge, a client. And the socket file is no proof either:' \
      '# it lives on the home volume, and a container stop SIGKILLs the server' \
      '# (it is not a child of PID 1), so every recreate leaves a stale socket' \
      '# that would skip the start forever. herdr status exits 0 either way, so' \
      '# read its answer. herdr server replaces a stale socket itself and' \
      '# refuses to start twice, so this is safe to run on every login.' \
      'herdr status 2>/dev/null | grep -q "status: running" || { setsid nohup herdr server >/dev/null 2>&1 </dev/null & }' \
      > /etc/profile.d/10-devbox.sh \
    && chmod 0644 /etc/profile.d/10-devbox.sh \
    && ln -sf /opt/venv/bin/python /usr/local/bin/python

# The tmux command-alias entries in /etc/tmux.conf cannot serve the FIRST
# command of a session. command-alias is a server option read when the server
# starts, so with no server running the client cannot resolve an unknown
# command name - it tries to connect instead of starting one, and you get
# "error connecting to /tmp/tmux-1000/default". `tmux start-server` does not
# help: with no sessions it exits immediately.
#
# So translate in the shell, before tmux is invoked. tmux then sees
# new-session, which it knows how to bootstrap a server for. Everything else
# passes through untouched, and `command tmux` prevents recursion.
#
# This lives in the image and is sourced from /etc/profile.d (login shells)
# and /etc/bash.bashrc (interactive non-login shells, e.g. editor terminals).
# Deliberately NOT in /etc/devbox/bashrc.append: the entrypoint appends that
# only when its marker is absent from /home/dev/.bashrc, so on any box that
# has already booted once, changes there can never arrive.
RUN printf '%s\n' \
      '# devbox tmux commands. See also command-alias in /etc/tmux.conf, which' \
      '# covers non-interactive use once a server is already running.' \
      'tmux() {' \
      '  case "${1:-}" in' \
      '    instance) shift; command tmux new-session -A -s "$@" ;;' \
      '    resume)   shift; command tmux attach-session -d -t "$@" ;;' \
      '    sessions) shift; command tmux list-sessions "$@" ;;' \
      '    *)        command tmux "$@" ;;' \
      '  esac' \
      '}' \
      > /etc/devbox/tmux-commands.sh \
    && chmod 0644 /etc/devbox/tmux-commands.sh \
    && printf '%s\n' \
      '' \
      '# devbox: plain-English tmux session commands (see the file for why).' \
      '[ -r /etc/devbox/tmux-commands.sh ] && . /etc/devbox/tmux-commands.sh' \
      >> /etc/bash.bashrc

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
      'mkdir -p /home/dev/.cache/huggingface /home/dev/.cache/uv /home/dev/.cache/pycache /home/dev/.ssh' \
      'chmod 700 /home/dev/.ssh' \
      '# Fix ownership only where it is wrong. Never a blanket chown -R: a' \
      '# chown dirties every inode it touches even when nothing changes, and' \
      '# each of those inodes was last written from the previous container' \
      '# cgroup, so the kernel switches its writeback owner one at a time.' \
      '# On a home volume of ~20k cache files that pinned kernel workers at' \
      '# 100% CPU for over ten minutes, with sshd not yet started - the box' \
      '# refused SSH and went unhealthy. -h: never follow a link out of home.' \
      'find /home/dev/.bashrc /home/dev/.cache /home/dev/.ssh \( ! -user dev -o ! -group dev \) -exec chown -h dev:dev {} +' \
      '' \
      '# The agent config dirs belong to dev too. mkdir ran as root above, so' \
      '# without this they come out root-owned and every agent that wants to' \
      '# write its own config fails with EACCES - which looks like a broken' \
      '# agent rather than a permission problem.' \
      'mkdir -p /home/dev/.config /home/dev/.local/bin' \
      'chown dev:dev /home/dev/.config /home/dev/.local /home/dev/.local/bin' \
      'mkdir -p /home/dev/.codex' \
      'chown dev:dev /home/dev/.codex' \
      '' \
      '# The image copy of herdr is the one that must be used, but' \
      '# /home/dev/.local/bin comes FIRST in PATH and the home volume' \
      '# carries a herdr installed there by hand. Left alone, that older' \
      '# binary shadows the image one forever - the image upgrade lands and' \
      '# nothing changes, which is worse than not shipping the binary at all.' \
      '# Point the volume path at the image copy rather than deleting it, so' \
      '# anything referencing the old absolute path keeps working.' \
      'if [ -x /home/dev/.local/bin/herdr ] && [ ! -L /home/dev/.local/bin/herdr ]; then' \
      '  rm -f /home/dev/.local/bin/herdr' \
      '  ln -s /usr/local/bin/herdr /home/dev/.local/bin/herdr' \
      '  chown -h dev:dev /home/dev/.local/bin/herdr' \
      'fi' \
      '' \
      '# Claude Code fullscreen copies a selection the moment a drag ends,' \
      '# unless copyOnSelect is false. Copying belongs to Ctrl+Insert (see' \
      '# /etc/tmux.conf), so seed false - only when the key is absent, so a' \
      '# later choice in /config sticks. Never fatal: a config Claude cannot' \
      '# parse is its problem to report, not a reason to refuse to boot.' \
      'cfg=/home/dev/.claude.json' \
      'if [ ! -e "$cfg" ]; then' \
      '  echo "{\"copyOnSelect\": false}" > "$cfg" && chown dev:dev "$cfg" || true' \
      'elif jq -e "has(\"copyOnSelect\") | not" "$cfg" >/dev/null 2>&1; then' \
      '  jq ".copyOnSelect = false" "$cfg" > "$cfg.devbox" && cat "$cfg.devbox" > "$cfg" || true' \
      '  rm -f "$cfg.devbox"' \
      'fi' \
      '' \
      '# Local home for virtualenvs and per-project tool caches (see the uv' \
      '# wrapper). Deliberately not chowned -R: this tree grows to tens of' \
      '# thousands of files per project, and it is only ever written as dev.' \
      'mkdir -p /home/dev/venvs/.caches' \
      'chown dev:dev /home/dev/venvs /home/dev/venvs/.caches' \
      '' \
      '# Herdr agent skill. The agents use it to spawn sibling agents in their' \
      '# own panes, so a subagent shows up as its own agent instead of hiding' \
      '# inside the parent process.' \
      '#' \
      '# The skill content lives in the IMAGE (/usr/share/devbox/herdr-skill).' \
      '# The agent config dirs live in /home/dev, which is a volume and may be' \
      '# recreated empty, so they are linked from here on every start rather' \
      '# than assumed to exist.' \
      '#' \
      '# Claude Code and OpenCode read ~/.agents/skills and ~/.claude/skills;' \
      '# Codex reads ~/.codex/skills and ignores the universal path, so it' \
      '# needs its own link. Every link is refreshed, never followed into.' \
      'skill=/usr/share/devbox/herdr-skill' \
      'HERDR_BIN=/usr/local/bin/herdr' \
      'HERDR_SOCKET=/home/dev/.config/herdr/herdr.sock' \
      'if [ -r "$skill/SKILL.md" ]; then' \
      '  for d in /home/dev/.agents/skills /home/dev/.claude/skills /home/dev/.codex/skills /home/dev/.config/opencode/skills; do' \
      '    mkdir -p "$d"' \
      '    rm -rf "$d/herdr"' \
      '    ln -s "$skill" "$d/herdr"' \
      '  done' \
      '  chown -R dev:dev /home/dev/.agents /home/dev/.claude/skills /home/dev/.codex/skills /home/dev/.config/opencode/skills' \
      'fi' \
      '' \
      '# Codex filters the environment it passes to spawned commands, so the' \
      '# multiplexer context (HERDR_ENV and friends) never reaches the shell' \
      '# and the herdr skill refuses to act. Restore it. The set block runs' \
      '# after Codex automatic exclusions, so it wins.' \
      '#' \
      '# Appended, never rewritten: config.toml holds the user own settings.' \
      '# Guarded by a marker so a restart does not append it twice - a' \
      '# duplicate TOML table makes Codex reject the whole file and fall back' \
      '# to defaults, which looks exactly like this fix never working.' \
      'cfg=/home/dev/.codex/config.toml' \
      'if [ -n "$HERDR_SOCKET" ] && ! grep -q devbox-herdr-shell-env "$cfg" 2>/dev/null; then' \
      '  mkdir -p /home/dev/.codex' \
      '  {' \
      '    echo ""' \
      '    echo "# devbox-herdr-shell-env: let the herdr skill see the multiplexer."' \
      '    echo "# Added by the devbox entrypoint; remove the marker line to drop it."' \
      '    echo "[shell_environment_policy]"' \
      '    echo "inherit = \"all\""' \
      '    echo ""' \
      '    echo "[shell_environment_policy.set]"' \
      '    echo "HERDR_ENV = \"1\""' \
      '    echo "HERDR_SOCKET_PATH = \"$HERDR_SOCKET\""' \
      '    echo "HERDR_BIN_PATH = \"$HERDR_BIN\""' \
      '  } >> "$cfg"' \
      '  chown dev:dev "$cfg"' \
      'fi' \
      '' \
      '# The crontab. cron keeps it in /var/spool/cron, which is the container' \
      '# layer, so a redeploy silently drops every schedule. The copy that' \
      '# counts lives on the home volume and is loaded on every start; edit' \
      '# that file, then run crontab on it to apply - a crontab -e edit lasts' \
      '# only until the next redeploy. A file cron rejects is reported, never' \
      '# fatal: a typo in a schedule is no reason to refuse to boot.' \
      'tab=/home/dev/.config/devbox/crontab' \
      'if [ -f "$tab" ]; then' \
      '  crontab -u dev "$tab" || echo "WARNING: crontab rejected $tab - no schedule loaded." >&2' \
      'fi' \
      '' \
      '# Start the Herdr server on the first interactive login. It owns the' \
      '# panes, so it must be running before any agent is started, and it' \
      '# dies with the container.' \
      '#' \
      '# The autostart lives in the IMAGE (/etc/profile.d/10-devbox.sh), not' \
      '# here: the entrypoint appends to .bashrc only when its marker is' \
      '# absent, so on a box that has already booted once, a change here can' \
      '# never arrive. The image is the only place a change always lands.' \
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
      '# After the checks, so a box that refuses to start runs nothing. cron' \
      '# daemonizes itself; failing to start it costs the schedule, not the box.' \
      '/usr/sbin/cron || echo "WARNING: cron did not start - schedules will not run." >&2' \
      '' \
      'exec /usr/sbin/sshd -D -e' \
      > /usr/local/bin/devbox-entrypoint \
    && chmod 0755 /usr/local/bin/devbox-entrypoint

EXPOSE 22 8888
ENTRYPOINT ["/usr/local/bin/devbox-entrypoint"]
