# Fork 仓库与上游（upstream）同步指南

在个人 fork 上开发时，需要定期拉取源项目（如 `microsoft/qlib`）的最新提交。本文说明远程配置、常见报错原因，以及合并与变基两种同步方式。

## 前置：配置 upstream远程

若尚未添加源仓库为 `upstream`：

```bash
git remote add upstream https://github.com/microsoft/qlib.git
```

查看远程：

```bash
git remote -v
```

通常会有：

- `origin`：你的 fork（推送目标）
- `upstream`：上游官方仓库（只读拉取即可）

## 为什么会出现「分叉分支」报错

执行 `git pull upstream main` 时，Git 会：先 `fetch`，再把 `upstream/main` 合并进**当前分支**。

若同时满足：

- 你的分支上有上游还没有的提交（例如在 fork 上的开发、文档修改）；
- 上游 `main` 上又有你本地还没有的提交；

则两边历史已经**分叉**。新版 Git 会提示必须先指定「如何调和」：**merge（合并）**、**rebase（变基）** 或 **仅快进（ff-only）**，否则会报错：

```text
fatal: Need to specify how to reconcile divergent branches.
```

这是正常现象，不是仓库损坏。

## 方法一：合并（merge）

**特点**：会生成一个合并提交；不改写已有提交的哈希；上手简单，适合大多数人。

```bash
git fetch upstream
git merge upstream/main
```

若有冲突：按文件解决后执行：

```bash
git add <已解决文件>
git commit
```

推送到你的 fork：

```bash
git push origin main
```

等价的一行拉取（显式要求合并策略，避免配置歧义）：

```bash
git pull upstream main --no-rebase
git push origin main
```

## 方法二：变基（rebase）

**特点**：把你的提交「挪到」当前 `upstream/main` 顶端之后，历史呈一条直线；本地提交的 commit hash 会变化。

```bash
git fetch upstream
git rebase upstream/main
```

若有冲突：解决后执行：

```bash
git add <已解决文件>
git rebase --continue
```

推送到 fork：若该分支曾推送过，rebase 后需改写远程历史，一般使用：

```bash
git push --force-with-lease origin main
```

**注意**：仅在确认没有其他人基于你 fork 的该分支协作时使用 force推送；团队共用分支慎用 rebase + force。

等价的一行拉取：

```bash
git pull upstream main --rebase
```

## 长期工作流建议

1. **在功能分支上开发**，`main` 尽量只负责同步上游与合并稳定内容。
2. **同步上游**：在 `main`（或你约定的基线分支）上执行 `git fetch upstream`，再对 `upstream/main` 做 `merge` 或 `rebase`，然后把更新合并或变基到你的功能分支。
3. **偶尔对齐**：若只在 `main` 上小改，可直接将 `upstream/main` merge/rebase 进当前分支，再 `push` 到 `origin`。

## 关于 `git config pull.rebase`

报错中的提示用于设置**以后**执行 `git pull` 时的默认策略（merge / rebase / 仅快进）。你也可以**不改全局配置**，每次在命令中写明：

- `--no-rebase`：合并；
- `--rebase`：变基；
- `--ff-only`：仅允许快进（若已分叉则会失败）。

## 简要选择建议

| 场景 | 建议 |
|------|------|
| 个人 fork、希望少踩坑 | 优先 `git fetch upstream && git merge upstream/main`，解决冲突后 `git push origin main` |
| 强烈偏好线性历史，且可接受必要时 `--force-with-lease` | 使用 `rebase` |

## 参考命令速查

```bash
# 仅查看上游更新（不改工作区）
git fetch upstream

# 合并上游 main 到当前分支
git merge upstream/main

# 将当前分支变基到上游 main 之上
git rebase upstream/main

# 推送到自己的 fork
git push origin main
```
