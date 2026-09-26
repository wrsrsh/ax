mod common;
use common::*;
use std::fs;

const LATIN: &[u8] = b"program Caf\xe9;\n{ pr\xfcfung \x80 }\nbegin end.\n";

#[test]
fn windows_1252_reads_decoded_and_edits_stay_1252() {
    let t = fixture();
    fs::write(t.path().join("unit.pas"), LATIN).unwrap();
    let out = stdout(&ax(t.path(), &["read", "unit.pas"]));
    assert!(out.contains("windows-1252"), "{out}");
    assert!(
        out.contains("program Café;") && out.contains("prüfung €"),
        "{out}"
    );

    let o = ax_in(
        t.path(),
        &["edit", "unit.pas"],
        "@@ find\nprüfung €\n@@ with\nprüfung ok é\n",
    );
    assert!(o.status.success(), "{}", stdout(&o));
    assert_eq!(
        fs::read(t.path().join("unit.pas")).unwrap(),
        b"program Caf\xe9;\n{ pr\xfcfung ok \xe9 }\nbegin end.\n"
    );

    // anchored replace with a hash taken from read (over the raw bytes)
    let a = anchor(t.path(), "unit.pas", 1);
    let o = ax_in(
        t.path(),
        &["edit", "unit.pas"],
        format!("@@ replace {a}\nprogram Crème;\n"),
    );
    assert!(o.status.success(), "{}", stdout(&o));
    assert!(
        fs::read(t.path().join("unit.pas"))
            .unwrap()
            .starts_with(b"program Cr\xe8me;\n")
    );
}

#[test]
fn unencodable_characters_are_refused() {
    let t = fixture();
    fs::write(t.path().join("unit.pas"), LATIN).unwrap();
    let o = ax_in(
        t.path(),
        &["edit", "unit.pas"],
        "@@ find\nbegin end.\n@@ with\nbegin 漢 end.\n",
    );
    assert_eq!(o.status.code(), Some(1));
    assert!(stdout(&o).contains("windows-1252"), "{}", stdout(&o));
    assert_eq!(fs::read(t.path().join("unit.pas")).unwrap(), LATIN);

    let p =
        "*** Begin Patch\n*** Update File: unit.pas\n-begin end.\n+begin 漢 end.\n*** End Patch\n";
    let o = ax_in(t.path(), &["patch"], p);
    assert_eq!(o.status.code(), Some(1));
    assert_eq!(fs::read(t.path().join("unit.pas")).unwrap(), LATIN);
}

#[test]
fn patch_and_write_keep_1252() {
    let t = fixture();
    fs::write(t.path().join("unit.pas"), LATIN).unwrap();
    let p = "*** Begin Patch\n*** Update File: unit.pas\n-program Café;\n+program Caféé;\n*** End Patch\n";
    let o = ax_in(t.path(), &["patch"], p);
    assert!(o.status.success(), "{}", stderr(&o));
    assert!(
        fs::read(t.path().join("unit.pas"))
            .unwrap()
            .starts_with(b"program Caf\xe9\xe9;")
    );

    let o = ax_in(t.path(), &["write", "unit.pas", "--force"], "é\n");
    assert!(o.status.success());
    assert_eq!(fs::read(t.path().join("unit.pas")).unwrap(), b"\xe9\n");

    // utf-8 files are left alone
    let o = ax_in(t.path(), &["write", "new.txt"], "é\n");
    assert!(o.status.success());
    assert_eq!(
        fs::read(t.path().join("new.txt")).unwrap(),
        "é\n".as_bytes()
    );
}
