---
name: sync-repo-to-git
description: >
  将代码库与 Git 远程同步：拉取远程更新、提交并推送本地更改。
  在用户询问同步到 git、拉取更新、push、提交并推送、更新远程仓库时使用。
---

# 同步代码库更新到 Git

指导用户或代其执行「拉取远程 → 提交本地 → 推送到远程」的完整同步流程。

## 同步前先检查状态

在建议具体命令前，先确认当前仓库状态：

1. **是否落后于远程**：`git fetch origin` 后比较 `HEAD` 与 `origin/<当前分支>`（如 `origin/main`）。
2. **是否有未提交更改**：`git status --short`。
3. **是否有未推送提交**：`git status` 或 `git log origin/<分支>..HEAD`。

根据结果决定先 pull、先 commit、还是先 push，并注意**避免在未提交更改时直接 pull**（易产生冲突或覆盖）。

## 推荐流程

### 1. 拉取远程更新（本地无未提交改动时）

```bash
git fetch origin
git pull origin <当前分支名>
```

若用户希望「拉取前先切到某分支」：

```bash
git checkout <分支名>
git pull origin <分支名>
```

### 2. 提交本地更改

确认要纳入提交的文件后：

```bash
git add <文件或路径>   # 或 git add -A
git commit -m "<清晰的一次性提交说明>"
```

提交信息宜简洁、用中文或英文均可，说明「做了什么」而非「改了什么文件」。

### 3. 推送到远程

```bash
git push origin <当前分支名>
```

若该分支首次推送或需设置上游：

```bash
git push -u origin <分支名>
```

## 常见场景速查

| 场景           | 建议操作 |
|----------------|----------|
| 只同步远程到本地 | `git pull origin <分支>`（确保无未提交改动） |
| 只把本地推上去   | `git push origin <分支>` |
| 有未提交改动且要先更新 | 先 `git stash`，再 `git pull`，再 `git stash pop`，解决冲突后提交、推送 |
| 想先看远程有无更新 | `git fetch origin`，再 `git log HEAD..origin/<分支>` 或 `git diff HEAD origin/<分支>` |

## 本仓库的持续同步脚本（可选）

仓库根目录下存在 `scripts/watch_git_pull.py`：

- **作用**：持续监听当前仓库的指定分支（默认 `main`），当 `origin` 有新提交时自动 `git pull`；若 `skills/` 下有变更，会将对应 skill 目录同步到 `~/.openclaw/workspace/skills`。
- **适用**：需要「后台自动拉取 + 同步 skills 到 OpenClaw」时，可由用户在本机运行。
- **用法示例**：
  ```bash
  python scripts/watch_git_pull.py --repo . --branch main --interval 60
  ```
  支持 `--repo`（本地路径或 clone URL）、`--work-dir`、`--branch`、`--interval`、`--openclaw-skills-dir` 等参数。仅依赖 Python 标准库。

当用户问「自动拉取」「监听 git 更新」「同步 skills 到 OpenClaw」时，可指向该脚本并说明上述用法。
