#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
旧衣客（jyk.scjyx.com）自动签到脚本
包含：每日签到 + 补签 + 看广告签到（循环）
环境变量 JYK_TOKENS：
    多个账号用 & 分隔，每个账号用 token#备注 形式
    例如：token1#备注1&token2#备注2
    自动去除 Bearer 前缀
"""

import json
import os
import random
import sys
import time
import urllib.request
from datetime import datetime

# ---------- 编码 & 日志 ----------
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def log(msg, end="\n"):
    print(msg, end=end, flush=True)

# ---------- 常量 ----------
PUSH_PLUS_TOKEN = os.environ.get("PUSH_PLUS_TOKEN", "").strip()

JYK_BASE_URL = "https://jyk.scjyx.com"
PAYCONFIG_ID = "2"
TIMEOUT = 15

AD_VIEW_MIN, AD_VIEW_MAX = 45, 60
AD_GAP_MIN, AD_GAP_MAX = 20, 40
ACCOUNT_GAP_MIN, ACCOUNT_GAP_MAX = 5, 15

# ---------- 解析 JYK_TOKENS ----------
def normalize_token(token):
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def parse_tokens(raw):
    if not raw:
        return []
    parts = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for item in line.split("&"):
            item = item.strip()
            if not item or item.startswith("#"):
                continue
            if "#" in item:
                token, remark = item.split("#", 1)
                token = normalize_token(token)
                remark = remark.strip()
            else:
                token = normalize_token(item)
                remark = ""
            if token:
                parts.append((token, remark or f"账号{len(parts) + 1}"))
    return parts


TOKENS_RAW = os.environ.get("JYK_TOKENS", "").strip()
ACCOUNTS = parse_tokens(TOKENS_RAW)
if not ACCOUNTS:
    log("❌ 未检测到有效的 JYK_TOKENS 环境变量，请配置后再运行")
    log("示例: token1#备注1&token2#备注2")
    sys.exit(1)

log(f"✅ 已加载 {len(ACCOUNTS)} 个账号")

# ---------- User-Agent ----------
def get_user_agent():
    return ("Mozilla/5.0 (Linux; Android 13; SM-G9980 Build/TP1A.220624.014; wv) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/150.0.7871.100 "
            "Mobile Safari/537.36 XWEB/1500000 MMWEBSDK/20260000 MMWEBID/3000 "
            "MicroMessenger/8.0.76.3140(0x28004C31) WeChat/arm64 NetType/WIFI "
            "Language/zh_CN ABI/arm64 MiniProgramEnv/android")

COMMON_HEADERS = {
    "Content-Type": "application/json",
    "Charset": "utf-8",
    "Referer": "https://servicewechat.com/wx3f0209cc35a953a4/80/page-frame.html",
    "User-Agent": get_user_agent(),
}

# ---------- 请求 API ----------
def api_request(token, path, method="GET", body=None):
    url = JYK_BASE_URL + path
    headers = dict(COMMON_HEADERS)
    if token:
        headers["Authorization"] = "Bearer " + token.strip()
    headers["x-payconfig-id"] = PAYCONFIG_ID
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"errno": -1, "message": str(e)}

# ---------- Token 校验 ----------
def get_valid_token(token, account_label):
    log(f"🔍 [{account_label}] 正在校验 token...")
    resp = api_request(token, "/api/user/getInfo")
    if resp.get("errno") == 0:
        log(f"✅ [{account_label}] token 有效")
        return token

    message = resp.get("message") or "未知错误"
    log(f"❌ [{account_label}] token 无效或已过期，请重新获取: {message}")
    return None

# ---------- 签到相关 ----------
def checkin_home(token):
    return api_request(token, "/api/checkin/home")

def checkin_sign(token, sign_type=1):
    """普通签到/补签，sign_type=1 普通签到，2 看广告签到（需先取 ad_token）"""
    return api_request(token, "/api/checkin/sign", method="POST", body={"sign_type": sign_type})

def ad_prepare(token):
    return api_request(token, "/api/checkin/ad/prepare", method="POST", body={})

def ad_sign(token, ad_token):
    return api_request(token, "/api/checkin/ad/sign", method="POST", body={"ad_token": ad_token})

# ---------- 普通签到 & 补签 ----------
def do_checkin(token, account_label):
    """
    普通签到 + 补签（若今日已签则检查是否可补签）
    返回日志列表
    """
    logs = []
    log(f"📅 [{account_label}] 开始查询签到状态...")
    home = checkin_home(token)
    if home.get("errno") != 0:
        logs.append(f"❌ 查询签到状态失败: {home.get('message')}")
        return logs
    data = home.get("data") or {}
    if not data.get("enabled"):
        logs.append("⚠️ 签到功能未启用")
        return logs

    integral = data.get("integral", "?")
    streak = data.get("streak_days", 0)

    # 今日未签到
    if not data.get("today_signed"):
        if not data.get("can_sign"):
            logs.append(f"ℹ️ 当前不可签到，积分 {integral}，连续 {streak} 天")
            return logs
        log(f"✍️ [{account_label}] 正在签到...")
        time.sleep(1)
        sign = checkin_sign(token, sign_type=1)
        if sign.get("errno") != 0:
            logs.append(f"❌ 签到失败: {sign.get('message')}")
            return logs
        sdata = sign.get("data") or {}
        reward = sdata.get("reward") or {}
        snapshot = sdata.get("snapshot") or {}
        amount = reward.get("amount", "?")
        reward_text = reward.get("reward_type_text", "积分")
        tip = sdata.get("success_tip", "")
        new_streak = snapshot.get("streak_days", streak)
        logs.append(f"✅ {tip} 获得 +{amount}{reward_text}，连续 {new_streak} 天")
    else:
        # 今日已签，尝试补签
        if data.get("can_makeup") and data.get("makeup_remain_today", 0) > 0:
            log(f"🩹 [{account_label}] 检测到可补签，正在补签...")
            time.sleep(1)
            sign = checkin_sign(token, sign_type=1)  # 补签也走普通签到接口
            if sign.get("errno") != 0:
                logs.append(f"❌ 补签失败: {sign.get('message')}")
                return logs
            sdata = sign.get("data") or {}
            reward = sdata.get("reward") or {}
            snapshot = sdata.get("snapshot") or {}
            amount = reward.get("amount", "?")
            reward_text = reward.get("reward_type_text", "积分")
            tip = sdata.get("success_tip", "")
            new_streak = snapshot.get("streak_days", streak)
            logs.append(f"✅ 补签成功，{tip} 获得 +{amount}{reward_text}，连续 {new_streak} 天")
        else:
            logs.append(f"ℹ️ 今日已签到，积分 {integral}，连续 {streak} 天")

    return logs

def do_ad_checkin(token, account_label, max_times=None):
    """
    循环看广告签到，直到 need_ad 为 False 或达到 max_times
    """
    logs = []
    done = 0
    while max_times is None or done < max_times:
        prep = ad_prepare(token)
        if prep.get("errno") != 0:
            logs.append(f"❌ 广告签到准备失败: {prep.get('message')}")
            break
        data = prep.get("data") or {}
        if not data.get("need_ad") or not data.get("ad_enabled"):
            logs.append("ℹ️ 广告签到已完成或未开启")
            break
        view_secs = random.randint(AD_VIEW_MIN, AD_VIEW_MAX)
        log(f"📺 [{account_label}] 模拟观看广告 ({view_secs}s)...")
        time.sleep(view_secs)
        res = ad_sign(token, data.get("ad_token", ""))
        if res.get("errno") != 0:
            fail = (res.get("data") or {}).get("fail_tip") or res.get("message", "")
            logs.append(f"❌ 广告签到失败: {fail}")
            break
        sdata = res.get("data") or {}
        reward = sdata.get("reward") or {}
        snapshot = sdata.get("snapshot") or {}
        done += 1
        logs.append(
            f"✅ 广告签到 第{reward.get('times_index', '?')}次"
            f" +{reward.get('amount', '?')}{reward.get('reward_type_text', '积分')}"
            f"，今日 {snapshot.get('today_count', '?')}/{snapshot.get('daily_limit', '?')} 次"
        )
        today = snapshot.get("today_count", 0)
        limit = snapshot.get("daily_limit", 0)
        if limit and today >= limit:
            logs.append("ℹ️ 今日广告签到已达上限")
            break
        if max_times is not None and done >= max_times:
            break
        gap = random.randint(AD_GAP_MIN, AD_GAP_MAX)
        log(f"⏳ [{account_label}] 等待 {gap}s 后进行下一次广告签到...")
        time.sleep(gap)
    if done == 0 and not logs:
        logs.append("ℹ️ 广告签到未执行")
    return logs

# ---------- 通知 ----------
def send_notify(title, content):
    if PUSH_PLUS_TOKEN:
        try:
            data = json.dumps({"token": PUSH_PLUS_TOKEN, "title": title, "content": content, "template": "txt"}).encode("utf-8")
            req = urllib.request.Request("https://www.pushplus.plus/send", data=data,
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass
            log("✅ PushPlus 推送成功")
        except Exception as e:
            log(f"❌ PushPlus 推送失败: {e}")
    else:
        try:
            from notify import send
            send(title, content)
        except Exception:
            pass

def account_succeeded(logs):
    return any(m in line for line in logs for m in ("✅", "ℹ️", "⚠️", "🩹"))

# ---------- 主流程 ----------
def main():
    max_times = None
    raw_times = os.environ.get("JYK_AD_TIMES", "").strip()
    if raw_times:
        try:
            max_times = int(raw_times)
        except ValueError:
            log("⚠️ JYK_AD_TIMES 不是有效整数，已忽略")

    results = []
    for idx, (token, remark) in enumerate(ACCOUNTS, 1):
        prefix = f"账号{idx} ({remark})"
        log(f"\n===== 开始执行 - {prefix} =====")
        token = get_valid_token(token, prefix)
        if not token:
            results.append({"remark": remark, "success": False, "error": "token 无效或已过期，请重新获取"})
            continue

        # 1. 普通签到 + 补签
        logs = do_checkin(token, prefix)

        # 2. 广告签到循环
        logs += do_ad_checkin(token, prefix, max_times=max_times)

        for line in logs:
            log(f"[{prefix}] {line}")
        success = account_succeeded(logs)
        results.append({
            "remark": remark,
            "success": success,
            "logs": logs,
            "error": "" if success else "签到未成功"
        })

        if idx < len(ACCOUNTS):
            gap = random.randint(ACCOUNT_GAP_MIN, ACCOUNT_GAP_MAX)
            log(f"[{prefix}] ⏳ 等待 {gap} 秒后切换下一个账号...")
            time.sleep(gap)

    # 汇总
    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    lines = [
        "📊 旧衣客签到结果汇总",
        "────────────────────────────",
        f"✅ 成功: {success_count}  |  ❌ 失败: {fail_count}",
        f"🕒 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "────────────────────────────"
    ]
    for r in results:
        icon = "✅" if r["success"] else "❌"
        lines.append(f"\n{icon} {r['remark']}")
        if r["success"]:
            for line in r["logs"]:
                lines.append("  " + line)
        else:
            lines.append(f"  失败: {r['error']}")
    summary = "\n".join(lines)
    log("\n" + summary)
    send_notify("📊 旧衣客签到结果汇总", summary)

if __name__ == "__main__":
    main()
