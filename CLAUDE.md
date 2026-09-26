# CLAUDE.md

linear is the source of truth for this repo. start every session by reading the linear project **"ax: agent file CLI + benchmark"** (team Hug): its description, the "Plan & decisions" doc, and open issues by milestone. continue from there, not from chat history.

rules, short version (full list is in the project description):
- work one issue at a time: move it to In Progress, put its id in every commit (lowercase, e.g. `hug-12: ...`), comment evidence when done, move to Done.
- new scope = new issue. bugs in ax = new issue labelled bug.
- gates (label needs-approval) block until the user moves them to Done. no paid/subscription model runs without the gate approved.
- tool apis change fast: check `--help`/docs, don't trust memory.
- commits and readmes: casual, lowercase, human.
- the agents under test never get linear or any mcp servers, and never see this project.

tests: `cd ax && cargo test`, `cd eval && uv run --dev pytest`. keep them green at the end of every issue.
