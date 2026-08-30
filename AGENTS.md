# Commit guidelines
1. Git commit信息。必须是简洁且规范，需要是中英双语。Commit内容包含为：本次修改的总结性概述，加上结构化有序标点描述。正文必须使用实际的换行符、空行及空格进行排版，严禁使用诸如 `\n` 或 `\t` 之类的转义字符来模拟格式效.

示例：

中文
  概述：一句话总结本次修改。
  变更：
    1. 第一项关键改动。
    2. 第二项关键改动。
  验证：
    1. 相关验证信息。

English
  Summary: One-line overview of the change.
  Changes:
    1. First key update.
    2. Second key update.
  Verification:
    1. Relevant verification notes.

# Worktree guidelines
1. 凡涉及新增功能、功能变更或代码修改的任务，必须询问用户是否使用 Git Worktree 来改动。 如果当前已经在某一个 Git Workstream 中，则无需询问。 

# CHANGELOG guidelines
1. 仓库根目录维护一份 `CHANGELOG.md`，作为全部代码变更的唯一记录入口。
2. 所有变更（含功能新增、功能调整、Bug 修复、重构、依赖或配置变化）都必须同步更新 `CHANGELOG.md`，与本次代码改动一并提交，不允许后补或漏写。
3. 未发布的变更先记录在 `## [Unreleased]` 段落下；正式发版时再迁移到对应版本号与日期的小节。

# Release note guidelines
1. 遵照 Release_Notes_Guidelines.md 里的要求

# 数据获取文档同步（持续维护）
1. 凡涉及数据获取的变化——新增/下线数据源、主备源切换、发布窗口调整、手动补充表（如 `NIFD_DATA` / `_ISM_SUPPLEMENT`）的口径或位置变化、采集脚本结构变化（如新增 `04_*.py`）、CRCL 采集源变化——必须**与代码改动同提交**更新 `docs/data-supplement-runbook.md`（取数手册）；数据源可用性实测结论同步更新 `docs/data-sources-guide.md`。
2. 执行数据补充任务（自动采集或 Agent 手动补充）时，发现文档与现状不符，顺手修正并记入本次提交，不留「文档债」。
3. 目标：哪些表能一键自动更新、哪些需 Agent 按手册跑一次，看手册即可回答；手册过期视为缺陷。

# Behavioral guidelines
## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

