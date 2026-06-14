---
name: glm-quota-check
description: "查询智谱 Coding Plan (GLM) 的配额使用情况：Token 用量、MCP 调用次数、重置倒计时。用户说「看下glm用量」「智谱配额」等时触发。"
version: 1.2.0
author: haig
license: MIT
platforms: [cli, gateway]
metadata:
  hermes:
    tags: [glm, zhipu, quota, monitoring, coding-plan]
---

# GLM 配额查询

查询智谱 Coding Plan 的实时配额使用情况。

## 触发条件

当用户询问以下内容时使用：
- "看下glm用量"、"智谱配额"、"glm还剩多少"
- "token用了多少"、"配额查询"、"用量查询"
- 任何关于智谱/GLM API 使用量、配额、限额的问题

## 执行方法

```bash
python3 ~/glm-tokens/glm_quota.py
```

无需额外参数。脚本从 `~/.hermes/.env` 读取 `GLM_API_KEY`，调用智谱监控 API。

## 重要：输出呈现规则

脚本的输出已经是精心格式化的（框线、emoji、彩色进度条、状态提示）。
**必须原样展示脚本的完整输出，不要摘要、不要精简、不要用自己的话重新组织。**
你可以额外补充一两句观察（如和上次对比的变化），但脚本本身的格式化输出不得删减。

## 输出内容

- 📋 套餐等级（Lite/Standard/Pro 等，带 emoji 徽章）
- 🕐 查询时间（北京时间）
- 🧠 Token 用量 — 滑动窗口（5h，高级套餐还有 7d），ANSI 彩色进度条 + 重置倒计时
- 🔌 MCP 调用次数 — 每月上限、已用/剩余、分模型明细
- 📈 根据用量自动生成的状态提示

自适应：API 返回几条 limit 就展示几条，不假设窗口数量。

## 错误处理

脚本覆盖了完整的错误链路（文件缺失、key 无效、网络超时、HTTP 错误、订阅过期等），
每个错误都输出清晰的中文提示和修复建议。遇到错误时直接将脚本的错误输出展示给用户。

## API 技术细节

- 端点: `GET https://open.bigmodel.cn/api/monitor/usage/quota/limit`
- 认证: `Authorization: <raw_api_key>`（裸 key，非 Bearer）
- 这是智谱监控平台唯一的配额查询端点；套餐到期时间等信息 API 不提供
- key 来源是 `~/.hermes/.env` 中的 `GLM_API_KEY`（Coding Plan key）
