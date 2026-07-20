#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
南网在线自动签到脚本 v2.3（通知修复版）
青龙面板适用
"""

import os
import sys
import json
import time
import requests
import subprocess
from datetime import datetime

BASE_URL = "https://95598.csg.cn"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/20A362 Ariver/1.0.15 NWZX/Portal Nebula WK WK RVKType(0) NebulaX/1.0.0"
TASK_ID = "654165b1z56x1bq1"

def send_notify(title, content):
    """调用青龙通知"""
    print(f"\n   [正在发送通知] {title}")

    # 方式1: 写入临时JS文件执行
    try:
        notify_dir = "/ql/data/scripts"
        if not os.path.exists(os.path.join(notify_dir, "sendNotify.js")):
            notify_dir = "/ql/scripts"

        notify_path = os.path.join(notify_dir, "sendNotify.js")
        if os.path.exists(notify_path):
            tmp_js = os.path.join(notify_dir, "_nanwang_notify_tmp.js")

            # 使用字符串拼接避免引号冲突
            lines = [
                'const { sendNotify } = require("./sendNotify");',
                '(async () => {',
                '    await sendNotify("' + title + '", "' + content + '");',
                '    process.exit(0);',
                '})();',
            ]
            with open(tmp_js, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            result = subprocess.run(
                ["node", tmp_js],
                cwd=notify_dir,
                capture_output=True,
                text=True,
                timeout=30
            )

            try:
                os.remove(tmp_js)
            except:
                pass

            if result.returncode == 0:
                print(f"   [通知发送成功] 通过 sendNotify.js")
                return
            else:
                print(f"   [sendNotify 错误] {result.stderr[:200]}")
        else:
            print(f"   [sendNotify.js 不存在] {notify_path}")
    except Exception as e:
        print(f"   [sendNotify 异常] {e}")

    # 方式2: Python notify 模块
    try:
        sys.path.insert(0, "/ql/data/scripts")
        sys.path.insert(0, "/ql/scripts")
        from notify import send
        send(title, content)
        print(f"   [通知发送成功] 通过 Python notify")
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"   [Python notify 异常] {e}")

    # 方式3: 兜底打印
    print(f"\n{'='*60}")
    print(f"[通知内容 - 请检查青龙通知配置]")
    print(f"标题: {title}")
    print(f"内容: {content}")
    print(f"{'='*60}")

class NanWangSign:
    def __init__(self, token, cookie=None):
        self.token = token
        self.cookie = cookie or f"CAMSID={token}; bfsResponseHandleType=0"
        self.session = requests.Session()
        self.headers = {
            "Host": "95598.csg.cn",
            "Accept": "*/*",
            "Accept-Charset": "utf-8",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "User-Agent": UA,
            "need-crypto": "0",
            "x-auth-token": token,
            "Origin": "https://95598.csg.cn",
            "Referer": "https://0000000000000141.95598.csg.cn/0000000000000141/1.0.3.1/index.html",
        }

    def _request(self, method, url, json_data=None):
        try:
            self.headers["Cookie"] = self.cookie
            if method.upper() == "GET":
                resp = self.session.get(url, headers=self.headers, timeout=15)
            else:
                resp = self.session.post(url, headers=self.headers, json=json_data, timeout=15)

            set_cookie = resp.headers.get("Set-Cookie", "")
            if "CAMSID=" in set_cookie:
                new_camsid = set_cookie.split("CAMSID=")[1].split(";")[0]
                self.cookie = f"CAMSID={new_camsid}; bfsResponseHandleType=0"
                print(f"   [Cookie更新] CAMSID={new_camsid}")

            return resp.json()
        except Exception as e:
            return {"sta": "-1", "message": f"请求异常: {e}"}

    def check_account(self):
        url = f"{BASE_URL}/mp/w2/szfw-points-txhsj/account/checkAccountIsExist"
        data = self._request("POST", url, {})
        if data.get("sta") == "00":
            info = data.get("data", {})
            return {
                "userId": info.get("userId", ""),
                "grantPoints": info.get("grantPoints", 0),
                "freezePoints": info.get("freezePoints", 0),
            }
        return None

    def get_sign_list(self):
        url = f"{BASE_URL}/mp/w2/szfw-points-txhsj/taskInfo/taskSignList"
        data = self._request("POST", url, {})
        if data.get("sta") == "00":
            info = data.get("data", {})
            return {
                "finished": info.get("taskFinishStatus", "0") == "1",
                "singCount": info.get("singCount", 0),
                "signGainPoints": info.get("signGainPoints", 1),
            }
        return None

    def do_sign(self):
        url = f"{BASE_URL}/mp/w2/szfw-points-txhsj/taskInfo/signOperate"
        return self._request("POST", url, {"taskId": TASK_ID, "thisGainPoints": 1})

def main():
    print("=" * 60)
    print("     南网在线自动签到脚本 v2.3")
    print("=" * 60)

    token = os.environ.get("NANWANG_TOKEN", "").strip()
    cookie = os.environ.get("NANWANG_COOKIE", "").strip()
    today = datetime.now().strftime("%Y-%m-%d")

    if not token and not cookie:
        msg = "缺少环境变量！请配置 NANWANG_TOKEN 或 NANWANG_COOKIE"
        print(msg)
        send_notify("南网在线签到失败", msg)
        sys.exit(1)

    if not token and cookie and "CAMSID=" in cookie:
        token = cookie.split("CAMSID=")[1].split(";")[0]
        print(f"[从Cookie提取Token] {token}")

    signer = NanWangSign(token, cookie)

    print("\n[1/3] 查询账户信息...")
    account = signer.check_account()
    if not account:
        msg = "Token失效或查询账户失败，请更新 NANWANG_TOKEN"
        print(msg)
        send_notify("南网在线签到失败", msg)
        sys.exit(1)

    print(f"   用户ID: {account['userId']}")
    print(f"   可用积分: {account['grantPoints']}")
    print(f"   冻结积分: {account['freezePoints']}")

    print("\n[2/3] 查询签到状态...")
    sign_info = signer.get_sign_list()
    if not sign_info:
        msg = "获取签到状态失败"
        print(msg)
        send_notify("南网在线签到失败", msg)
        sys.exit(1)

    if sign_info["finished"]:
        print(f"   今日({today})已签到，连续 {sign_info['singCount']} 天")
        account = signer.check_account()
        points = account["grantPoints"] if account else "未知"

        title = f"南网在线签到 [{today}]"
        content = f"签到状态: 今日已签到\n连续签到: {sign_info['singCount']} 天\n当前积分: {points}"
        print(f"\n{content}")
        send_notify(title, content)
        sys.exit(0)

    print(f"\n[3/3] 执行签到...")
    result = signer.do_sign()

    if result.get("sta") == "00":
        gain_points = result.get("data", 1)
        print(f"   签到成功，获得 {gain_points} 积分")

        time.sleep(1)
        account = signer.check_account()
        points = account["grantPoints"] if account else "未知"

        title = f"南网在线签到成功 [{today}]"
        content = f"签到结果: 成功\n获得积分: {gain_points}\n当前积分: {points}"
        print(f"\n{content}")
        send_notify(title, content)
        sys.exit(0)
    else:
        msg = f"签到失败: {result.get('message', '未知错误')}"
        print(msg)
        send_notify(f"南网在线签到失败 [{today}]", msg)
        sys.exit(1)

if __name__ == "__main__":
    main()
