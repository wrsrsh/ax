use ax::output::Report;
use ax::{AxError, Ctx};
use clap::{Parser, Subcommand};
use std::io::{Read, Write};

/// one cli for the file work coding agents do all day: orient, find, search, read, edit.
#[derive(Parser)]
#[command(name = "ax", version, about)]
struct Cli {
    /// machine-readable output
    #[arg(long, global = true)]
    json: bool,
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// one-screen overview of a repo, or of one dir in it
    Map { dir: Option<String> },
    /// find files by name (smart-case substring) or rg-style glob
    Find {
        pattern: Option<String>,
        /// dirs to search under (same as --in)
        paths: Vec<String>,
        /// only these extensions (comma-separated or repeated)
        #[arg(long)]
        ext: Vec<String>,
        /// only under this dir (repeatable)
        #[arg(long = "in")]
        within: Vec<String>,
        /// modified within this long (30m, 1h, 2d)
        #[arg(long)]
        changed: Option<String>,
        /// include hidden and gitignored files
        #[arg(long)]
        all: bool,
    },
    /// search file contents (rg-compatible flags)
    Grep {
        pattern: String,
        /// files or dirs to search, like rg's trailing paths (same as --in)
        paths: Vec<String>,
        /// treat the pattern as a literal string
        #[arg(short = 'F', long)]
        fixed_strings: bool,
        /// whole words only
        #[arg(short = 'w', long)]
        word_regexp: bool,
        /// case-insensitive
        #[arg(short = 'i', long)]
        ignore_case: bool,
        /// case-insensitive unless the pattern has uppercase
        #[arg(short = 'S', long)]
        smart_case: bool,
        /// only files of this rg type (ts, py, rust, go, …; repeatable)
        #[arg(short = 't', long = "type")]
        types: Vec<String>,
        /// include/exclude files by glob, rg-style (repeatable, `!` excludes)
        #[arg(short = 'g', long = "glob")]
        globs: Vec<String>,
        /// only under this dir (repeatable)
        #[arg(long = "in")]
        within: Vec<String>,
        /// lines of context around each hit
        #[arg(short = 'C', long, default_value_t = 0)]
        context: usize,
        /// list matching files only
        #[arg(short = 'l', long)]
        files_with_matches: bool,
        /// count hits per file
        #[arg(short = 'c', long)]
        count: bool,
        /// stop after this many matching lines per file, like rg -m
        #[arg(short = 'm', long)]
        max_count: Option<u64>,
        /// accepted for rg muscle memory; hits always carry line numbers
        #[arg(short = 'n', long = "line-number", hide = true)]
        line_number: bool,
        /// include hidden and gitignored files
        #[arg(long)]
        all: bool,
    },
    /// symbol outline of files or dirs
    Outline {
        #[arg(required = true)]
        paths: Vec<String>,
    },
    /// jump to a symbol definition
    Def {
        sym: String,
        /// only under this dir (repeatable)
        #[arg(long = "in")]
        within: Vec<String>,
    },
    /// find references to a symbol
    Refs {
        sym: String,
        /// skip matches inside comments and strings
        #[arg(long)]
        code_only: bool,
        /// only under this dir (repeatable)
        #[arg(long = "in")]
        within: Vec<String>,
    },
    /// read files or line ranges (path:10-20) with LINE:HASH anchors
    Read {
        paths: Vec<String>,
        /// read just this symbol (Class.method or name)
        #[arg(long)]
        sym: Option<String>,
        /// whole file, no outline/window for long files
        #[arg(long)]
        full: bool,
    },
    /// apply anchored edit ops from stdin
    Edit {
        /// one file; the ops come on stdin
        #[arg(required = true)]
        paths: Vec<String>,
        /// show the result, write nothing
        #[arg(long)]
        dry_run: bool,
    },
    /// write a whole file from stdin
    Write {
        path: String,
        /// only if the file still has this hash (from `ax read`)
        #[arg(long = "if")]
        if_hash: Option<String>,
        /// overwrite an existing file without --if
        #[arg(long)]
        force: bool,
        /// show the result, write nothing
        #[arg(long)]
        dry_run: bool,
    },
    /// apply a multi-file patch from stdin
    Patch {
        /// check the patch applies, write nothing
        #[arg(long)]
        dry_run: bool,
    },
    /// git status + stat + capped hunks
    Diff {
        /// every hunk, no cap
        #[arg(long)]
        full: bool,
        /// status and per-file counts only, no hunks
        #[arg(long, conflicts_with = "full")]
        stat: bool,
        /// limit to these paths
        paths: Vec<String>,
    },
    /// print the usage note for CLAUDE.md / AGENTS.md
    AgentHelp {
        /// list the AX_* env knobs instead
        #[arg(long)]
        env: bool,
    },
}

