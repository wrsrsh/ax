//! repo root detection + path helpers. everything ax prints is relative to the
//! repo root, and nothing gets written outside it.

use std::path::{Component, Path, PathBuf};

/// walk up from `start` looking for `.git` (dir or file, so worktrees and
/// submodules count). falls back to `start` itself when there's no repo.
pub fn find_root(start: &Path) -> PathBuf {
    let start = start.canonicalize().unwrap_or_else(|_| start.to_path_buf());
    let mut cur = start.as_path();
    loop {
        if cur.join(".git").exists() {
            return cur.to_path_buf();
        }
        match cur.parent() {
            Some(p) => cur = p,
            None => return start,
        }
    }
}

/// lexically normalize `a/./b/../c` -> `a/c` without touching the disk.
pub fn normalize(p: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for c in p.components() {
        match c {
            Component::CurDir => {}
            Component::ParentDir => {
                if !out.pop() {
                    out.push("..");
                }
            }
            other => out.push(other.as_os_str()),
        }
    }
    out
}

/// resolve a user-given path (relative to cwd) to an absolute path.
pub fn absolute(cwd: &Path, p: &Path) -> PathBuf {
    normalize(&if p.is_absolute() {
        p.to_path_buf()
    } else {
        cwd.join(p)
    })
}

/// repo-relative display path, using `/` separators. paths outside the root
/// come back unchanged (absolute).
pub fn rel(root: &Path, abs: &Path) -> String {
    let s = match abs.strip_prefix(root) {
        Ok(r) if r.as_os_str().is_empty() => ".".to_string(),
        Ok(r) => r.to_string_lossy().into_owned(),
        Err(_) => abs.to_string_lossy().into_owned(),
    };
    s.replace('\\', "/")
}

/// true when `abs` is inside `root` after resolving symlinks on the longest
/// existing prefix (so a new file under a symlinked dir that points outside
/// the repo is still caught).
pub fn inside(root: &Path, abs: &Path) -> bool {
    let root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let abs = normalize(abs);
    let mut existing = abs.as_path();
    let mut rest = Vec::new();
    while !existing.exists() {
        match (existing.file_name(), existing.parent()) {
            (Some(name), Some(parent)) => {
                rest.push(name.to_os_string());
                existing = parent;
            }
            _ => return false,
        }
    }
    let Ok(mut real) = existing.canonicalize() else {
        return false;
    };
    for name in rest.into_iter().rev() {
        real.push(name);
    }
    real.starts_with(&root)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn finds_root_from_subdir() {
        let t = tempfile::tempdir().unwrap();
        fs::create_dir_all(t.path().join(".git")).unwrap();
        fs::create_dir_all(t.path().join("a/b")).unwrap();
        let root = find_root(&t.path().join("a/b"));
        assert_eq!(root, t.path().canonicalize().unwrap());
    }

    #[test]
    fn git_file_counts_too() {
        let t = tempfile::tempdir().unwrap();
        fs::write(t.path().join(".git"), "gitdir: elsewhere").unwrap();
        assert_eq!(find_root(t.path()), t.path().canonicalize().unwrap());
    }

    #[test]
    fn no_repo_falls_back_to_start() {
        let t = tempfile::tempdir().unwrap();
        // tempdirs live under /tmp which isn't a repo on any sane machine
        let start = t.path().canonicalize().unwrap();
        let root = find_root(&start);
        assert!(start.starts_with(&root));
    }

    #[test]
    fn normalize_and_rel() {
        assert_eq!(normalize(Path::new("a/./b/../c")), PathBuf::from("a/c"));
        let root = Path::new("/r");
        assert_eq!(rel(root, Path::new("/r/src/x.rs")), "src/x.rs");
        assert_eq!(rel(root, Path::new("/r")), ".");
        assert_eq!(rel(root, Path::new("/elsewhere/x")), "/elsewhere/x");
    }

    #[test]
    fn inside_checks() {
        let t = tempfile::tempdir().unwrap();
        let root = t.path().canonicalize().unwrap();
        fs::create_dir(root.join("src")).unwrap();
        assert!(inside(&root, &root.join("src/new.rs")));
        assert!(inside(&root, &root.join("brand/new/dir/f.rs")));
        assert!(!inside(&root, &root.join("../escape.rs")));
        let out = tempfile::tempdir().unwrap();
        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(out.path(), root.join("link")).unwrap();
            assert!(!inside(&root, &root.join("link/f.rs")));
        }
    }
}
