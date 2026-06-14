#!/usr/bin/env python3
"""GLM API 调用封装，带自动重试 + 指数退避。

解决 Coding Plan API 瞬时频率限制（429）问题。

用法：
    from glm_api import glm_chat, glm_vision_judge

    # 文本对话
    result = glm_chat(messages=[...], model="glm-5.1")

    # 视觉审核（JSON 结构化输出）
    result = glm_vision_judge(image_url, "请评价这张图片...")
"""
import json
import urllib.request
import urllib.error
import os
import time
import socket


# ── 配置 ──
GLM_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
GLM_ENDPOINT = GLM_BASE_URL + "/chat/completions"
MAX_RETRIES = 6
INITIAL_BACKOFF = 10  # 首次重试等待秒数（GLM RPM 限制通常需要等更长）
MAX_BACKOFF = 180     # 最大等待秒数
DEFAULT_TIMEOUT = 60  # 默认请求超时秒数（视觉模型需要更长）


def _get_api_key():
    """从 ~/.hermes/.env 读取 GLM_API_KEY"""
    with open(os.path.expanduser("~/.hermes/.env")) as f:
        for line in f:
            s = line.strip()
            if "GLM_API_KEY" in s and not s.startswith("#") and len(s) > 15:
                return s.split("=", 1)[1].strip()
    raise RuntimeError("GLM_API_KEY not found in ~/.hermes/.env")


def _do_request(payload, timeout=DEFAULT_TIMEOUT):
    """发起一次 HTTP 请求，返回解析后的 JSON。

    对 429 / 5xx / 超时 自动重试（指数退避）。
    对 4xx（非 429）直接抛出，不重试。
    """
    api_key = _get_api_key()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    data = json.dumps(payload).encode()
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(GLM_ENDPOINT, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())

        except urllib.error.HTTPError as e:
            code = e.code
            last_error = e
            body = ""
            try:
                body = e.read().decode()
            except Exception:
                pass

            # 解析业务错误码
            biz_code = None
            try:
                biz = json.loads(body)
                biz_code = biz.get("error", {}).get("code", "")
            except Exception:
                pass

            # 根据官方文档分类处理：
            #   1302 = 并发限制 → 指数退避重试
            #   1305 = 平台过载 → 更长退避重试
            #   1308 = 用量窗口耗尽 → 不重试（需等 5h 窗口重置）
            #   1313 = 公平使用策略违规 → 不重试
            #   429（无业务码）→ 通用重试
            #   5xx → 通用重试
            #   400 含限速关键词 → 重试（GLM 不稳定时偶发）
            NO_RETRY_CODES = ["1308", "1313"]
            should_retry = False
            extra_backoff = 0

            if biz_code in NO_RETRY_CODES:
                should_retry = False
            elif biz_code == "1305":
                # 平台过载 → 拉长退避
                should_retry = True
                extra_backoff = 20
            elif biz_code == "1210" and any(k in body for k in ["图片", "image", "解析"]):
                # GLM 拉取外部图片 URL 偶发失败 → 重试（design.md 坑点2）
                should_retry = True
            elif code == 429 or code >= 500:
                should_retry = True
            elif code == 400 and any(k in body for k in ["速率", "频率", "rate", "limit", "1302"]):
                should_retry = True

            if should_retry:
                backoff = min((INITIAL_BACKOFF + extra_backoff) * (2 ** (attempt - 1)), MAX_BACKOFF)
                retry_after = e.headers.get("Retry-After")
                if retry_after:
                    try:
                        backoff = min(int(retry_after), MAX_BACKOFF)
                    except ValueError:
                        pass
                if attempt < MAX_RETRIES:
                    print(f"  ⚠️ HTTP {code} (biz={biz_code})，第 {attempt}/{MAX_RETRIES} 次重试，等待 {backoff}s...")
                    time.sleep(backoff)
                    continue

            # 不可重试的错误 → 直接抛出，附带详细信息
            raise RuntimeError(f"GLM API 不可重试错误: HTTP {code} (biz={biz_code}): {body[:500]}")

        except (socket.timeout, TimeoutError) as e:
            last_error = e
            backoff = min(INITIAL_BACKOFF * (2 ** (attempt - 1)), MAX_BACKOFF)
            if attempt < MAX_RETRIES:
                print(f"  ⚠️ 请求超时，第 {attempt}/{MAX_RETRIES} 次重试，等待 {backoff}s...")
                time.sleep(backoff)
                # 重试时加大 timeout
                continue
            raise

        except urllib.error.URLError as e:
            last_error = e
            if "timeout" in str(e).lower():
                backoff = min(INITIAL_BACKOFF * (2 ** (attempt - 1)), MAX_BACKOFF)
                if attempt < MAX_RETRIES:
                    print(f"  ⚠️ 网络超时，第 {attempt}/{MAX_RETRIES} 次重试，等待 {backoff}s...")
                    time.sleep(backoff)
                    continue
            raise

    # 所有重试用完
    raise last_error


