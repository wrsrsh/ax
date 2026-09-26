pub mod config;
pub mod diff;
pub mod edit;
pub mod find;
pub mod fsio;
pub mod grep;
pub mod hash;
pub mod hits;
pub mod map;
pub mod output;
pub mod read;
pub mod repo;
pub mod symbols;
pub mod syntax;
pub mod text;
pub mod walk;

use std::path::PathBuf;

/// everything a command needs to know about where it's running.
#[derive(Debug, Clone)]
pub struct Ctx {
    pub cfg: config::Config,
    pub cwd: PathBuf,
    pub root: PathBuf,
}

impl Ctx {
    pub fn from_env() -> std::io::Result<Self> {
        let cwd = std::env::current_dir()?;
        let root = repo::find_root(&cwd);
        Ok(Ctx {
            cfg: config::Config::from_env(),
            cwd,
            root,
        })
    }
}

/// a real error (bad path, io failure, refused write). "no matches" is not one.
#[derive(Debug)]
pub struct AxError(pub String);

impl std::fmt::Display for AxError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for AxError {}

impl From<std::io::Error> for AxError {
    fn from(e: std::io::Error) -> Self {
        AxError(e.to_string())
    }
}

pub type Result<T> = std::result::Result<T, AxError>;
