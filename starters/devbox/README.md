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
| home | `/home/dev` | Shell config, git identity, `gh` login, VS Code server |

Publish container port `22` on a free host port, and `8888` if you run Jupyter. The only login is
user `dev`, and `dev` has passwordless sudo — so never mount the host's docker socket.

To add a machine later, append its public key to the mounted key file; sshd reads it on the next
connection, no restart needed. Edit the file in place (`>>`, or `cat tmp > file`) rather than
replacing it, or a single-file bind mount keeps pointing at the old copy.
