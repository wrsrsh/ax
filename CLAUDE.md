# CLAUDE.md

linear is the source of truth for this repo. start every session by reading the linear project **"ax: agent file CLI + benchmark"** (team Hug): its description, the "Plan & decisions" doc, and open issues by milestone. continue from there, not from chat history.

rules, short version (full list is in the project description):
- work one issue at a time: move it to In Progress, commit with a plain message (no `hug-12:` prefix), comment evidence + commit links on the issue when done, move to Done.
- new scope = new issue. bugs in ax = new issue labelled bug.
- gates (label needs-approval) block until the user moves them to Done. no paid model runs without the gate approved, and $2,000 total is a hard cap.
- agent under test is codex (`codex exec`) on gpt-6-astra, medium reasoning. claude code comes later, maybe.
- tool apis change fast: check `--help`/docs, don't trust memory.
- commits and readmes: casual, lowercase, human. no co-authored-by trailers.
- the agents under test never get linear or any mcp servers, and never see this project.

tests: `cd ax && cargo test`, `cd eval && uv run --dev pytest`. keep them green at the end of every issue.
