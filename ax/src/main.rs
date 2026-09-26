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
    Grep { pattern: String },
    /// symbol outline of a file or dir
    Outline { path: String },
    /// jump to a symbol definition
    Def { sym: String },
    /// find references to a symbol
    Refs { sym: String },
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
        Cmd::Grep { .. } => "grep",
        Cmd::Outline { .. } => "outline",
        Cmd::Def { .. } => "def",
        Cmd::Refs { .. } => "refs",
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
            print!("{out}");
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
