//! tree-sitter layer: which language a file is, the symbols in it, the
//! innermost symbol around a line, parse-error counts, and "is this byte
//! offset code or a comment/string".
//!
//! everything here is syntactic. `def`/`refs` match names, they don't know
//! types, so same-named things in different scopes all show up.

use tree_sitter::{Language, Node, Parser, Tree};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lang {
    TypeScript,
    Tsx,
    JavaScript,
    Python,
    Rust,
    Go,
}

impl Lang {
    pub fn from_path(path: &str) -> Option<Lang> {
        let ext = path.rsplit_once('.')?.1;
        Some(match ext {
            "ts" | "mts" | "cts" => Lang::TypeScript,
            "tsx" => Lang::Tsx,
            "js" | "jsx" | "mjs" | "cjs" => Lang::JavaScript,
            "py" | "pyi" => Lang::Python,
            "rs" => Lang::Rust,
            "go" => Lang::Go,
            _ => return None,
        })
    }

    fn language(self) -> Language {
        match self {
            Lang::TypeScript => tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into(),
            Lang::Tsx => tree_sitter_typescript::LANGUAGE_TSX.into(),
            Lang::JavaScript => tree_sitter_javascript::LANGUAGE.into(),
            Lang::Python => tree_sitter_python::LANGUAGE.into(),
            Lang::Rust => tree_sitter_rust::LANGUAGE.into(),
            Lang::Go => tree_sitter_go::LANGUAGE.into(),
        }
    }
}

pub fn parse(lang: Lang, src: &[u8]) -> Option<Tree> {
    let mut p = Parser::new();
    p.set_language(&lang.language()).ok()?;
    p.parse(src, None)
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct Symbol {
    pub kind: &'static str,
    pub name: String,
    /// dotted path through enclosing symbols, e.g. `Hono.fetch`
    pub path: String,
    /// 1-based, inclusive
    pub start: usize,
    pub end: usize,
    pub depth: usize,
}

fn text<'a>(n: Node, src: &'a [u8]) -> &'a str {
    std::str::from_utf8(&src[n.byte_range()]).unwrap_or("")
}

fn field_text(n: Node, field: &str, src: &[u8]) -> Option<String> {
    n.child_by_field_name(field)
        .map(|c| text(c, src).to_string())
        .filter(|s| !s.is_empty())
}

/// strip generics / pointers / refs from a type name: `*Server` -> `Server`,
/// `Foo<T>` -> `Foo`, `&'a mut Bar` -> `Bar`.
fn bare_type(s: &str) -> String {
    let s = s
        .split('<')
        .next()
        .unwrap_or(s)
        .split('[')
        .next()
        .unwrap_or(s);
    s.rsplit(|c: char| !(c.is_alphanumeric() || c == '_'))
        .find(|p| !p.is_empty())
        .unwrap_or(s)
        .to_string()
}

/// is `n` a definition? returns (kind, name).
fn def_of(lang: Lang, n: Node, src: &[u8], in_class: bool) -> Option<(&'static str, String)> {
    let k = n.kind();
    let name = || field_text(n, "name", src);
    match lang {
        Lang::TypeScript | Lang::Tsx | Lang::JavaScript => match k {
            "function_declaration" | "generator_function_declaration" | "function_signature" => {
                Some(("function", name().unwrap_or_else(|| "default".into())))
            }
            "class_declaration" | "abstract_class_declaration" => {
                Some(("class", name().unwrap_or_else(|| "default".into())))
            }
            "class" => name().map(|n| ("class", n)),
            "method_definition" | "method_signature" | "abstract_method_signature" => {
                name().map(|n| ("method", n))
            }
            // `export default function () {}` / `export default () => {}`
            "export_statement" => {
                let v = n.child_by_field_name("value")?;
                match v.kind() {
                    "function_expression"
                    | "function"
                    | "arrow_function"
                    | "generator_function" => Some(("function", "default".into())),
                    "class" if v.child_by_field_name("name").is_none() => {
                        Some(("class", "default".into()))
                    }
                    _ => None,
                }
            }
            "interface_declaration" => name().map(|n| ("interface", n)),
            "type_alias_declaration" => name().map(|n| ("type", n)),
            "enum_declaration" => name().map(|n| ("enum", n)),
            "internal_module" | "module" => name().map(|n| ("namespace", n)),
            "variable_declarator" | "public_field_definition" | "field_definition" => {
                let v = n.child_by_field_name("value")?;
                let kind = match v.kind() {
                    "arrow_function"
                    | "function_expression"
                    | "function"
                    | "generator_function" => {
                        if k == "variable_declarator" {
                            "function"
                        } else {
                            "method"
                        }
                    }
                    "class" => "class",
                    _ => return None,
                };
                let nm = n
                    .child_by_field_name("name")
                    .or_else(|| n.child_by_field_name("property"))?;
                matches!(
                    nm.kind(),
                    "identifier" | "property_identifier" | "private_property_identifier"
                )
                .then(|| (kind, text(nm, src).to_string()))
            }
            _ => None,
        },
        Lang::Python => match k {
            "function_definition" => {
                name().map(|n| (if in_class { "method" } else { "function" }, n))
            }
            "class_definition" => name().map(|n| ("class", n)),
            _ => None,
        },
        Lang::Rust => match k {
            "function_item" | "function_signature_item" => {
                name().map(|n| (if in_class { "method" } else { "fn" }, n))
            }
            "struct_item" => name().map(|n| ("struct", n)),
            "enum_item" => name().map(|n| ("enum", n)),
            "union_item" => name().map(|n| ("union", n)),
            "trait_item" => name().map(|n| ("trait", n)),
            "mod_item" => name().map(|n| ("mod", n)),
            "macro_definition" => name().map(|n| ("macro", n)),
            "const_item" | "static_item" => name().map(|n| ("const", n)),
            "type_item" => name().map(|n| ("type", n)),
            "impl_item" => {
                let ty = field_text(n, "type", src).map(|t| bare_type(&t))?;
                Some(("impl", ty))
            }
            _ => None,
        },
        Lang::Go => match k {
            "function_declaration" => name().map(|n| ("func", n)),
            "method_declaration" => name().map(|n| ("method", n)),
            "type_spec" => {
                let kind = match n.child_by_field_name("type").map(|t| t.kind()) {
                    Some("struct_type") => "struct",
                    Some("interface_type") => "interface",
                    _ => "type",
                };
                name().map(|n| (kind, n))
            }
            _ => None,
        },
    }
}