fn stdin() -> ax::Result<Vec<u8>> {
    let mut input = Vec::new();
    std::io::stdin().read_to_end(&mut input)?;
    Ok(input)
}

fn run(ctx: &Ctx, cmd: Cmd) -> ax::Result<Report> {
    match cmd {
        Cmd::Map { dir } => ax::map::run(ctx, dir.as_deref()),
        Cmd::Find {
            pattern,
            paths,
            ext,
            within,
            changed,
            all,
        } => ax::find::run(
            ctx,
            &ax::find::FindArgs {
                pattern,
                ext,
                within: within.into_iter().chain(paths).collect(),
                changed,
                all,
            },
        ),
        Cmd::Grep {
            pattern,
            paths,
            fixed_strings,
            word_regexp,
            ignore_case,
            smart_case,
            types,
            globs,
            within,
            context,
            files_with_matches,
            count,
            max_count,
            line_number: _,
            all,
        } => ax::grep::run(
            ctx,
            &ax::grep::GrepArgs {
                pattern,
                fixed: fixed_strings,
                word: word_regexp,
                ignore_case,
                smart_case,
                types,
                globs,
                within: within.into_iter().chain(paths).collect(),
                context,
                files_only: files_with_matches,
                count,
                max_count,
                all,
            },
        ),
        Cmd::Outline { paths } => ax::symbols::outline(ctx, &paths),
        Cmd::Def { sym, within } => ax::symbols::def(ctx, &sym, &within),
        Cmd::Refs {
            sym,
            code_only,
            within,
        } => ax::symbols::refs(ctx, &sym, code_only, &within),
        Cmd::Read { paths, sym, full } => ax::read::run(ctx, &paths, sym.as_deref(), full),
        Cmd::Edit { paths, dry_run } => match paths.as_slice() {
            [path] => ax::edit::run(ctx, path, &stdin()?, dry_run),
            more => Err(ax::AxError(format!(
                "ax edit takes one file ({} given). run it once per file, each with its own ops on stdin.",
                more.len()
            ))),
        },
        Cmd::Write {
            path,
            if_hash,
            force,
            dry_run,
        } => {
            let opts = ax::write::WriteOpts {
                if_hash: if_hash.as_deref(),
                force,
                dry_run,
            };
            ax::write::run(ctx, &path, &opts, &stdin()?)
        }
        Cmd::Patch { dry_run } => ax::patch::run(ctx, &stdin()?, dry_run),
        Cmd::Diff { full, stat, paths } => ax::diff::run(ctx, full, stat, &paths),
        Cmd::AgentHelp { env } => Ok(ax::help::run(env)),
    }
}

fn log_call(started: std::time::Instant, exit: i32, out_bytes: usize, data: &serde_json::Value) {
    let Ok(path) = std::env::var("AX_LOG") else {
        return;
    };
    let args: Vec<String> = std::env::args().skip(1).collect();
    let knobs: Vec<String> = std::env::vars()
        .filter(|(k, _)| k.starts_with("AX_") && k != "AX_LOG")
        .map(|(k, v)| format!("{k}={v}"))
        .collect();
    let line = serde_json::json!({
        "ts": std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0),
        "cmd": args.iter().find(|a| !a.starts_with('-')).cloned().unwrap_or_default(),
        "args": args,
        "exit": exit,
        "out_bytes": out_bytes,
        "ms": started.elapsed().as_secs_f64() * 1000.0,
        "outcome": data.get("outcome").cloned().unwrap_or(serde_json::Value::Null),
        "knobs": knobs,
    });
    // one write per line: parallel ax calls append to the same file, and
    // O_APPEND only keeps whole writes from interleaving
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    {
        let _ = f.write_all(format!("{line}\n").as_bytes());
    }
}

fn main() {
    let started = std::time::Instant::now();
    let cli = Cli::parse();
    let result = Ctx::from_env()
        .map_err(AxError::from)
        .and_then(|ctx| run(&ctx, cli.cmd));
    let (out, exit, data, to_stderr) = match result {
        Ok(report) => {
            let out = if cli.json {
                report.render_json()
            } else {
                report.render_text(ax::config::Config::from_env().byte_cap())
            };
            (out, i32::from(report.failed), report.data, false)
        }
        Err(e) => {
            let out = if cli.json {
                format!("{}\n", serde_json::json!({ "error": e.0 }))
            } else {
                format!("ax: {e}\n")
            };
            (out, 1, serde_json::json!({ "outcome": "error" }), !cli.json)
        }
    };
    let _ = if to_stderr {
        std::io::stderr().lock().write_all(out.as_bytes())
    } else {
        std::io::stdout().lock().write_all(out.as_bytes())
    };
    log_call(started, exit, out.len(), &data);
    std::process::exit(exit);
}
