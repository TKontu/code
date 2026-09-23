# devbox starter

A `Dockerfile` for a remote development container you work in over SSH, from a terminal or VS Code
Remote-SSH. It ships Python (a venv at `/opt/venv` with torch, Jupyter, ruff, pytest), uv, Poetry,
Node with Claude Code, the Docker CLI, and the GitHub CLI.

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

## What none of this fixes

CIFS delivers no inotify events, so file watchers and `--reload` will not see edits made from
another machine. If you need those, the project's working copy has to be on local disk too, with
git as the sync boundary rather than the share.