/// go methods live at top level but belong to their receiver type.
fn go_receiver(n: Node, src: &[u8]) -> Option<String> {
    let recv = n.child_by_field_name("receiver")?;
    let mut c = recv.walk();
    for p in recv.named_children(&mut c) {
        if let Some(t) = p.child_by_field_name("type") {
            return Some(bare_type(text(t, src)));
        }
    }
    None
}

/// symbols whose function children are methods (a fn inside `mod` is not).
fn is_container(kind: &str) -> bool {
    matches!(kind, "class" | "interface" | "impl" | "trait")
}

pub fn symbols(lang: Lang, tree: &Tree, src: &[u8]) -> Vec<Symbol> {
    let mut out = Vec::new();
    // (node, parent path, depth, parent is a class-like container)
    let mut stack: Vec<(Node, String, usize, bool)> =
        vec![(tree.root_node(), String::new(), 0, false)];
    while let Some((n, parent, depth, in_class)) = stack.pop() {
        let mut child_parent = parent.clone();
        let mut child_depth = depth;
        let mut child_in_class = in_class;
        if let Some((kind, name)) = def_of(lang, n, src, in_class) {
            let mut path = if parent.is_empty() {
                name.clone()
            } else {
                format!("{parent}.{name}")
            };
            if lang == Lang::Go
                && kind == "method"
                && let Some(r) = go_receiver(n, src)
            {
                path = format!("{r}.{name}");
            }
            out.push(Symbol {
                kind,
                name,
                path: path.clone(),
                start: n.start_position().row + 1,
                end: n.end_position().row + 1,
                depth,
            });
            child_parent = path;
            child_depth = depth + 1;
            child_in_class = is_container(kind);
        }
        let mut c = n.walk();
        let kids: Vec<Node> = n.named_children(&mut c).collect();
        for k in kids.into_iter().rev() {
            stack.push((k, child_parent.clone(), child_depth, child_in_class));
        }
    }
    out.sort_by_key(|s| (s.start, s.depth));
    out
}

/// innermost symbol whose range contains `line` (1-based).
pub fn enclosing(syms: &[Symbol], line: usize) -> Option<&Symbol> {
    syms.iter()
        .filter(|s| s.start <= line && line <= s.end)
        .max_by_key(|s| (s.depth, s.start))
}

/// ERROR + MISSING nodes in the tree.
pub fn error_count(tree: &Tree) -> usize {
    let mut n = 0;
    let mut stack = vec![tree.root_node()];
    while let Some(node) = stack.pop() {
        if node.is_error() || node.is_missing() {
            n += 1;
        }
        if node.has_error() {
            let mut c = node.walk();
            stack.extend(node.children(&mut c));
        }
    }
    n
}

pub fn parse_errors(lang: Lang, src: &[u8]) -> Option<usize> {
    parse(lang, src).map(|t| error_count(&t))
}

