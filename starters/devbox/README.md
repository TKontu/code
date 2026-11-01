# devbox starter

A `Dockerfile` for a remote development container you work in over SSH, from a terminal or VS Code
Remote-SSH. It ships Python (a venv at `/opt/venv` with torch, Jupyter, ruff, pytest), uv, Poetry,
Node with Claude Code, the Docker CLI, the GitHub CLI, herdr, and Postgres and Redis (installed but
not started) along with the libraries a headless browser needs.

Like the other starters, this is a convenience, not part of the kit's contracts. Keep the compose
or stack file that deploys it in your own infrastructure repo — it will name hosts, ports and
shares, which do not belong here.

## Build

```bash
docker build -t devbox:local starters/devbox
```

| Build arg | Default | Set it when |
| --- | --- | --- |
| `BASE_IMAGE` | `ubuntu:24.04` | You have NVIDIA GPUs — use a CUDA devel image, e.g. `nvidia/cuda:12.8.0-devel-ubuntu24.04` |
| `TORCH_INDEX_URL` | `https://download.pytorch.org/whl/cpu` | Match the CUDA base, e.g. `.../whl/cu128` |
| `DEV_UID` / `DEV_GID` | `1000` | Files under `/work` must be owned by a different host uid/gid |
| `NODE_MAJOR` | `22` | You need another Node major |

From Compose, point `build:` at this directory and pass the same names under `build.args`.

## Run

The entrypoint refuses to start unless both of these hold. Both checks are deliberate: a box nobody
can log into, or one silently working in an empty `/work`, is worse than one that fails to start.

| Mount | Container path | Why |
| --- | --- | --- |
| File with your public key(s), read-only | `/etc/ssh/authorized_keys.d/dev` | Password login is off; this is the only way in |
| Your working directory (volume or share) | `/work` | Must be a mount point |

Recommended, so rebuilds keep state:

| Volume | Container path | Keeps |
| --- | --- | --- |
| host keys | `/etc/ssh/host_keys` | The SSH identity — without it, every rebuild triggers "REMOTE HOST IDENTIFICATION HAS CHANGED" |
| home | `/home/dev` | Shell config, git identity, `gh` login, VS Code server, and every project virtualenv (below) |

Publish container port `22` on a free host port, and `8888` if you run Jupyter. The only login is
user `dev`, and `dev` has passwordless sudo — so never mount the host's docker socket.

To add a machine later, append its public key to the mounted key file; sshd reads it on the next
connection, no restart needed. Edit the file in place (`>>`, or `cat tmp > file`) rather than
replacing it, or a single-file bind mount keeps pointing at the old copy.

### What a redeploy keeps

Only the mounts. Everything else is the container's own layer, and replacing the container
(a new image, or `compose up` after any change) throws it away — even though a plain restart does
not, which is how hand-installed state quietly piles up over weeks. That includes anything you
`apt install`ed or `pip install`ed into `/opt/venv`, all of `/tmp`, and every running process.
Before a redeploy, check for runtime installs with:

```bash
grep -h -E '^(Start-Date|Commandline)' /var/log/apt/history.log
```

If you keep needing something, it belongs in the image.

### Scheduled jobs

cron runs on every start, but its own copy of your crontab (`/var/spool/cron`) is in the container
layer. The copy that survives is `~/.config/devbox/crontab` on the home volume: the entrypoint loads
it on every start. So edit that file, not `crontab -e`, and apply it straight away with:

```bash
crontab ~/.config/devbox/crontab
```

A `crontab -e` edit works until the next redeploy, then silently reverts to the file. If cron
rejects the file, the container still starts; the reason is in the container log
(`WARNING: crontab rejected ...`).

### Postgres, Redis and headless browsers

The image ships Postgres, Redis and the system libraries a headless Chromium needs (Playwright's
list for Ubuntu 24.04, plus Xvfb), so integration tests can run against real services.

They are **installed, not started** — nothing holds 5432 or 6379 unless you ask, so a project that
brings its own via compose does not collide with them. Start them when you need them:

```bash
sudo service postgresql start
sudo service redis-server start
```

Their data lives in the container layer and does not survive a redeploy. Treat them as scratch
databases for tests; anything worth keeping belongs in a project's own service with a volume.
Browser *binaries* stay per-project (`playwright install chromium`), so their version follows the
project's lockfile rather than the image.

## Virtualenvs never live under `/work`

If `/work` is a network share — the common case — a virtualenv must not sit inside the project
directory, for two independent reasons:

- **Correctness.** The share is visible to other machines running other interpreters. One `.venv`
  cannot be valid for a 3.12 container and a 3.14 host at once, and the failure is silent until
  something reads `pyvenv.cfg` and believes it.
- **Cost.** A virtualenv is tens of thousands of files. Measured on an SMB share against local
  disk on the same box: reads ~33x slower, writes ~40x, stats ~17x. Since tooling walks the
  environment far more than it walks your source, this is usually *most* of a test or type-check
  run.

