use ax::output::Report;
use ax::{AxError, Ctx};
use clap::{Parser, Subcommand};

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
    /// one-screen overview of a repo
    Map { dir: Option<String> },
    /// find files by name (smart-case substring) or rg-style glob
    Find {
        pattern: Option<String>,
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
        /// include hidden and gitignored files
        #[arg(long)]
        all: bool,
    },
    /// symbol outline of a file or dir
    Outline { path: String },
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
    /// read files or line ranges with LINE:HASH anchors
    Read { paths: Vec<String> },
    /// apply anchored edit ops from stdin
    Edit { path: String },
    /// write a whole file from stdin
    Write { path: String },
    /// apply a multi-file patch from stdin
    Patch,
    /// git status + stat + capped hunks
    Diff,
    /// print the usage note for CLAUDE.md / AGENTS.md
    AgentHelp,
}

fn run(ctx: &Ctx, cmd: Cmd) -> ax::Result<Report> {
    let name = match cmd {
        Cmd::Map { dir } => return ax::map::run(ctx, dir.as_deref()),
        Cmd::Find {
            pattern,
            ext,
            within,
            changed,
            all,
        } => {
            let args = ax::find::FindArgs {
                pattern,
                ext,
                within,
                changed,
                all,
            };
            return ax::find::run(ctx, &args);
        }
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
            all,
        } => {
            let args = ax::grep::GrepArgs {
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
                all,
            };
            return ax::grep::run(ctx, &args);
        }
        Cmd::Outline { path } => return ax::symbols::outline(ctx, &path),
        Cmd::Def { sym, within } => return ax::symbols::def(ctx, &sym, &within),
        Cmd::Refs {
            sym,
            code_only,
            within,
        } => return ax::symbols::refs(ctx, &sym, code_only, &within),
        Cmd::Read { .. } => "read",
        Cmd::Edit { .. } => "edit",
        Cmd::Write { .. } => "write",
        Cmd::Patch => "patch",
        Cmd::Diff => "diff",
        Cmd::AgentHelp => "agent-help",
    };
    Err(AxError(format!("{name}: not built yet")))
}

fn main() {
    let cli = Cli::parse();
    let result = Ctx::from_env()
        .map_err(AxError::from)
        .and_then(|ctx| run(&ctx, cli.cmd));
    match result {
        Ok(report) => {
            let out = if cli.json {
                report.render_json()
            } else {
                report.render_text()
            };
            // `ax grep … | head` closing the pipe early is fine, not a panic
            use std::io::Write;
            let _ = std::io::stdout().lock().write_all(out.as_bytes());
        }
        Err(e) => {
            if cli.json {
                println!("{}", serde_json::json!({ "error": e.0 }));
            } else {
                eprintln!("ax: {e}");
            }
            std::process::exit(1);
        }
    }
}