/// true if the byte range sits in code, false if it's inside a comment or a
/// string (template substitutions like `${x}` count as code again).
pub fn is_code(tree: &Tree, start: usize, end: usize) -> bool {
    let Some(mut n) = tree.root_node().descendant_for_byte_range(start, end) else {
        return true;
    };
    loop {
        let k = n.kind();
        if matches!(k, "template_substitution" | "interpolation") {
            return true;
        }
        if k.contains("comment") || k.contains("string") || k == "char_literal" {
            return false;
        }
        match n.parent() {
            Some(p) => n = p,
            None => return true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn syms(lang: Lang, src: &str) -> Vec<(String, &'static str, usize, usize)> {
        let t = parse(lang, src.as_bytes()).unwrap();
        symbols(lang, &t, src.as_bytes())
            .into_iter()
            .map(|s| (s.path, s.kind, s.start, s.end))
            .collect()
    }

    #[test]
    fn typescript() {
        let src = "\
export class Hono<E> {
  router: Router
  get(path: string) {
    return 1
  }
  fetch = (req: Request) => {
    return this.dispatch(req)
  }
}
interface Env { a: string }
type Handler = () => void
export const compose = (m: any[]) => {
  const inner = function () {}
}
function helper() {}
enum Mode { A, B }
";
        let s = syms(Lang::TypeScript, src);
        assert_eq!(
            s,
            vec![
                ("Hono".into(), "class", 1, 9),
                ("Hono.get".into(), "method", 3, 5),
                ("Hono.fetch".into(), "method", 6, 8),
                ("Env".into(), "interface", 10, 10),
                ("Handler".into(), "type", 11, 11),
                ("compose".into(), "function", 12, 14),
                ("compose.inner".into(), "function", 13, 13),
                ("helper".into(), "function", 15, 15),
                ("Mode".into(), "enum", 16, 16),
            ]
        );
    }

    #[test]
    fn tsx_and_js() {
        let s = syms(Lang::Tsx, "const App = () => <div>hi</div>\n");
        assert_eq!(s, vec![("App".into(), "function", 1, 1)]);
        let s = syms(
            Lang::JavaScript,
            "class A { m() {} }\nexport default function () {}\n",
        );
        assert_eq!(
            s,
            vec![
                ("A".into(), "class", 1, 1),
                ("A.m".into(), "method", 1, 1),
                ("default".into(), "function", 2, 2),
            ]
        );
    }

    #[test]
    fn python() {
        let src = "class A:\n    @property\n    def x(self):\n        return 1\n\ndef top():\n    def inner():\n        pass\n";
        assert_eq!(
            syms(Lang::Python, src),
            vec![
                ("A".into(), "class", 1, 4),
                ("A.x".into(), "method", 3, 4),
                ("top".into(), "function", 6, 8),
                ("top.inner".into(), "function", 7, 8),
            ]
        );
    }

    #[test]
    fn rust() {
        let src = "struct S;\nimpl<T> Foo for S<T> {\n    fn go(&self) {}\n}\nmod m {\n    pub fn f() {}\n}\nmacro_rules! mac { () => {} }\n";
        assert_eq!(
            syms(Lang::Rust, src),
            vec![
                ("S".into(), "struct", 1, 1),
                ("S".into(), "impl", 2, 4),
                ("S.go".into(), "method", 3, 3),
                ("m".into(), "mod", 5, 7),
                ("m.f".into(), "fn", 6, 6),
                ("mac".into(), "macro", 8, 8),
            ]
        );
    }

    #[test]
    fn go() {
        let src = "package x\n\ntype Server struct{}\n\ntype H interface{ Do() }\n\nfunc (s *Server) Handle() {}\n\nfunc main() {}\n";
        assert_eq!(
            syms(Lang::Go, src),
            vec![
                ("Server".into(), "struct", 3, 3),
                ("H".into(), "interface", 5, 5),
                ("Server.Handle".into(), "method", 7, 7),
                ("main".into(), "func", 9, 9),
            ]
        );
    }

    #[test]
    fn enclosing_picks_innermost() {
        let src = "class A {\n  m() {\n    const f = () => {\n      go()\n    }\n  }\n}\n";
        let t = parse(Lang::TypeScript, src.as_bytes()).unwrap();
        let s = symbols(Lang::TypeScript, &t, src.as_bytes());
        assert_eq!(enclosing(&s, 4).unwrap().path, "A.m.f");
        assert_eq!(enclosing(&s, 6).unwrap().path, "A.m");
        assert_eq!(enclosing(&s, 1).unwrap().path, "A");
        assert!(enclosing(&s, 99).is_none());
    }

    #[test]
    fn errors() {
        assert_eq!(parse_errors(Lang::Rust, b"fn a() {}"), Some(0));
        assert!(parse_errors(Lang::Rust, b"fn a( {}").unwrap() > 0);
        assert!(parse_errors(Lang::TypeScript, b"const x = ;").unwrap() > 0);
        assert!(parse_errors(Lang::Python, b"def f(:\n  pass").unwrap() > 0);
    }

    #[test]
    fn code_vs_comments_and_strings() {
        let src = "// foo here\nconst a = foo + 'foo' + `x${foo}` // foo\n";
        let t = parse(Lang::TypeScript, src.as_bytes()).unwrap();
        let hits: Vec<bool> = src
            .match_indices("foo")
            .map(|(i, _)| is_code(&t, i, i + 3))
            .collect();
        assert_eq!(hits, vec![false, true, false, true, false]);
    }

    #[test]
    fn langs() {
        assert_eq!(Lang::from_path("a/b.mts"), Some(Lang::TypeScript));
        assert_eq!(Lang::from_path("x.tsx"), Some(Lang::Tsx));
        assert_eq!(Lang::from_path("x.md"), None);
        assert_eq!(Lang::from_path("Makefile"), None);
    }
}
