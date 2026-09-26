use assert_cmd::Command;

#[test]
fn help_lists_every_subcommand() {
    let out = Command::cargo_bin("ax")
        .unwrap()
        .arg("--help")
        .output()
        .unwrap();
    assert!(out.status.success());
    let help = String::from_utf8(out.stdout).unwrap();
    for cmd in [
        "map",
        "find",
        "grep",
        "outline",
        "def",
        "refs",
        "read",
        "edit",
        "write",
        "patch",
        "diff",
        "agent-help",
    ] {
        assert!(help.contains(cmd), "missing {cmd} in --help");
    }
}

#[test]
fn real_errors_exit_nonzero_and_json_says_so() {
    let out = Command::cargo_bin("ax")
        .unwrap()
        .args(["--json", "patch"])
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(1));
    let v: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert!(v["error"].as_str().unwrap().contains("patch"));
}
