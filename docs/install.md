# Installing SPIDER

SPIDER follows the open [Agent Skills specification](https://agentskills.io/specification). The easiest cross-client installation uses the open `skills` CLI:

```bash
npx skills add baytcho/spider-dead-code-skill
```

The installer detects supported coding agents and asks where to install the skill. The manual options below install the repository as a folder named `spider`; `SKILL.md` must sit directly inside that folder.

## Codex

Codex discovers personal skills under `~/.agents/skills` and project skills under `.agents/skills`.

Personal installation:

```bash
git clone https://github.com/baytcho/spider-dead-code-skill.git ~/.agents/skills/spider
npm --prefix ~/.agents/skills/spider ci
```

Invoke it explicitly with a prompt such as:

```text
Use $spider to audit this repository for dead-code candidates.
```

See the official [OpenAI skill documentation](https://developers.openai.com/codex/build-skills) for discovery rules and additional installation options.

## Claude Code

Claude Code discovers personal skills under `~/.claude/skills` and project skills under `.claude/skills`.

```bash
git clone https://github.com/baytcho/spider-dead-code-skill.git ~/.claude/skills/spider
npm --prefix ~/.claude/skills/spider ci
```

Invoke the skill with `/spider`. See the official [Claude Code skill documentation](https://code.claude.com/docs/en/skills) for discovery and invocation details.

## Skill-file import

Download `spider.skill` from the [latest GitHub release](https://github.com/baytcho/spider-dead-code-skill/releases/latest). A `.skill` file is a ZIP archive with one top-level `spider/` directory; do not unpack it when the client offers direct skill import.

## Prerequisites

- Python 3 is required.
- Node.js is required for TypeScript and JavaScript projects. `npm ci` installs the parser pinned by this repository's lockfile inside the skill folder.
- Java 17+ and [Joern](https://github.com/joernio/joern) are optional. They accelerate call-graph construction; the load and name graphs do not require them.

## Update

If you installed SPIDER with the `skills` CLI:

```bash
npx skills update
```

For a manual Git clone, run this from the installed skill folder:

```bash
git pull --ff-only
npm ci
```

If the host does not detect a newly created top-level skill folder, restart it after installation.

## Remove

Delete only the installed `spider` skill folder from the relevant skills directory. This does not touch any project that SPIDER analysed or any separate analysis directory you chose for a run.
