# Transcript Schema

Trail is `md first`. The canonical interface is the markdown transcript file under `~/.trail/transcripts/`, not a JSON API.

## Directory Contract

- Root: `~/.trail/transcripts/`
- Day bucket: `YYYY-MM-DD/` using the session `started_at` date
- Filename: `HHMMSS--<tool>--<session_id>.md`
- One session always maps to one markdown file, even if it crosses midnight

## Frontmatter Contract

Every transcript starts with YAML frontmatter. These fields are the stable schema for agents:

- `kind`: always `trail_session`
- `schema_version`: currently `trail_session/v1`
- `session_id`: stable UUID for the session
- `tool`: current values include `claude` and `codex`
- `status`: `active` or `completed`
- `date`: session start date in `YYYY-MM-DD`
- `week`: ISO week in `YYYY-Www`
- `started_at`: session start timestamp in ISO 8601 with timezone
- `ended_at`: session end timestamp in ISO 8601 with timezone, or empty while active
- `last_synced_at`: last transcript write timestamp in ISO 8601 with timezone
- `duration`: human-readable duration, best-effort
- `exit_code`: process exit code when completed, or empty while active
- `turn_count`: number of parsed turns currently written
- `repo`: git repo root when available, else empty
- `cwd`: session working directory
- `branch`: git branch when available, else empty
- `raw_log_path`: path to the raw jsonl event log
- `preview`: first non-empty turn preview

## Body Contract

After frontmatter, the transcript body contains:

- `# Trail Session <session_id>`
- `## Transcript`
- Repeating turn sections with `### <Speaker>` headings
- Each turn includes `Started` and `Ended` timestamps, followed by the turn text

## Agent Guidance

Agents should:

- discover sessions by walking `~/.trail/transcripts/YYYY-MM-DD/*.md`
- use frontmatter fields for filtering and time slicing
- read the `## Transcript` section for content
- treat `raw_log_path` as an optional evidence layer, not the primary interface

Agents should not depend on:

- CLI text output formatting
- sqlite internal schema
- transient parser confidence or debug fields
