# Power Monitor

## 配置指南

1. 在 **Settings → Secrets and variables → Actions** 中添加：
   - `POWER_MONITOR_MID`
2. 新建一个 Issue 用于接收提醒，例如标题“Power Monitor 日报”。
3. 在同一页面的 **Repository variables** 里添加变量
   `POWER_MONITOR_NOTIFY_ISSUE`，填写 Issue 的编号。

每天将在八点执行。

- 在 Job Summary 中会显示每日电费情况。
- 如果设置了 `POWER_MONITOR_NOTIFY_ISSUE`，使用 `GITHUB_TOKEN` 自动在该 Issue
  下发布评论，从而触发 GitHub 邮件通知。
