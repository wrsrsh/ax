# parity: ax vs rg

- ax: ax 0.1.0
- ax commit: f99b4c8
- rg: ripgrep 14.1.0
- repos: hono@ee0622e144, ripgrep@3fce3b5bb0, requests@611c6162cb, cobra@adbc881390, ax@HEAD

**120/120 cases identical.**

| repo | tool | args | rg | ax | ok |
|---|---|---|---|---|---|
| hono | find | `(all)` | 454 | 454 | yes |
| hono | find | `*.md` | 8 | 8 | yes |
| hono | find | `**/*test*` | 144 | 144 | yes |
| hono | find | `!*.md` | 446 | 446 | yes |
| hono | grep | `TODO` | 0 | 0 | yes |
| hono | grep | `-i error` | 1779 | 1779 | yes |
| hono | grep | `-w self` | 72 | 72 | yes |
| hono | grep | `-w c` | 4781 | 4781 | yes |
| hono | grep | `-F ()` | 12170 | 12170 | yes |
| hono | grep | `-F .` | 29994 | 29994 | yes |
| hono | grep | `return\s+\w+` | 2267 | 2267 | yes |
| hono | grep | `^\s*(pub )?fn ` | 0 | 0 | yes |
| hono | grep | `-S Err` | 915 | 915 | yes |
| hono | grep | `-S err` | 2454 | 2454 | yes |
| hono | grep | `-g *.md the` | 74 | 74 | yes |
| hono | grep | `-g !*.md the` | 1476 | 1476 | yes |
| hono | grep | `-t rust impl` | 0 | 0 | yes |
| hono | grep | `-t py def` | 0 | 0 | yes |
| hono | grep | `-t go func` | 0 | 0 | yes |
| hono | grep | `-t ts export` | 921 | 921 | yes |
| hono | grep | `-C 2 TODO` | 0 | 0 | yes |
| hono | grep | `nothing-should-ever-match-this-zq9` | 0 | 0 | yes |
| hono | grep | `-l test` | 155 | 155 | yes |
| hono | grep | `-c test` | 155 | 155 | yes |
| ripgrep | find | `(all)` | 231 | 231 | yes |
| ripgrep | find | `*.md` | 23 | 23 | yes |
| ripgrep | find | `**/*test*` | 7 | 7 | yes |
| ripgrep | find | `!*.md` | 208 | 208 | yes |
| ripgrep | grep | `TODO` | 9 | 9 | yes |
| ripgrep | grep | `-i error` | 1337 | 1337 | yes |
| ripgrep | grep | `-w self` | 4889 | 4889 | yes |
| ripgrep | grep | `-w c` | 251 | 251 | yes |
| ripgrep | grep | `-F ()` | 8132 | 8132 | yes |
| ripgrep | grep | `-F .` | 30353 | 30353 | yes |
| ripgrep | grep | `return\s+\w+` | 660 | 660 | yes |
| ripgrep | grep | `^\s*(pub )?fn ` | 2732 | 2732 | yes |
| ripgrep | grep | `-S Err` | 987 | 987 | yes |
| ripgrep | grep | `-S err` | 2653 | 2653 | yes |
| ripgrep | grep | `-g *.md the` | 875 | 875 | yes |
| ripgrep | grep | `-g !*.md the` | 5958 | 5958 | yes |
| ripgrep | grep | `-t rust impl` | 793 | 793 | yes |
| ripgrep | grep | `-t py def` | 0 | 0 | yes |
| ripgrep | grep | `-t go func` | 0 | 0 | yes |
| ripgrep | grep | `-t ts export` | 0 | 0 | yes |
| ripgrep | grep | `-C 2 TODO` | 9 | 9 | yes |
| ripgrep | grep | `nothing-should-ever-match-this-zq9` | 0 | 0 | yes |
| ripgrep | grep | `-l test` | 82 | 82 | yes |
| ripgrep | grep | `-c test` | 81 | 81 | yes |
| requests | find | `(all)` | 102 | 102 | yes |
| requests | find | `*.md` | 5 | 5 | yes |
| requests | find | `**/*test*` | 10 | 10 | yes |
| requests | find | `!*.md` | 97 | 97 | yes |
| requests | grep | `TODO` | 7 | 7 | yes |
| requests | grep | `-i error` | 476 | 476 | yes |
| requests | grep | `-w self` | 1025 | 1025 | yes |
| requests | grep | `-w c` | 30 | 30 | yes |
| requests | grep | `-F ()` | 725 | 725 | yes |
| requests | grep | `-F .` | 6482 | 6482 | yes |
| requests | grep | `return\s+\w+` | 297 | 297 | yes |
| requests | grep | `^\s*(pub )?fn ` | 1 | 1 | yes |
| requests | grep | `-S Err` | 363 | 363 | yes |
| requests | grep | `-S err` | 553 | 553 | yes |
| requests | grep | `-g *.md the` | 238 | 238 | yes |
| requests | grep | `-g !*.md the` | 1393 | 1393 | yes |
| requests | grep | `-t rust impl` | 0 | 0 | yes |
| requests | grep | `-t py def` | 821 | 821 | yes |
| requests | grep | `-t go func` | 0 | 0 | yes |
| requests | grep | `-t ts export` | 0 | 0 | yes |
| requests | grep | `-C 2 TODO` | 7 | 7 | yes |
| requests | grep | `nothing-should-ever-match-this-zq9` | 0 | 0 | yes |
| requests | grep | `-l test` | 36 | 36 | yes |
| requests | grep | `-c test` | 36 | 36 | yes |
| cobra | find | `(all)` | 59 | 59 | yes |
| cobra | find | `*.md` | 17 | 17 | yes |
| cobra | find | `**/*test*` | 17 | 17 | yes |
| cobra | find | `!*.md` | 42 | 42 | yes |
| cobra | grep | `TODO` | 3 | 3 | yes |
| cobra | grep | `-i error` | 979 | 979 | yes |
| cobra | grep | `-w self` | 0 | 0 | yes |
| cobra | grep | `-w c` | 1121 | 1121 | yes |
| cobra | grep | `-F ()` | 1205 | 1205 | yes |
| cobra | grep | `-F .` | 5570 | 5570 | yes |
| cobra | grep | `return\s+\w+` | 479 | 479 | yes |
| cobra | grep | `^\s*(pub )?fn ` | 4 | 4 | yes |
| cobra | grep | `-S Err` | 917 | 917 | yes |
| cobra | grep | `-S err` | 2118 | 2118 | yes |
| cobra | grep | `-g *.md the` | 376 | 376 | yes |
| cobra | grep | `-g !*.md the` | 1334 | 1334 | yes |
| cobra | grep | `-t rust impl` | 0 | 0 | yes |
| cobra | grep | `-t py def` | 0 | 0 | yes |
| cobra | grep | `-t go func` | 953 | 953 | yes |
| cobra | grep | `-t ts export` | 0 | 0 | yes |
| cobra | grep | `-C 2 TODO` | 3 | 3 | yes |
| cobra | grep | `nothing-should-ever-match-this-zq9` | 0 | 0 | yes |
| cobra | grep | `-l test` | 32 | 32 | yes |
| cobra | grep | `-c test` | 32 | 32 | yes |
| ax | find | `(all)` | 99 | 99 | yes |
| ax | find | `*.md` | 6 | 6 | yes |
| ax | find | `**/*test*` | 9 | 9 | yes |
| ax | find | `!*.md` | 93 | 93 | yes |
| ax | grep | `TODO` | 22 | 22 | yes |
| ax | grep | `-i error` | 262 | 262 | yes |
| ax | grep | `-w self` | 104 | 104 | yes |
| ax | grep | `-w c` | 380 | 380 | yes |
| ax | grep | `-F ()` | 2323 | 2323 | yes |
| ax | grep | `-F .` | 22794 | 22794 | yes |
| ax | grep | `return\s+\w+` | 357 | 357 | yes |
| ax | grep | `^\s*(pub )?fn ` | 311 | 311 | yes |
| ax | grep | `-S Err` | 206 | 206 | yes |
| ax | grep | `-S err` | 415 | 415 | yes |
| ax | grep | `-g *.md the` | 50 | 50 | yes |
| ax | grep | `-g !*.md the` | 506 | 506 | yes |
| ax | grep | `-t rust impl` | 29 | 29 | yes |
| ax | grep | `-t py def` | 114 | 114 | yes |
| ax | grep | `-t go func` | 0 | 0 | yes |
| ax | grep | `-t ts export` | 0 | 0 | yes |
| ax | grep | `-C 2 TODO` | 22 | 22 | yes |
| ax | grep | `nothing-should-ever-match-this-zq9` | 11 | 11 | yes |
| ax | grep | `-l test` | 60 | 60 | yes |
| ax | grep | `-c test` | 60 | 60 | yes |

