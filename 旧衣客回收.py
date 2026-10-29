#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
旧衣客回收（jyk.scjyx.com）每日自动签到（YYB 版 - 艾瑞风格）
支持普通签到 + 广告签到 + 补签（普通补签 + 广告补签）
"""

import json
import os
import random
import sys
import time
import urllib.request
from datetime import datetime, timedelta

# ---------- 控制台输出编码 & 强制刷新 ----------
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def log(msg, end="\n"):
    print(msg, end=end, flush=True)

# ---------- 配置 ----------
YYB_BASE_URL = os.environ.get("YYB_BASE_URL", "http://192.168.124.100:8000").rstrip("/")
YYB_APP_ID = os.environ.get("YYB_APP_ID", "wx3f0209cc35a953a4")
PUSH_PLUS_TOKEN = os.environ.get("PUSH_PLUS_TOKEN", "").strip()

JYK_BASE_URL = "https://jyk.scjyx.com"
PAYCONFIG_ID = "2"
TIMEOUT = 15

AD_VIEW_MIN, AD_VIEW_MAX = 45, 60
AD_GAP_MIN, AD_GAP_MAX = 20, 40
ACCOUNT_GAP_MIN, ACCOUNT_GAP_MAX = 5, 15

# ---------- 解析 JYK_OPENIDS ----------
def parse_openids(raw):
    if not raw:
        return []
    parts = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        for item in line.split('&'):
            item = item.strip()
            if not item or item.startswith('#'):
                continue
            if '#' in item:
                openid, remark = item.split('#', 1)
                parts.append((openid.strip(), remark.strip() or openid.strip()[:8]))
            else:
                parts.append((item, item[:8]))
    return parts

OPENIDS_RAW = os.environ.get("JYK_OPENIDS", "").strip()
ACCOUNTS = parse_openids(OPENIDS_RAW)
if not ACCOUNTS:
    log("❌ 未配置环境变量 JYK_OPENIDS，请设置（多账号用 & 或换行分隔）")
    log("格式: openid1#备注1&openid2#备注2")
    sys.exit(1)

log(f"✅ 读取到 {len(ACCOUNTS)} 个账号")

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

# ---------- 缓存管理 ----------
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jyk_token_cache.json")

def read_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def write_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def get_cached_token(openid):
    cache = read_cache()
    entry = cache.get(openid)
    if entry and entry.get("token"):
        if entry.get("expires_at"):
            now = datetime.now().timestamp()
            if now > entry["expires_at"]:
                log(f"⏰ [{openid[:8]}] 缓存 token 已过期")
                return None
        return entry["token"]
    return None

def save_cached_token(openid, token, uid, expires_in):
    cache = read_cache()
    cache[openid] = {
        "token": token,
        "uid": uid,
        "expires_at": datetime.now().timestamp() + expires_in,
        "updated_at": datetime.now().isoformat()
    }
    write_cache(cache)

def remove_cached_token(openid):
    cache = read_cache()
    if openid in cache:
        del cache[openid]
        write_cache(cache)
        log(f"🗑️ [{openid[:8]}] 缓存已清除")

# ---------- YYB 接口 ----------
def yyb_request(path, method="GET", body=None):
    url = YYB_BASE_URL + path
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"code": -1, "msg": str(e), "data": None}

def get_code_from_yyb(openid):
    log(f"📡 正在通过 YYB 获取 code (openid: {openid[:8]}...)")
    body = {"ref": openid, "app_id": YYB_APP_ID}
    resp = yyb_request("/wxapp/getCode", method="POST", body=body)
    if resp.get("code") != 0:
        log(f"⚠️ 获取 code 失败 (openid={openid[:8]}): {resp.get('msg')}")
        return None
    data = resp.get("data")
    if not data or not data.get("result"):
        return None
    code = data["result"].get("code")
    log(f"✅ 获取 code 成功")
    return code

# ---------- 旧衣客 API 请求 ----------
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

def login_with_code(code):
    payload = {
        "code": code.strip(),
        "pid": 0,
        "device_info": "ios_iPhone11<iPhone12,1>_iOS17.4_896_414"
    }
    resp = api_request("", "/api/index/get_openid", method="POST", body=payload)
    if resp.get("errno") != 0:
        return None, resp.get("message")
    data = resp.get("data", {})
    token = data.get("access_token")
    uid = data.get("uid")
    expires_in = data.get("expires_in", 2592000)
    if not token:
        return None, "未获取到 access_token"
    return {"token": token, "uid": uid, "expires_in": expires_in}, None

# ---------- Token 获取与刷新 ----------
def get_valid_token(openid):
    cached = get_cached_token(openid)
    if cached:
        log(f"🔑 [{openid[:8]}] 使用缓存 token，验证中...")
        resp = api_request(cached, "/api/user/getInfo")
        if resp.get("errno") == 0:
            log(f"✅ [{openid[:8]}] 缓存 token 有效")
            return cached
        else:
            log(f"🔄 [{openid[:8]}] 缓存 token 失效，重新登录")
            remove_cached_token(openid)
    else:
        log(f"🔄 [{openid[:8]}] 无缓存，准备登录")

    code = get_code_from_yyb(openid)
    if not code:
        return None
    log(f"🔐 [{openid[:8]}] 正在登录旧衣客...")
    result, err = login_with_code(code)
    if not result:
        log(f"❌ [{openid[:8]}] 登录失败: {err}")
        return None
    save_cached_token(openid, result["token"], result["uid"], result["expires_in"])
    log(f"✅ [{openid[:8]}] 登录成功，token 已缓存")
    return result["token"]

# ---------- 签到函数 ----------
def checkin_home(token):
    return api_request(token, "/api/checkin/home")

def checkin_sign(token, sign_type=1):
    """执行签到（普通或补签），sign_type=1普通，2广告（广告需额外ad_token）"""
    return api_request(token, "/api/checkin/sign", method="POST", body={"sign_type": sign_type})

def ad_prepare(token):
    return api_request(token, "/api/checkin/ad/prepare", method="POST", body={})

def ad_sign(token, ad_token):
    return api_request(token, "/api/checkin/ad/sign", method="POST", body={"ad_token": ad_token})

# ---------- 核心签到逻辑（含补签） ----------
def do_checkin(token, openid):
    """
    执行普通签到 + 普通补签（当今日已签且可补签时）
    返回日志列表
    """
    logs = []
    log(f"📋 [{openid[:8]}] 查询签到状态...")
    home = checkin_home(token)
    if home.get("errno") != 0:
        logs.append(f"⚠️ 查询签到状态失败: {home.get('message')}")
        return logs
    data = home.get("data") or {}
    if not data.get("enabled"):
        logs.append("❌ 签到功能未开启")
        return logs

    integral = data.get("integral", "?")
    streak = data.get("streak_days", 0)

    # 处理普通签到（今日未签）
    if not data.get("today_signed"):
        if not data.get("can_sign"):
            logs.append(f"⏭️ 当前不可签到（积分 {integral}，连续 {streak} 天）")
            return logs
        log(f"📝 [{openid[:8]}] 执行签到...")
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
        logs.append(f"🎉 {tip} 奖励 +{amount}{reward_text}，连续 {new_streak} 天")
    else:
        # 今日已签，检查补签
        if data.get("can_makeup") and data.get("makeup_remain_today", 0) > 0:
            log(f"🔁 [{openid[:8]}] 发现可补签，执行普通补签...")
            time.sleep(1)
            sign = checkin_sign(token, sign_type=1)  # 补签也用相同接口
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
            logs.append(f"🔁 补签成功！{tip} 奖励 +{amount}{reward_text}，连续 {new_streak} 天")
        else:
            logs.append(f"✅ 今日已签到，无需重复（积分 {integral}，连续 {streak} 天）")

    return logs

def do_ad_checkin(token, openid, max_times=None):
    """
    广告签到（包括广告补签，只要 need_ad 为 True 就会执行）
    """
    logs = []
    done = 0
    while max_times is None or done < max_times:
        prep = ad_prepare(token)
        if prep.get("errno") != 0:
            logs.append(f"⚠️ 广告签到准备失败: {prep.get('message')}")
            break
        data = prep.get("data") or {}
        if not data.get("need_ad") or not data.get("ad_enabled"):
            logs.append("ℹ️ 广告签到未开启，跳过")
            break
        view_secs = random.randint(AD_VIEW_MIN, AD_VIEW_MAX)
        log(f"📺 [{openid[:8]}] 模拟观看广告 ({view_secs}s)...")
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
            f"📺 广告签到 第{reward.get('times_index', '?')}次"
            f" +{reward.get('amount', '?')}{reward.get('reward_type_text', '积分')}"
            f"（今日 {snapshot.get('today_count', '?')}/{snapshot.get('daily_limit', '?')} 次）"
        )
        today = snapshot.get("today_count", 0)
        limit = snapshot.get("daily_limit", 0)
        if limit and today >= limit:
            logs.append("🏁 今日广告签到次数已满")
            break
        if max_times is not None and done >= max_times:
            break
        gap = random.randint(AD_GAP_MIN, AD_GAP_MAX)
        log(f"⏳ [{openid[:8]}] 等待 {gap}s 后进行下一次广告签到...")
        time.sleep(gap)
    if done == 0 and not logs:
        logs.append("ℹ️ 广告签到未执行")
    return logs

# ---------- 推送 ----------
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
            log(f"⚠️ PushPlus 推送失败: {e}")
    else:
        try:
            from notify import send
            send(title, content)
        except Exception:
            pass

def account_succeeded(logs):
    return any(m in line for line in logs for m in ("🎉", "✅", "📺", "🔁"))

# ---------- 主程序 ----------
def main():
    max_times = None
    raw_times = os.environ.get("JYK_AD_TIMES", "").strip()
    if raw_times:
        try:
            max_times = int(raw_times)
        except ValueError:
            log(f"⚠️ JYK_AD_TIMES 无效，忽略")

    results = []
    for idx, (openid, remark) in enumerate(ACCOUNTS, 1):
        prefix = f"账号{idx} ({remark})"
        log(f"\n===== 旧衣客签到 - {prefix} =====")
        token = get_valid_token(openid)
        if not token:
            results.append({"remark": remark, "success": False, "error": "无法获取有效 token"})
            continue

        # 1. 普通签到 + 普通补签
        logs = do_checkin(token, openid)

        # 2. 广告签到（含广告补签）
        logs += do_ad_checkin(token, openid, max_times=max_times)

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
            log(f"[{prefix}] ⏳ 等待 {gap} 秒后处理下一账号...")
            time.sleep(gap)

    # 汇总推送
    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    lines = [
        "📝 旧衣客签到结果",
        "━━━━━━━━━━━━━━━━━━━━",
        f"✅ 成功: {success_count}  |  ❌ 失败: {fail_count}",
        f"🕒 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "━━━━━━━━━━━━━━━━━━━━"
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
    send_notify("📝 旧衣客签到任务完成", summary)

if __name__ == "__main__":
    main()