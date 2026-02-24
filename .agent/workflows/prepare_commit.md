---
description: Prepare Commit - generate a commit message based on staged changes
---

# Prepare Commit

When the user asks to "prepare commit", follow these steps:

1. Run `git diff --cached --name-status` to get a concise list of staged files and their change types. If there are no staged files, advise the user to `git add` the files they wish to include first.
2. Analyze only the staged changes to determine the conventional commit type (`feat`, `fix`, `chore`, `refactor`, `docs`, `test`, `ci`, `perf`, `style`, or `build`) and a short description.
3. Output EXACTLY **1 copyable codeblock** containing the commit command.

### 1. Commit command
```bash
git commit -m "<type>: <short description>"
```

## Rules
- The output MUST be in a fenced codeblock so the user can copy-paste directly.
- The commit message must follow the Conventional Commits format.
- Keep the short description under 50 characters.
- Ensure the description accurately reflects ONLY the staged changes.