def glm_chat(messages, model="glm-5.1", max_tokens=4096,
             thinking=None, response_format=None, timeout=DEFAULT_TIMEOUT):
    """GLM 文本对话。

    Args:
        messages: OpenAI 格式的消息列表
        model: 模型名（glm-5.1, glm-4.6v-flash 等）
        max_tokens: 最大输出 token 数
        thinking: {"type": "enabled"/"disabled"} 或 None
        response_format: {"type": "json_object"} 或 None
        timeout: 请求超时秒数

    Returns:
        API 返回的完整 JSON 响应
    """
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if thinking:
        payload["thinking"] = thinking
    if response_format:
        payload["response_format"] = response_format

    return _do_request(payload, timeout=timeout)


def glm_vision_judge(image_url, instruction, model="glm-4.6v-flash",
                     max_tokens=500, json_output=True, timeout=DEFAULT_TIMEOUT):
    """GLM 视觉审核：看图 + 指令 → 结构化评价。

    自动处理 URL 拉取失败：先试 URL，失败后下载转 base64 重试。
    """
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }],
        "max_tokens": max_tokens,
        "thinking": {"type": "disabled"},
    }
    if json_output:
        payload["response_format"] = {"type": "json_object"}

    try:
        result = _do_request(payload, timeout=timeout)
        content = result["choices"][0]["message"]["content"]
        if json_output:
            return json.loads(content)
        return content
    except RuntimeError as e:
        # URL 方式失败 → 尝试下载图片转 base64
        if "1210" in str(e) or "400" in str(e):
            print("  ⚠️ URL 图片传递失败，尝试 base64 fallback...")
            import base64 as _b64

            # 判断是 URL 还是已经是 data URL
            if image_url.startswith("data:"):
                raise  # 已经是 base64 还失败，不重试

            # 下载图片
            try:
                import urllib.request as _ur
                with _ur.urlopen(image_url, timeout=30) as resp:
                    img_data = resp.read()
                # 检测 content-type
                ct = resp.headers.get("Content-Type", "image/png")
                if "jpeg" in ct or "jpg" in ct:
                    mime = "image/jpeg"
                else:
                    mime = "image/png"
                b64 = _b64.b64encode(img_data).decode()
                data_url = f"data:{mime};base64,{b64}"

                payload["messages"][0]["content"][1] = {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                }
                result = _do_request(payload, timeout=timeout)
                content = result["choices"][0]["message"]["content"]
                if json_output:
                    return json.loads(content)
                return content
            except Exception:
                raise
        raise


# ── 测试入口 ──
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python3 glm_api.py <image_url>")
        print("     python3 glm_api.py --text '你好'")
        sys.exit(1)

    if sys.argv[1] == "--text":
        msg = sys.argv[2] if len(sys.argv) > 2 else "你好"
        resp = glm_chat(
            messages=[{"role": "user", "content": msg}],
            model="glm-5.1",
            max_tokens=100,
        )
        print(resp["choices"][0]["message"]["content"])
    else:
        image_url = sys.argv[1]
        result = glm_vision_judge(
            image_url,
            "请评价这张图片的质量，1-5分，列出包含的元素和任何问题。用JSON输出："
            "{overall_quality, elements, issues, suggestions}",
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
