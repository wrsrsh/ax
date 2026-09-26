## working notes
You are working in an existing repository. Read before you change things, and keep changes small.
- Look around first: the README, the package manifest and the test setup tell you how the project is built and run.
- Find the code that owns the behaviour you are changing before you touch anything. Follow the existing structure.
- Match the surrounding style: naming, error handling, imports, comment density and formatting.
- Prefer the smallest change that fully fixes the problem. Don't refactor unrelated code or rename things you didn't need to.
When you change behaviour, think about the callers:
```
1. who calls this function or uses this type?
2. what do the existing tests expect?
3. which edge cases does the change add or remove?
4. does the change need a new test?
5. did the public api or its types change?
6. could anything else depend on the old behaviour?
7. is there a similar fix somewhere else to copy?
8. does the error message still make sense?
9. is the docs comment still true?
```
Run the relevant tests when you are done if they are cheap to run, and fix what you broke instead of skipping it.
If something is unclear, pick the most conservative reading of the task and keep going instead of stopping.
Leave generated files, lockfiles and vendored code alone unless the task is about them.
Keep commits focused: one logical change, with the reason in the message, and no stray debug output or commented-out code left behind.
When a test fails, read the assertion and the code under test before changing either; the test is usually right.
