# 🤖 glm-quota-check — 智谱 Coding Plan 配额查询 for Hermes

为 **Hermes Agent** 用户打造的智谱 GLM Coding Plan 配额查询工具。

一句话查询，实时展示 Token 用量、MCP 调用次数、重置倒计时。

## ✨ 效果预览

```
╔══════════════════════════════════════════╗
║     🤖 智谱 Coding Plan 配额报告        ║
╚══════════════════════════════════════════╝

  📋 套餐等级：🥉 Lite（体验版）
  🕐 查询时间：2026-06-15 00:21:30 CST
  ─────────────────────────────────────────

  ┌─ 🔌 MCP 调用次数 ─────────────────────┐
  │ 📌 每1月，上限 100 次
  │
  │ 🟢 █████░░░░░░░░░░░░░░░ 25%
  │
  │ ✅ 已用 25 次 ｜ 剩余 75 次
  │ 📈 ✅ 余量充足
  │
  │ 🔍 分项明细：
  │    · 🔍 搜索增强：20 次
  │    · 🌐 网页阅读：5 次
  │    · 📖 深度阅读：0 次
  │ 🔄 重置时间：06月22日 14:58
  │ ⏱️ 7 天 14 小时
  └────────────────────────────────────────┘

  ┌─ 🧠 Token 用量 ──────────────────────────┐
  │ ⏳ 5 小时滑动窗口
  │
  │ 🟢 █████████░░░░░░░░░░░ 47%
  │
  │ 📈 👍 状态良好，放心使用
  │ 🔄 重置时间：06月15日 01:05
  │ ⏱️ 44 分钟
  └────────────────────────────────────────┘

  💡 提示：Token 窗口在倒计时结束后自动刷新，无需手动操作。
```

## 📋 前置条件

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) 已安装
- 智谱 Coding Plan 订阅（[开通地址](https://open.bigmodel.cn/)）
- `~/.hermes/.env` 中已配置 `GLM_API_KEY`

## 🚀 安装

### 方式一：通过 Hermes Skills 安装（推荐）

```bash
hermes skills install https://github.com/haig/glm-quota-check/blob/main/SKILL.md
```

安装后重启 Hermes 会话即可使用。

### 方式二：手动安装

```bash
git clone https://github.com/haig/glm-quota-check.git ~/glm-quota-check
```

然后在对话中告诉 Hermes：
> 运行 python3 ~/glm-quota-check/glm_quota.py 查看我的智谱配额

## 🎯 使用方法

安装 skill 后，在 Hermes 对话中直接说：

- 「看下 glm 用量」
- 「智谱配额还剩多少」
- 「token 用了多少」
- 「查下我的 coding plan 用量」

Hermes 会自动调用脚本并返回格式化结果。

## 🔧 工作原理

1. 从 `~/.hermes/.env` 读取 `GLM_API_KEY`
2. 调用智谱监控 API：`GET /api/monitor/usage/quota/limit`
3. 解析返回的 `limits` 数组，自适应展示所有窗口
4. 渲染彩色进度条 + 倒计时

### API 响应结构

```json
{
  "code": 200,
  "data": {
    "limits": [
      {"type": "TIME_LIMIT", "unit": 5, "number": 1, "usage": 100, ...},
      {"type": "TOKENS_LIMIT", "unit": 3, "number": 5, "percentage": 43, ...}
    ],
    "level": "lite"
  },
  "success": true
}
```

- `TOKENS_LIMIT` — Token 滑动窗口（unit=3: 小时，unit=6: 周）
- `TIME_LIMIT` — MCP 月度调用次数（unit=5: 月）
- `level` — 套餐等级（lite / standard / pro / max / team）

不同套餐返回的窗口数量不同（如 lite 只有 5h 窗口，更高套餐有 5h + 7d），脚本自适应展示。

## ⚠️ 错误处理

脚本覆盖以下错误场景，每个都提供清晰的中文提示和修复建议：

| 场景 | 提示 |
|------|------|
| `.env` 文件不存在 | 提示运行 `hermes setup` |
| `GLM_API_KEY` 未配置 | 提示获取地址和配置方法 |
| Key 为空或格式可疑 | 提示检查或重新获取 |
| 认证失败（401） | 提示检查 Key 来源是否为 Coding Plan |
| 权限不足（403） | 提示确认 Coding Plan 是否开通 |
| 请求频率限制（429） | 提示稍后重试 |
| 网络超时 / 连接失败 | 提示检查网络 |
| 服务器异常（5xx） | 提示稍后重试 |
| 订阅过期 / limits 为空 | 提示登录平台确认 |

## 📁 项目结构

```
glm-quota-check/
├── SKILL.md          # Hermes skill 定义
├── glm_quota.py      # 主脚本（零依赖，纯 Python 标准库）
├── README.md         # 本文件
└── LICENSE           # MIT
```

## 🙏 致谢

本项目的灵感来自知乎上的一篇文章：[智谱用户福音：ClaudeCode中实时显示 API 配额的状态栏](https://zhuanlan.zhihu.com/p/2029208610895405621)，作者 [@Dark易草离](https://www.zhihu.com/people/Dark-yi-cao-li)。

文章介绍了如何为 Claude Code 编写自定义状态栏，实时显示智谱 Coding Plan 的 Token 配额和调用次数。读到这篇文章后，我们想到 Hermes Agent 的用户同样面临配额管理的需求 —— 写着写着突然配额用完、不清楚 5 小时窗口还剩多少 Token，这些痛点是相通的。

不同的是，Hermes Agent 的使用场景更多是对话式的（CLI / 即时通讯平台），不需要常驻状态栏。因此我们简化了思路：不嵌入界面，而是做成一个可随时调用的查询命令，配合 Hermes 的 Skill 机制，用户一句话就能查看配额全貌。

感谢原作者开源了配额查询的 API 端点和数据解析思路，项目仓库：[Darkycl/claude-code-glm-statusline](https://github.com/Darkycl/claude-code-glm-statusline)

## 📜 License

MIT
