# Python starter files

Drop-in root files for a new Python project, matching
`.claude/templates/profiles/python-fastapi.md`.

| File | Copy to | Then |
| --- | --- | --- |
| `pyproject.toml` | project root | Set `[project] name`, and `known-first-party` to your package |
| `.env.example` | project root | Replace the keys with the ones your app reads; commit this, never `.env` |

These are a convenience, not part of the kit's contracts. A project on another stack ignores this
directory entirely — add a sibling (`starters/node/`, `starters/go/`) if you want the same for
another ecosystem.