So `/usr/local/bin/uv` is a small wrapper. It finds the project root the way uv does — nearest
ancestor holding `pyproject.toml` — and if that root is under `/work` it points the environment and
the per-project tool caches at local disk instead:

| | Location |
| --- | --- |
| Virtualenv | `/home/dev/venvs/<project>-<hash>` |
| mypy / ruff / pytest caches | `/home/dev/venvs/.caches/<project>-<hash>/` |
| uv wheel cache, `__pycache__` | `/home/dev/.cache/` (shared across projects; safe to be) |

The hash is of the full project path, so `/work/a/api` and `/work/b/api` get separate slots. A
project already on local disk is left alone, and an explicit `UV_PROJECT_ENVIRONMENT` always wins.
Nothing in any project file changes, and nothing here is required for the kit's contracts — a
project that has never seen this box behaves identically.

It is a wrapper rather than an entry in `/etc/environment` because the value has to be per-project,
and because agents commonly run `ssh box '<cmd>'`, which is non-interactive and non-login and so
sources no shell files at all. Consequences worth knowing:

- `uv sync` in a project is what creates the environment; `.venv/` under `/work` is then dead
  weight and should be deleted.
- Mount `/home/dev` as a volume or every environment is rebuilt on each redeploy.
- Tools invoked directly rather than through `uv run` (a bare `mypy`) miss the cache redirection.
  Prefer `uv run`, which is what the Python profile's Project Commands table uses.

## Git does not track exec bits under `/work`

The same share, the other half of the problem. CIFS cannot store a per-file executable bit — it
synthesizes one mode for every file from the mount options. A file is therefore executable to a
host mounting with `file_mode=0755` and not to this container at `0664`, and git reports the whole
tree as modified on every status.

`/etc/gitconfig` carries a conditional include so repos under `/work` get `core.fileMode = false`:

```gitconfig
[includeIf "gitdir:/work/"]
	path = /etc/gitconfig-share
```

Scoped rather than global on purpose. A repo on local disk has real exec bits and keeps tracking
them, so `chmod +x` still gets recorded there. Nothing is lost on the share either — git stores the
bit in the index regardless, so CI on a normal filesystem checks out correctly; only the on-disk
bit is ignored.

It is system config rather than `/home/dev/.gitconfig` because the home volume may start empty, and
it is *appended* with `git config` rather than written, because git-lfs already owns that file.

**This include is a backstop, not the main mechanism.** Git probes the filesystem at `git init`
and writes the answer into the repo's *own* `.git/config`, and local config outranks system config.
On a share the probe gets it right on its own, so a repo created there needs nothing. The include
only decides repos where that key is absent.

The repos that actually break are the ones created somewhere else and later moved or copied onto
the share: they carry `fileMode = true` from a filesystem where it was correct, and that local
value wins over everything here. Nothing in the image can fix those — they need the value corrected
per repo:

```bash
# from the root of the share, fix every repo that arrived with the wrong answer
for g in */.git; do
  d=${g%/.git}
  [ "$(git -C "$d" config --local --get core.fileMode)" = "true" ] \
    && git -C "$d" config --local core.fileMode false && echo "fixed: $d"
done
```

Worth knowing while you are there: `git clone` of a *local path* onto a CIFS share fails with
`fatal: hardlink different from source`, because it hardlinks objects by default. Use
`git clone --no-hardlinks`, or clone over the network.

## Sessions that outlive your laptop

An SSH session that dies takes the shell's children with it — a long build, a test run, an agent
mid-task. The sshd drop-in buys some tolerance (`ClientAliveInterval 30` × `ClientAliveCountMax
240` = two hours), but that only helps while the TCP connection itself survives. A laptop
shutdown, an IP change or a NAT timeout tears down the socket, and the grace period never applies.

So use tmux, which is installed and preconfigured at `/etc/tmux.conf`. The config adds four
plain-English commands so routine use needs no flags at all:

| command | what it does |
| --- | --- |
| `tmux instance <name>` | start a named session, or step back into it if it already exists |
| `tmux resume <name>` | reattach to a session, evicting any stale client |
| `tmux sessions` | list what is still running |
| `tmux detach` | leave the session running and return to the shell (built in) |

```bash
ssh <box>
tmux instance iknos1
# ... laptop dies ...
ssh <box>
tmux resume iknos1
```

They are **additions** — every standard form such as `tmux new -s name` or `tmux attach -t name`
still behaves exactly as documented.

They are provided twice, on purpose, because neither mechanism covers everything:

- **A shell function** in `/etc/devbox/tmux-commands.sh`, sourced from `/etc/profile.d` (login
  shells) and `/etc/bash.bashrc` (interactive non-login shells, such as editor terminals). It
  rewrites the word before tmux is invoked.
- **tmux `command-alias` entries** in `/etc/tmux.conf`, which also cover non-interactive use such
  as `ssh <box> 'tmux sessions'`, where no shell config is read at all.