## hyperfine (mean ± stddev, ms; raw json alongside)

| repo | case | ax | rg |
|---|---|---|---|
| hono | files | 4.3 ± 0.7 | 5.2 ± 0.6 |
| hono | grep literal | 8.8 ± 0.3 | 6.3 ± 0.7 |
| hono | grep regex | 15.3 ± 0.8 | 11.1 ± 0.7 |
| hono | grep -i word | 12.2 ± 1.5 | 6.4 ± 0.6 |
| ripgrep | files | 2.9 ± 0.2 | 4.9 ± 0.6 |
| ripgrep | grep literal | 3.6 ± 0.1 | 5.5 ± 0.6 |
| ripgrep | grep regex | 9.0 ± 0.6 | 10.3 ± 0.6 |
| ripgrep | grep -i word | 6.1 ± 0.3 | 5.6 ± 0.5 |
| requests | files | 2.1 ± 0.2 | 3.2 ± 0.6 |
| requests | grep literal | 7.0 ± 1.1 | 5.1 ± 1.4 |
| requests | grep regex | 12.4 ± 1.0 | 10.4 ± 1.7 |
| requests | grep -i word | 26.9 ± 2.6 | 5.0 ± 0.5 |
| cobra | files | 2.4 ± 0.5 | 3.4 ± 0.6 |
| cobra | grep literal | 5.1 ± 0.8 | 4.5 ± 0.5 |
| cobra | grep regex | 12.0 ± 1.0 | 9.8 ± 0.7 |
| cobra | grep -i word | 8.1 ± 2.2 | 4.9 ± 0.5 |
| ax | files | 2.0 ± 0.2 | 3.2 ± 0.6 |
| ax | grep literal | 15.3 ± 1.9 | 4.9 ± 0.5 |
| ax | grep regex | 17.2 ± 1.5 | 10.6 ± 3.5 |
| ax | grep -i word | 15.4 ± 3.0 | 5.0 ± 0.4 |

before/after for parallel grep (old single-threaded numbers next to these): [grep_parallel.md](grep_parallel.md)
