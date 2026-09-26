//! the only code that writes to disk.
//!
//! writes go to a temp file in the same dir, get fsynced, then renamed over
//! the target, so a crash never leaves a half-written file. permissions are
//! kept. symlinks are written through (the link stays a link). anything that
//! resolves outside the repo root is refused.

use crate::{AxError, Ctx, Result, repo};
use std::io::Write;
use std::path::{Path, PathBuf};

/// resolve a user path for writing: absolute, inside the repo, symlinks
/// followed to their target.
pub fn target(ctx: &Ctx, path: &str) -> Result<PathBuf> {
    let abs = repo::absolute(&ctx.cwd, path.as_ref());
    if !repo::inside(&ctx.root, &abs) {
        return Err(AxError(format!(
            "refusing to write {path}: it's outside the repo ({})",
            ctx.root.display()
        )));
    }
    // follow a symlink to what it points at, and re-check that
    if abs.is_symlink() {
        let real = abs
            .canonicalize()
            .map_err(|e| AxError(format!("can't resolve symlink {path}: {e}")))?;
        if !repo::inside(&ctx.root, &real) {
            return Err(AxError(format!(
                "refusing to write {path}: it links outside the repo"
            )));
        }
        return Ok(real);
    }
    Ok(abs)
}

/// atomically replace (or create) `path` with `bytes`.
pub fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let dir = path
        .parent()
        .ok_or_else(|| AxError(format!("no parent dir for {}", path.display())))?;
    std::fs::create_dir_all(dir)?;
    let name = path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    let tmp = dir.join(format!(".{name}.ax-tmp-{}", std::process::id()));
    let perms = std::fs::metadata(path).ok().map(|m| m.permissions());
    let res = (|| -> std::io::Result<()> {
        let mut f = std::fs::File::create(&tmp)?;
        f.write_all(bytes)?;
        f.sync_all()?;
        if let Some(p) = &perms {
            std::fs::set_permissions(&tmp, p.clone())?;
        }
        std::fs::rename(&tmp, path)
    })();
    if let Err(e) = res {
        let _ = std::fs::remove_file(&tmp);
        return Err(AxError(format!("write {} failed: {e}", path.display())));
    }
    Ok(())
}

/// write several files all-or-nothing: if any write fails, the ones already
/// written are put back the way they were. `None` = delete the file.
pub fn atomic_write_all(changes: &[(PathBuf, Option<Vec<u8>>)]) -> Result<()> {
    let mut done: Vec<(PathBuf, Option<Vec<u8>>)> = Vec::new();
    for (path, new) in changes {
        let before = std::fs::read(path).ok();
        let res = match new {
            Some(b) => atomic_write(path, b),
            None => std::fs::remove_file(path).map_err(AxError::from),
        };
        if let Err(e) = res {
            for (p, old) in done.into_iter().rev() {
                let _ = match old {
                    Some(b) => atomic_write(&p, &b),
                    None => std::fs::remove_file(&p).map_err(AxError::from),
                };
            }
            return Err(e);
        }
        done.push((path.clone(), before));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn writes_and_keeps_mode() {
        let t = tempfile::tempdir().unwrap();
        let p = t.path().join("x.sh");
        std::fs::write(&p, "old").unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o755)).unwrap();
        }
        atomic_write(&p, b"new").unwrap();
        assert_eq!(std::fs::read(&p).unwrap(), b"new");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let m = std::fs::metadata(&p).unwrap().permissions().mode();
            assert_eq!(m & 0o777, 0o755);
        }
        // no temp litter
        assert_eq!(std::fs::read_dir(t.path()).unwrap().count(), 1);
    }

    #[test]
    fn creates_dirs() {
        let t = tempfile::tempdir().unwrap();
        let p = t.path().join("a/b/c.txt");
        atomic_write(&p, b"hi").unwrap();
        assert_eq!(std::fs::read(&p).unwrap(), b"hi");
    }

    #[test]
    fn all_or_nothing_rolls_back() {
        let t = tempfile::tempdir().unwrap();
        let a = t.path().join("a.txt");
        std::fs::write(&a, "A").unwrap();
        // second target's parent is a file, so creating it fails
        std::fs::write(t.path().join("f"), "not a dir").unwrap();
        let bad = t.path().join("f/child.txt");
        let r = atomic_write_all(&[
            (a.clone(), Some(b"A2".to_vec())),
            (bad, Some(b"x".to_vec())),
        ]);
        assert!(r.is_err());
        assert_eq!(std::fs::read(&a).unwrap(), b"A");
    }
}