The shell function is what makes the *first* command of a session work. `command-alias` is a
**server** option, read when the tmux server starts, so with no server running the client cannot
resolve an unknown command name — it tries to connect to a server that is not there and fails with
`error connecting to /tmp/tmux-1000/default`. `tmux start-server` does not help either: with no
sessions it exits immediately. Rewriting in the shell sidesteps this entirely, because tmux then
receives `new-session`, which it knows how to start a server for.

Note neither mechanism lives in `/etc/devbox/bashrc.append`. The entrypoint appends that file only
when its marker is absent from `/home/dev/.bashrc`, so on a box that has already booted once,
changes there can never arrive.

The flags they bake in are the ones easy to forget and annoying to omit: `-s` makes the argument a
session *name* (without it `new-session` treats it as a command to run), `-A` re-enters an existing
session instead of erroring, and `-d` on attach evicts the dead client a dropped connection leaves
registered — otherwise tmux sizes the window to that ghost and your terminal arrives squashed.

`/etc/tmux.conf` rather than a seeded `~/.tmux.conf`, because the home volume may start empty and
tmux reads the system file directly. Your own `~/.tmux.conf` still overrides it. The settings match
`cheatsheets/tmux-cheatsheet.md`; three of them are load-bearing for full-screen applications —
`allow-passthrough` (or escape sequences never reach the outer terminal and notifications vanish),
`extended-keys` (or Shift+Enter never arrives, so multi-line input breaks *only* under tmux), and
`escape-time 0` (the 500 ms default reads as laggy, garbled keys).

### Claude Code under tmux: scrolling, copying, Shift+Enter

The image sets `CLAUDE_CODE_NO_FLICKER=1` (in `/etc/environment` and `/etc/profile.d`), which
selects Claude Code's **fullscreen renderer**. The classic renderer redraws a streaming reply in
place, but rows that have already scrolled off the top cannot be redrawn. When a long table re-lays
out its columns mid-stream, scrollback keeps every stale width, and scrolling up shows the same
rows repeated at different widths. That is not a tmux bug and not a resize: it reproduces
identically in tmux 3.4 and 3.7, and with tmux hidden from Claude Code entirely. Fullscreen
re-renders the whole transcript on the alternate screen, so scrolling always shows the final
layout. To opt out, put `unset CLAUDE_CODE_NO_FLICKER` in your `~/.bashrc`.

Copying is **on demand, never on contact**. A mouse drag only selects; `Ctrl+Insert` copies — the
CUA copy key, and what a desktop-wide Super+C sends to terminals on some Linux desktops. It works
in a plain shell (tmux copy mode) and in Claude Code, which keeps its own selection in fullscreen:
tmux translates the key into Claude Code's own copy key, `Ctrl+Shift+C`, which does nothing when
nothing is selected. The copy travels as OSC 52, so it lands on the clipboard of the machine you
are sitting at. On boot the entrypoint seeds `"copyOnSelect": false` into `~/.claude.json` — only
when the key is absent, so a later choice in `/config` sticks.

What your **local terminal** must do — this half cannot be fixed on the server:

| Terminal | Shift+Enter | Ctrl+Insert |
| --- | --- | --- |
| Ghostty | `keybind = shift+enter=csi:13;2u` | prefix the copy bind with `performable:` (`keybind = performable:control+insert=copy_to_clipboard`) so it passes through when Ghostty has no selection of its own |
| Alacritty | `{ key = "Return", mods = "Shift", chars = "\u001B[13;2u" }` | remove any `Ctrl+Insert` → `Copy` binding; Alacritty consumes the key even with nothing selected |
| VS Code | add to `keybindings.json`: `{ "key": "shift+enter", "command": "workbench.action.terminal.sendSequence", "args": { "text": "\u001b[13;2u" }, "when": "terminalFocus" }` | the default copy binding applies only `when terminalTextSelected`, so the key already passes through |

Without the Shift+Enter line, the terminal sends a plain `Enter` and nothing downstream can tell
the two apart. To bypass tmux and Claude Code and select with the terminal itself, hold **Shift**
while dragging.

Two limits worth knowing:

- **tmux survives your laptop, not a redeploy.** The server is a container process, so replacing
  the container kills every session. Anything that must outlive a redeploy belongs in git.
- **Claude Code has no detach or daemon mode** — its own docs say to start it inside tmux or
  screen. What it does have is on-disk session transcripts under `~/.claude/projects/`, so with
  `/home/dev` mounted as a volume a conversation is resumable with `claude --resume` even after a
  redeploy. A turn interrupted mid-tool-call is marked as cut off, and on resume Claude is told to
  check whether the call took effect before retrying it.

## What none of this fixes

CIFS delivers no inotify events, so file watchers and `--reload` will not see edits made from
another machine. If you need those, the project's working copy has to be on local disk too, with
git as the sync boundary rather than the share.
