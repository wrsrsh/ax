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
    /// find files by name or glob
    Find { pattern: String },
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

fn main() {
    let cli = Cli::parse();
    let _ = cli.json;
    let name = match cli.cmd {
        Cmd::Map { .. } => "map",
        Cmd::Find { .. } => "find",
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
    eprintln!("ax {name}: not built yet");
    std::process::exit(2);
}
