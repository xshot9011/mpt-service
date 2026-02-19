---
description: Prepare PR - generate branch name, commit message, and PR description from current git diff
---

# Prepare PR

When the user asks to "prepare PR", follow these steps:

1. Run `git status` and `git diff` (or `git diff main..HEAD` if on a branch) to understand all changes.
2. Analyze the changes to determine:
   - The type prefix: `feat`, `fix`, `chore`, `refactor`, `docs`, `test`, `ci`, `perf`, `style`, or `build`
   - A short detail slug for the branch name
   - A concise commit message
   - A descriptive PR body

3. Output exactly **3 copyable codeblocks** in this order:

### 1. Branch checkout command
```
git checkout -b <type>/<detail-slug>
```

### 2. Commit command (stage all + commit)
```
git add -A && git commit -m "<type>: <short description>"
```

### 3. PR description (markdown)
```markdown
## <type>: <title>

### Description
<what this PR does and why>

### Changes
| File | Description |
|---|---|
| `file` | what changed |

### Notes
<any important context, warnings, or follow-ups>
```

## Rules
- All 3 outputs MUST be in fenced codeblocks so the user can copy-paste directly.
- Branch name uses kebab-case for the detail slug (e.g. `feat/init-django-project`).
- Commit message follows conventional commits format.
- PR description should be concise but informative.
- If already on a feature branch, skip the checkout command and note it.
