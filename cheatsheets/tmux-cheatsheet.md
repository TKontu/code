# tmux Cheat Sheet

> **The prefix:** almost every in-tmux command is `Ctrl-b` *released*, then a key.
> Written below as `C-b <key>`. It is two presses, not a chord.

---

## Sessions — the persistent containers for your work

The `starters/devbox` image adds four flag-free commands via tmux's own `command-alias`, so the
everyday cases need nothing memorised. Elsewhere, use the standard forms in the next table.

| Command | Does |
|---|---|
| `tmux instance work` | Start a session named `work`, or step back into it if it exists |
| `tmux resume work` | Reattach to `work`, evicting any stale client |
| `tmux sessions` | List running sessions |
| `tmux detach` | Leave the session running and return to the shell (built in) |

To add them anywhere else, put this in your `~/.tmux.conf` — indices start at 100 because tmux
fills 0–5 with its own aliases:

```tmux
set -s command-alias[100] 'instance=new-session -A -s'
set -s command-alias[101] 'resume=attach -d -t'
set -s command-alias[102] 'sessions=list-sessions'
```

They are additions, not overrides: everything below still works. Note you cannot usefully override
a built-in such as `new`, because the alias body is prepended — `new=new-session -A -s` turns
`tmux new -d foo` into `new-session -A -s -d foo`, where `-s` swallows the `-d`.

### The standard forms

| Command (from shell) | Does |
|---|---|
| `tmux new -s work` | Start a new session named `work` |
| `tmux` | Start an unnamed session |
| `tmux ls` | List running sessions |
| `tmux attach -t work` | Reattach to `work` |
| `tmux a` | Attach to most recent session |
| `tmux attach -d -t work` | Attach and **detach other clients** (fixes resize/squish) |
| `tmux kill-session -t work` | Destroy `work` |
| `tmux kill-server` | Destroy **all** sessions (full reset) |

**Inside tmux:**

| Key | Does |
|---|---|
| `C-b d` | **Detach** — leave everything running. Your main move. |
| `C-b s` | Visual list of sessions, switch between them |
| `C-b $` | Rename current session |

---

## Windows — like tabs

| Key | Does |
|---|---|
| `C-b c` | Create new window |
| `C-b n` / `C-b p` | Next / previous window |
| `C-b 0`–`9` | Jump to window by number |
| `C-b w` | Visual list of windows |
| `C-b ,` | Rename current window |
| `C-b &` | Close current window (confirm) |

---

## Panes — split a window into tiles

| Key | Does |
|---|---|
| `C-b %` | Split **vertically** (left / right) |
| `C-b "` | Split **horizontally** (top / bottom) |
| `C-b ←↑↓→` | Move to pane in that direction |
| `C-b o` | Cycle to next pane |
| `C-b z` | **Zoom** pane to fullscreen (toggle) |
| `C-b x` | Close current pane (confirm) |
| `C-b Space` | Cycle pane layouts |
| `C-b !` | Break current pane into its own window |

---

## Copy / scroll mode

| Key | Does |
|---|---|
| `C-b [` | Enter scroll/copy mode |
| `↑ ↓ PgUp PgDn` | Scroll around |
| `Space` then `Enter` | Start selection, then copy |
| `C-b ]` | Paste tmux's copy buffer |
| `q` | Quit copy mode |
| `/` then text | Search forward (`n`/`N` to repeat) |

---

## ⚠️ Running Claude Code (or any TUI) inside tmux

Two things were fighting each other; here's how to get **both** scroll and paste:

- **Scrolling needs `mouse on`.** Claude Code draws its conversation on the alternate
  screen, so the only way the wheel scrolls *Claude's* history is for tmux to forward
  the wheel into the app — which it only does with `set -g mouse on`. With mouse off,
  the wheel goes nowhere useful inside a full-screen TUI.
- **Paste is fixed by the clipboard/passthrough lines**, not by mouse mode. With
  `set-clipboard on`, `allow-passthrough on`, and `escape-time 0`, bracketed paste
  passes through cleanly even with the mouse on.
- **Select/copy terminal text by hand:** hold **Shift** while dragging (Shift+wheel for
  native terminal scrollback). Shift makes most terminals (iTerm2, GNOME Terminal,
  Windows Terminal, Kitty, Alacritty) bypass tmux for a native selection.
- **Changed the config but a session still misbehaves?** Old sessions keep old settings —
  run `tmux kill-server` and start fresh so everything reloads.

---

## Recommended `~/.tmux.conf` — TUI-friendly

The `starters/devbox` image already ships these settings at `/etc/tmux.conf`, so there is nothing
to do on that box. Elsewhere, put them in `~/.tmux.conf` — which also overrides the system file if
you want to change one.

```tmux
# Mouse ON so the scroll wheel is forwarded INTO Claude Code (it scrolls its own view).
# Paste stays clean thanks to the clipboard/passthrough/escape-time lines below.
# To hand-select terminal text, hold SHIFT while dragging (bypasses tmux).
set -g mouse on

# True color + correct terminal type so TUIs render correctly
set -g default-terminal "tmux-256color"
set -ga terminal-overrides ",*256col*:Tc"

# Pass clipboard (OSC 52) and other escape sequences straight to the terminal
set -g set-clipboard on
set -g allow-passthrough on

# No Escape delay — fixes laggy / garbled keys in TUIs
set -sg escape-time 0

# Extended keys, so Shift+Enter reaches the application. Without these,
# multi-line input breaks ONLY inside tmux, which makes it look like the
# application's bug rather than the multiplexer's.
set -s extended-keys on
set -as terminal-features 'tmux-256color:extkeys'
bind-key -n S-Enter send-keys Escape "[13;2u"

# Bigger scrollback for when you DO use copy mode (C-b [)
set -g history-limit 50000

# Start numbering at 1
set -g base-index 1
setw -g pane-base-index 1

# Intuitive splits
bind | split-window -h
bind - split-window -v

# Reload config: C-b r
bind r source-file ~/.tmux.conf \; display "Config reloaded"
```

After creating the file, `tmux kill-server` once, then start a new session so it picks up the settings.

---

## The everyday workflow

```bash
ssh devbox                 # or VS Code integrated terminal on the remote
tmux new -s work           # start (or `tmux a` to resume)

#   ...run your long job: training, uvicorn, downloads, claude...

# C-b d                    # detach — safe to disconnect / sleep / close laptop

# later, from any new connection:
tmux a                     # everything still running, exactly as left
```

**Rule of thumb:** launch anything you'd be sad to lose *inside* tmux first.
Keepalives reduce dropped connections; tmux makes a dropped connection harmless.
