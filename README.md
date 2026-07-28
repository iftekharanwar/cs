# cs — Claude Sessions

Find and reopen past Claude Code conversations from any directory.

Claude Code's built-in `/resume` only lists sessions started in your current
working directory. Once you have a few hundred conversations spread across
projects, "which folder was that in?" becomes the hard part. `cs` reads the
whole history at once and makes it searchable.

```
cs                    sessions from the last 7 days, grouped by day
cs -i                 fuzzy picker with preview; Enter resumes
cs <query>            search your own prompts
cs -g <query>         search inside full transcripts, replies included
cs -p <name>          everything under a matching project path
cs -v <id|index>      read a session without reopening it
cs -r <id|index>      resume a session
ccps                  sessions running right now
```

## Install

Requires Python 3 (stdlib only) and Claude Code. `fzf` is optional and only
needed for `cs -i`.

```sh
git clone https://github.com/<you>/cs.git
cd cs
./install.sh                  # symlinks into ~/.local/bin
./install.sh /usr/local/bin   # or a directory of your choice
```

The install symlinks rather than copies, so `git pull` updates the commands in
place. To skip it entirely, run `bin/cs` directly or add `bin/` to your PATH.

## What the output means

```
Tuesday 28 July
  1. 4f2a91c0 07:26 ▪▪     21msg  Add pagination to the search endpoint
      ~/code/api-server
  2. b83de117 00:34 ▪▪▪▪   87msg  Debug flaky integration tests  (6 sittings)
      ~/code/web-client
```

- **Titles** are the ones Claude Code generates. Nothing needs renaming.
- **Weight bars** scale with message count, so substantial sessions stand out
  from one-off questions.
- **`(6 sittings)`** means the session was resumed six separate times. It is one
  thread, listed once, dated by its most recent activity.
- The leading number is an index into the list you just ran, for `-v` and `-r`.

## Typical use

Reopening something from last week:

```sh
cs -i          # type to filter, Enter resumes
```

Enter changes into the session's own project directory before resuming, so
relative paths and `CLAUDE.md` resolve against the right tree.

When you want to see the matches before committing to one:

```sh
cs webhook     # numbered list of sessions, with the matching prompts
cs -r 2        # resume the second
```

`-v` and `-r` take either the index from the last list or a session id prefix.

Remembering an answer but not the question:

```sh
cs -g "connection pool"
```

This decodes every transcript, so it is slower than `cs <query>`, which only
looks at prompts you typed.

## Search range

A bare `cs` shows 7 days because it is a browse view. Anything that names a
target — a query, `-p`, `-i`, `-v`, `-r` — searches all of history, since work
you are hunting for is usually older than a week. `-d N` overrides either:

```sh
cs -d 30       # last 30 days
cs -a          # everything
cs -d 3 auth   # scope a search deliberately
```

## Data and compatibility

`cs` only reads, and only from two places:

| Path | Used for |
|---|---|
| `~/.claude/history.jsonl` | prompts, session ids, project paths, timestamps |
| `~/.claude/projects/**/*.jsonl` | transcripts, titles, `-g` search |

Nothing is written, sent anywhere, or cached outside those files. Resuming
shells out to `claude --resume <id>`.

Both formats are internal to Claude Code and can change without notice. If an
update breaks parsing, `cs` reports what it could not read rather than failing
silently. [claude-history](https://github.com/raine/claude-history) is a
maintained alternative if you need something with a stability guarantee.

Subagent transcripts live in nested directories under `projects/`. They are
deliberately excluded, since they are not resumable sessions.

## Known limits

- Tested on macOS with zsh. Nothing is platform-specific, but Linux and
  Windows are unverified.
- `cs -g` scans every transcript and takes a few seconds on large histories.
- Resuming a session that is already open elsewhere gives two processes writing
  the same transcript. Check `ccps` first.
- `cs -r` replaces the current shell process, so exiting the resumed session
  returns you to the project directory rather than where you started.
