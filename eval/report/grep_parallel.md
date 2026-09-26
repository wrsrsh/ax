# ax grep in parallel: before / after

grep used to search files one at a time, then tree-sitter parse every shown file
one at a time for the `@` symbol headers. now both run on scoped threads
(`AX_THREADS`, default = cores, 1 = off), results slotted back by index so the
output is byte-identical to the single-threaded version.

- after: ax commit f99b4c8 + this change, ripgrep 14.1.0, 8 cores
- before (committed): the table from eval/report/parity.md at eb2d6bb
- before (rerun): the pre-change binary benched again in the same session as "after",
  so machine noise is the same. speedup is rerun / after.
- the ax repo row is this repo, which has grown since eb2d6bb, so compare it to the rerun

hyperfine mean ± stddev in ms, default output (caps on), stdout to /dev/null.

| repo | case | before (committed) | before (rerun) | after | speedup | rg (after run) |
|---|---|---|---|---|---|---|
| hono | files | 4.0 ± 0.2 | 4.0 ± 0.2 | 4.3 ± 0.7 | 0.92x | 5.2 ± 0.6 |
| hono | grep literal | 14.4 ± 0.2 | 14.9 ± 1.1 | 8.8 ± 0.3 | 1.69x | 6.3 ± 0.7 |
| hono | grep regex | 15.6 ± 0.4 | 16.8 ± 2.0 | 15.3 ± 0.8 | 1.10x | 11.1 ± 0.7 |
| hono | grep -i word | 21.5 ± 0.4 | 21.9 ± 0.7 | 12.2 ± 1.5 | 1.80x | 6.4 ± 0.6 |
| ripgrep | files | 2.9 ± 0.2 | 2.8 ± 0.2 | 2.9 ± 0.2 | 0.99x | 4.9 ± 0.6 |
| ripgrep | grep literal | 4.2 ± 0.3 | 4.2 ± 0.3 | 3.6 ± 0.1 | 1.15x | 5.5 ± 0.6 |
| ripgrep | grep regex | 9.8 ± 0.2 | 9.8 ± 0.2 | 9.0 ± 0.6 | 1.09x | 10.3 ± 0.6 |
| ripgrep | grep -i word | 7.1 ± 0.2 | 7.1 ± 0.2 | 6.1 ± 0.3 | 1.17x | 5.6 ± 0.5 |
| requests | files | 2.1 ± 0.2 | 2.1 ± 0.2 | 2.1 ± 0.2 | 0.99x | 3.2 ± 0.6 |
| requests | grep literal | 7.5 ± 0.2 | 7.6 ± 0.4 | 7.0 ± 1.1 | 1.09x | 5.1 ± 1.4 |
| requests | grep regex | 14.4 ± 0.3 | 14.8 ± 0.8 | 12.4 ± 1.0 | 1.20x | 10.4 ± 1.7 |
| requests | grep -i word | 33.0 ± 0.8 | 33.1 ± 1.1 | 26.9 ± 2.6 | 1.23x | 5.0 ± 0.5 |
| cobra | files | 2.3 ± 0.2 | 2.3 ± 0.2 | 2.4 ± 0.5 | 0.97x | 3.4 ± 0.6 |
| cobra | grep literal | 5.3 ± 0.2 | 5.3 ± 0.5 | 5.1 ± 0.8 | 1.04x | 4.5 ± 0.5 |
| cobra | grep regex | 12.5 ± 0.2 | 12.9 ± 1.0 | 12.0 ± 1.0 | 1.07x | 9.8 ± 0.7 |
| cobra | grep -i word | 8.1 ± 0.2 | 8.3 ± 0.6 | 8.1 ± 2.2 | 1.02x | 4.9 ± 0.5 |
| ax | files | 1.8 ± 0.2 | 2.1 ± 0.2 | 2.0 ± 0.2 | 1.07x | 3.2 ± 0.6 |
| ax | grep literal | 19.1 ± 0.3 | 26.5 ± 2.8 | 15.3 ± 1.9 | 1.74x | 4.9 ± 0.5 |
| ax | grep regex | 15.6 ± 0.2 | 25.5 ± 8.2 | 17.2 ± 1.5 | 1.48x | 10.6 ± 3.5 |
| ax | grep -i word | 11.4 ± 0.2 | 64.4 ± 19.0 | 15.4 ± 3.0 | 4.19x | 5.0 ± 0.4 |

`files` is `ax find` and untouched by this change; it is in the table as a noise check.

the ax rows in the rerun were noisy (other jobs on the box, load avg ~4.5), so here they
are again with both binaries in one interleaved hyperfine run (30+ runs each):

| repo | case | before | after | speedup |
|---|---|---|---|---|
| ax | grep literal | 26.2 ± 2.1 | 13.6 ± 1.3 | 1.93x |
| ax | grep regex | 19.6 ± 1.6 | 16.5 ± 1.1 | 1.19x |
| ax | grep -i word | 26.3 ± 1.6 | 15.0 ± 1.3 | 1.75x |

what is left: the slow cases are one big file being parsed for symbols. requests
`-i -w error` spends ~20 ms of its ~24 ms parsing tests/test_requests.py (3k lines),
which threads can not split. with `AX_NO_SYMBOLS=1` the same search is ~4 ms.
