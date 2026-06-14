#!/usr/bin/env python3
"""查询智谱 Coding Plan 配额使用情况。

从 ~/.hermes/.env 读取 GLM_API_KEY，调用智谱监控 API，
返回 Token 滑动窗口用量、MCP 月度调用次数、重置倒计时。

自适应：API 返回几条 limit 就展示几条，不假设窗口数量。
有的套餐只有 5h 窗口，有的同时有 5h 和 7d 窗口。

灵感来源：https://zhuanlan.zhihu.com/p/2029208610895405621
原始项目：https://github.com/Darkycl/claude-code-glm-statusline
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ── 常量 ──
CST = timezone(timedelta(hours=8))  # 北京时间
API_URL = "https://open.bigmodel.cn/api/monitor/usage/quota/limit"
API_TIMEOUT = 10  # 秒

# 套餐等级中文名
LEVEL_NAMES = {
    "lite": "🥉 Lite（体验版）",
    "standard": "🥈 Standard（标准版）",
    "pro": "🥇 Pro（专业版）",
    "max": "💎 Max（旗舰版）",
    "team": "🏢 Team（团队版）",
}

# 模型名称映射
MODEL_NAMES = {
    "search-prime": "🔍 搜索增强",
    "web-reader": "🌐 网页阅读",
    "zread": "📖 深度阅读",
}


# ══════════════════════════════════════════════════════════════
#  错误处理
# ══════════════════════════════════════════════════════════════

class QuotaError(Exception):
    """配额查询错误，带用户友好的提示。"""
    pass


def get_api_key():
    """从 Hermes ~/.hermes/.env 读取 GLM_API_KEY。

    可能抛出 QuotaError，包含具体原因和修复建议。
    """
    env_path = os.path.expanduser("~/.hermes/.env")

    # 1. 文件不存在
    if not os.path.exists(env_path):
        raise QuotaError(
            f"❌ 找不到配置文件\n\n"
            f"   路径：{env_path}\n"
            f"   原因：Hermes 配置目录不存在\n"
            f"   建议：确认 Hermes 已正确安装，运行 hermes setup 完成初始化"
        )

    # 2. 读取文件内容
    try:
        with open(env_path) as f:
            lines = f.readlines()
    except PermissionError:
        raise QuotaError(
            f"❌ 配置文件无读取权限\n\n"
            f"   路径：{env_path}\n"
            f"   建议：chmod 600 {env_path}"
        )

    # 3. 查找 GLM_API_KEY
    raw_key = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("GLM_API_KEY=") and not stripped.startswith("#"):
            raw_key = stripped.split("=", 1)[1].strip()
            break

    if raw_key is None:
        raise QuotaError(
            f"❌ 未找到 GLM_API_KEY\n\n"
            f"   路径：{env_path}\n"
            f"   原因：配置文件中没有 GLM_API_KEY 这一行\n"
            f"   建议：\n"
            f"     1. 登录智谱开放平台获取 API Key\n"
            f"        https://open.bigmodel.cn/usercenter/apikeys\n"
            f"     2. 在 {env_path} 中添加：\n"
            f"        GLM_API_KEY=你的API密钥"
        )

    # 4. key 为空
    if not raw_key:
        raise QuotaError(
            f"❌ GLM_API_KEY 为空\n\n"
            f"   路径：{env_path}\n"
            f"   原因：配置文件中 GLM_API_KEY= 后面没有值\n"
            f"   建议：填入有效的智谱 API Key"
        )

    # 5. key 明显太短（正常 key 至少 20 字符）
    if len(raw_key) < 20:
        raise QuotaError(
            f"❌ GLM_API_KEY 格式可疑\n\n"
            f"   路径：{env_path}\n"
            f"   原因：API Key 长度异常（{len(raw_key)} 字符，通常应 > 20 字符）\n"
            f"   建议：请检查是否复制完整，或重新获取 API Key\n"
            f"         https://open.bigmodel.cn/usercenter/apikeys"
        )

    return raw_key


def fetch_quota(api_key):
    """调用智谱监控 API，返回 (limits, level)。

    可能抛出 QuotaError，包含具体 HTTP 错误信息和修复建议。
    """
    req = urllib.request.Request(API_URL, headers={
        "Authorization": api_key,
        "Accept-Language": "en-US,en",
        "Content-Type": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        # HTTP 错误码
        code = e.code
        if code == 401:
            raise QuotaError(
                f"❌ 认证失败（HTTP 401）\n\n"
                f"   原因：API Key 无效或已过期\n"
                f"   建议：\n"
                f"     1. 检查 ~/.hermes/.env 中的 GLM_API_KEY 是否正确\n"
                f"     2. 确认 Key 来源是 Coding Plan 订阅，非普通 API Key\n"
                f"     3. 重新获取：https://open.bigmodel.cn/usercenter/apikeys"
            )
        elif code == 403:
            raise QuotaError(
                f"❌ 权限不足（HTTP 403）\n\n"
                f"   原因：该 API Key 可能没有 Coding Plan 配额查询权限\n"
                f"   建议：\n"
                f"     1. 确认账号已开通 Coding Plan\n"
                f"     2. 确认使用的是 Coding Plan 对应的 API Key"
            )
        elif code == 429:
            raise QuotaError(
                f"❌ 请求过于频繁（HTTP 429）\n\n"
                f"   原因：触发了速率限制\n"
                f"   建议：稍等几分钟后重试"
            )
        elif code >= 500:
            raise QuotaError(
                f"❌ 智谱服务器异常（HTTP {code}）\n\n"
                f"   原因：智谱平台服务端错误\n"
                f"   建议：稍后重试，或查看智谱开放平台公告"
            )
        else:
            raise QuotaError(
                f"❌ 请求失败（HTTP {code}）\n\n"
                f"   建议：请稍后重试，或检查网络连接"
            )
    except urllib.error.URLError as e:
        # 网络层错误（DNS、超时、连接拒绝等）
        if "timeout" in str(e).lower() or isinstance(e.reason, TimeoutError):
            raise QuotaError(
                f"❌ 请求超时（{API_TIMEOUT}s）\n\n"
                f"   原因：连接智谱服务器超时\n"
                f"   建议：\n"
                f"     1. 检查网络连接\n"
                f"     2. 确认能访问 open.bigmodel.cn\n"
                f"     3. 稍后重试"
            )
        else:
            raise QuotaError(
                f"❌ 网络错误\n\n"
                f"   详情：{e.reason}\n"
                f"   建议：\n"
                f"     1. 检查网络连接是否正常\n"
                f"     2. 确认防火墙未拦截 open.bigmodel.cn\n"
                f"     3. 稍后重试"
            )
    except TimeoutError:
        raise QuotaError(
            f"❌ 请求超时（{API_TIMEOUT}s）\n\n"
            f"   原因：连接智谱服务器超时\n"
            f"   建议：检查网络连接后重试"
        )

    # 解析 JSON
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        raise QuotaError(
            f"❌ 响应解析失败\n\n"
            f"   原因：API 返回的不是有效的 JSON 数据\n"
            f"   建议：可能是智谱平台临时故障，请稍后重试"
        )

    # 检查 API 业务状态
    if not data.get("success"):
        msg = data.get("msg", "未知错误")
        code = data.get("code", "?")
        raise QuotaError(
            f"❌ API 返回错误\n\n"
            f"   错误码：{code}\n"
            f"   详情：{msg}\n"
            f"   建议：请稍后重试，或检查 API Key 是否有效"
        )

    d = data.get("data")
    if d is None:
        raise QuotaError(
            f"❌ API 返回数据异常\n\n"
            f"   原因：响应中没有 data 字段\n"
            f"   建议：可能是智谱平台临时故障，请稍后重试"
        )

    limits = d.get("limits")
    if not limits:
        raise QuotaError(
            f"❌ 未获取到配额数据\n\n"
            f"   原因：API 返回的 limits 列表为空\n"
            f"   可能原因：\n"
            f"     1. Coding Plan 订阅已过期\n"
            f"     2. 账号当前没有有效的配额限制\n"
            f"   建议：登录智谱开放平台确认订阅状态\n"
            f"         https://open.bigmodel.cn"
        )

    return limits, d.get("level", "unknown")


# ══════════════════════════════════════════════════════════════
#  格式化辅助
# ══════════════════════════════════════════════════════════════

def format_remaining(reset_ts_ms):
    """毫秒时间戳 → 倒计时"""
    if not reset_ts_ms:
        return "未知"
    diff = reset_ts_ms / 1000 - datetime.now(timezone.utc).timestamp()
    if diff <= 0:
        return "🔄 已重置"
    total_min = int(diff // 60)
    if total_min < 60:
        return f"⏱️ {total_min} 分钟"
    h = total_min // 60
    m = total_min % 60
    if h < 24:
        return f"⏱️ {h} 小时 {m} 分钟"
    d = h // 24
    rh = h % 24
    return f"⏱️ {d} 天 {rh} 小时"

def format_reset_time(reset_ts_ms):
    """毫秒时间戳 → 北京时间"""
    if not reset_ts_ms:
        return "未知"
    dt = datetime.fromtimestamp(reset_ts_ms / 1000, tz=CST)
    return dt.strftime("%m月%d日 %H:%M")

def pct_emoji(pct):
    """根据百分比返回状态 emoji"""
    pct = int(round(pct or 0))
    if pct >= 90:
        return "🔴"
    elif pct >= 70:
        return "🟠"
    elif pct >= 50:
        return "🟡"
    elif pct >= 20:
        return "🟢"
    else:
        return "⚪"

def progress_bar(pct, width=20):
    """百分比 → 彩色进度条（ANSI 颜色）"""
    pct = int(round(pct or 0))
    filled = pct * width // 100
    bar = "█" * filled + "░" * (width - filled)

    # ANSI 颜色
    R = "\033[0m"
    if pct >= 90:
        color = "\033[1;31m"  # 加粗红
    elif pct >= 70:
        color = "\033[31m"    # 红
    elif pct >= 50:
        color = "\033[33m"    # 黄
    else:
        color = "\033[32m"    # 绿

    return f"{color}{bar}{R} {pct}%"

def status_text(pct, kind="token"):
    """根据用量生成一句状态描述"""
    pct = int(round(pct or 0))
    if kind == "token":
        if pct >= 90:
            return "⚠️ 配额快满了，悠着点用！"
        elif pct >= 70:
            return "😮 用了不少了，注意控制节奏"
        elif pct >= 50:
            return "😌 使用过半，状态正常"
        elif pct >= 20:
            return "👍 状态良好，放心使用"
        else:
            return "✨ 刚重置不久，尽情发挥~"
    else:
        if pct >= 90:
            return "⚠️ 调用次数快用完了！"
        elif pct >= 50:
            return "📊 使用过半"
        else:
            return "✅ 余量充足"


# ══════════════════════════════════════════════════════════════
#  主函数
# ══════════════════════════════════════════════════════════════

def main():
    # ── 获取 API Key ──
    try:
        api_key = get_api_key()
    except QuotaError as e:
        print(f"\n{e}\n")
        sys.exit(1)

    # ── 查询配额 ──
    try:
        limits, level = fetch_quota(api_key)
    except QuotaError as e:
        print(f"\n{e}\n")
        sys.exit(1)

    # ── 渲染输出 ──
    level_display = LEVEL_NAMES.get(level, f"🎭 {level}")
    now_cst = datetime.now(tz=CST).strftime("%Y-%m-%d %H:%M:%S")

    print()
    print("╔══════════════════════════════════════════╗")
    print("║     🤖 智谱 Coding Plan 配额报告        ║")
    print("╚══════════════════════════════════════════╝")
    print()
    print(f"  📋 套餐等级：{level_display}")
    print(f"  🕐 查询时间：{now_cst} CST")
    print(f"  ─────────────────────────────────────────")
    print()

    for lim in limits:
        ltype = lim.get("type", "")
        unit = lim.get("unit", 0)
        pct = lim.get("percentage", 0)
        reset_ms = lim.get("nextResetTime")
        number = lim.get("number", 0)

        if ltype == "TOKENS_LIMIT":
            # Token 滑动窗口
            if unit == 3:
                window = f"⏳ {number} 小时滑动窗口"
            elif unit == 6:
                window = f"📅 {number} 周滑动窗口（{number*7} 天）"
            else:
                window = f"📊 窗口 (unit={unit})"

            print(f"  ┌─ 🧠 Token 用量 ──────────────────────────┐")
            print(f"  │ {window}")
            print(f"  │")
            print(f"  │ {pct_emoji(pct)} {progress_bar(pct)}")
            print(f"  │")
            print(f"  │ 📈 {status_text(pct, 'token')}")
            print(f"  │ 🔄 重置时间：{format_reset_time(reset_ms)}")
            print(f"  │ {format_remaining(reset_ms)}")
            print(f"  └────────────────────────────────────────┘")
            print()

        elif ltype == "TIME_LIMIT":
            # MCP 月度调用次数限制
            UNIT_NAMES = {3: "小时", 4: "天", 5: "月", 6: "周"}
            unit_name = UNIT_NAMES.get(unit, f"unit={unit}")
            window = f"📌 每{number}{unit_name}"
            usage = lim.get("usage", 0)
            current = lim.get("currentValue", 0)
            remaining = lim.get("remaining", 0)
            details = lim.get("usageDetails", [])

            call_pct = (current / usage * 100) if usage else 0

            print(f"  ┌─ 🔌 MCP 调用次数 ─────────────────────┐")
            print(f"  │ {window}，上限 {usage} 次")
            print(f"  │")
            print(f"  │ {pct_emoji(call_pct)} {progress_bar(call_pct)}")
            print(f"  │")
            print(f"  │ ✅ 已用 {current} 次 ｜ 剩余 {remaining} 次")
            print(f"  │ 📈 {status_text(call_pct, 'call')}")
            if details:
                print(f"  │")
                print(f"  │ 🔍 分项明细：")
                for d in details:
                    model = MODEL_NAMES.get(d.get("modelCode", ""), f"⚙️ {d.get('modelCode', '?')}")
                    print(f"  │    · {model}：{d.get('usage', 0)} 次")
            print(f"  │ 🔄 重置时间：{format_reset_time(reset_ms)}")
            print(f"  │ {format_remaining(reset_ms)}")
            print(f"  └────────────────────────────────────────┘")
            print()

        else:
            # 未知类型
            print(f"  ┌─ ❓ 未知限制类型 ({ltype}) ────────────┐")
            print(f"  │ {json.dumps(lim, ensure_ascii=False)}")
            print(f"  └────────────────────────────────────────┘")
            print()

    print("  💡 提示：Token 窗口在倒计时结束后自动刷新，无需手动操作。")
    print()


if __name__ == "__main__":
    main()
