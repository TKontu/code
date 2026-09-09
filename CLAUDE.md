# CLAUDE.md

This repository is a **Claude Code scaffold kit** — a portable set of commands, skills, and
templates for driving a project with Claude Code, including a multi-agent "round" workflow. It is
copied into other projects; it is not itself an application.

Read `.claude/README.md` first. It defines the two contracts everything here is written against.

## Project Commands

The table every command in `.claude/commands/` resolves its tooling from. This repo is markdown, so
most keys are `n/a` — that is the correct value, and commands will skip those steps and say so.

<!-- claude:commands -->
| Key       | Command |
| --------- | ------- |
| install   | n/a |
| test      | n/a |
| test-one  | n/a |
| lint      | n/a |
| lint-fix  | n/a |
| format    | n/a |
| typecheck | n/a |
| run       | n/a |
| build     | n/a |
<!-- /claude:commands -->

## Layout

```
.claude/
├── README.md          the contracts + install instructions — start here
├── commands/          slash commands: everyday tier + round-workflow tier
├── skills/            debug, tdd, verify + gitnexus-* knowledge-graph skills
├── templates/         CLAUDE.md, TODO, backlog, round, and handoff templates
│   └── profiles/      stack-specific add-ons (python-fastapi, node-typescript, go)
└── settings.json      stack-neutral permissions; profiles carry the rest
starters/python/       drop-in pyproject.toml + .env.example for a new Python project
cheatsheets/           git, docker, pytest, venv, tmux
CLAUDE_CODE_GUIDE.md   working practices for Claude Code itself
```

## Rules for editing this kit

Everything here ships to unknown projects. Three rules follow from that:

1. **Nothing names a specific project.** No repository, service, internal identifier, ticket
   prefix, hostname, or port. If an example needs a domain, invent a neutral one (`User`, `Order`).
   Reviewing a change here means asking: would this still make sense in someone else's repo?

2. **Commands resolve, they do not assume.** No command hardcodes `pytest`, `npm test`, `ruff`, or
   any other tool. It reads the key it needs from the Project Commands table, and skips — visibly —
   when the key is absent or `n/a`. Stack specifics belong in a profile.

3. **No required helper scripts.** The round workflow runs on plain markdown files. A project may
   add validation scripts and declare them under **Round tooling** in its `docs/conventions.md`;
   commands then use them. Nothing may *depend* on them existing.

When adding a stack, copy the closest profile in `.claude/templates/profiles/` and keep its section
headings — `profiles/README.md` explains the structure.

## Adding a command

Put it in `.claude/commands/<name>.md`. Give it a one-line title, state what it does and what it
refuses to do, and name the contract keys it reads. Then add it to the tier table in
`.claude/README.md` — a command missing from that table is invisible.
