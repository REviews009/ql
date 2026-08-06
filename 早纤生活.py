# -*- coding: utf-8 -*-
"""
脚本名称： 早纤生活
作者: YSJohnson

变量名: ZXSH
变量值: 备注#手机号#密码 或 备注#token 或 token
       多账号 换行 或 & 分隔 或新建同名变量
功能：自动看广、领取福利
"""

import os
import time
import hashlib
import random
import requests
import signal
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 全局停止事件
STOP_EVENT = threading.Event()

class Config:
    BASE_URL = "http://gw.yyzqsh.cn/api/web"
    SALT = "aB3xK9pQ2sL8mZ1nR7tY4uW0vJ5cH6gF"
    FIXED_WATCH_SEC = 100
    TIMEOUT = 30
    MAX_WORKERS = 5  # 最大并发线程数

def signal_handler(signum, frame):
    """捕获停止信号"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [WARN] 🛑 接收到终止信号，正在停止所有任务...")
    STOP_EVENT.set()

class Utils:
    @staticmethod
    def md5(text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest().upper()

    @staticmethod
    def md5_lower(text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    @staticmethod
    def generate_random_string(length: int = 8) -> str:
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        return ''.join(random.choice(chars) for _ in range(length))

    @staticmethod
    def generate_sign(timestamp: str, random_number: str, video_id: str) -> str:
        raw_str = f"randomNumber={random_number}&timeStamp={timestamp}&videoId={video_id}&{Config.SALT}="
        return Utils.md5_lower(raw_str)

    @staticmethod
    def parse_env_list(env_str: str) -> list:
        if not env_str:
            return []
        normalized = env_str.replace('\r', '').replace('\n', '&')
        return [item.strip() for item in normalized.split('&') if item.strip()]

    @staticmethod
    def get_random_device_info() -> str:
        """生成随机设备信息，降低被检测风险"""
        models = [
            ("Xiaomi", "Mi 10", "umi"), ("Xiaomi", "Redmi K30", "phoenix"),
            ("HUAWEI", "P40 Pro", "ELS-AN00"), ("HUAWEI", "Mate 40", "OCE-AN10"),
            ("Samsung", "Galaxy S21", "SM-G9910"), ("OPPO", "Find X3", "PEEM00"),
            ("VIVO", "X60", "V2046A")
        ]
        brand, model, device = random.choice(models)
        release = random.randint(10, 13)
        return f"MANUFACTURER:{brand},MODEL:{model},DEVICE:{device},VERSION.RELEASE:{release},"

    @staticmethod
    def random_sleep(min_sec=3, max_sec=8):
        """可中断的随机延时"""
        wait_time = random.uniform(min_sec, max_sec)
        STOP_EVENT.wait(wait_time)


class ZXSHRunner:
    def __init__(self):
        self.results = []

    def log(self, content: str, level: str = "INFO", context: str = None):
        context_str = f"[{context}] " if context else ""
        time_str = datetime.now().strftime("%H:%M:%S")
        print(f"[{time_str}] [{level}] {context_str}{content}")

    def _request(self, method: str, path: str, token: str = None, data: dict = None, custom_headers: dict = None,
                 session=None) -> dict:
        if STOP_EVENT.is_set(): return {}

        url = f"{Config.BASE_URL}{path}"
        if session is None:
            session = requests.Session()
            session.headers.update({
                "host": "gw.yyzqsh.cn",
                "platform": "Android",
                "version": "v1.3.0",
                "content-type": "application/json; charset=UTF-8",
                "user-agent": "okhttp/4.10.0"
            })

        headers = session.headers.copy()
        if token:
            headers["authorization"] = token.strip()
        if custom_headers:
            headers.update(custom_headers)

        for attempt in range(3):
            if STOP_EVENT.is_set(): return {}
            try:
                response = session.request(method, url, json=data or {}, headers=headers, timeout=Config.TIMEOUT)
                if response.status_code in [500, 502, 503, 504]:
                    raise requests.RequestException(f"Server Error {response.status_code}")
                return response.json()
            except Exception as e:
                if attempt == 2:
                    raise Exception(f"请求失败(重试3次): {str(e)}")
                STOP_EVENT.wait(2)
        return {}

    def login(self, phone: str, pwd: str, remark: str) -> str:
        if STOP_EVENT.is_set(): return ""
        self.log(f"🚀 正在登录...", "CHECK", remark)
        payload = {"phone": phone, "password": Utils.md5(pwd)}
        res = self._request("POST", "/auth/pwdLogin", data=payload)

        if res.get("code") != 200:
            raise Exception(res.get("message") or "登录失败")

        self.log("✅ 登录成功", "SUCCESS", remark)
        return res["result"]["token"]

    def process_user_task(self, item: str, idx: int) -> dict:
        parts = [p.strip() for p in item.split("#") if p.strip()]
        count = len(parts)

        # 初始化信息
        remark = f"账号{idx + 1}"
        token = ""
        result_entry = {"备注": remark, "类型": "未知", "状态": "❌ 失败", "原因": ""}

        # 1. 登录/解析阶段
        try:
            if count == 2:  # 备注#Token
                remark = parts[0]
                token = parts[1]
                result_entry["类型"] = "Token"
            elif count == 3:  # 备注#手机#密码
                if STOP_EVENT.is_set(): return result_entry
                remark = parts[0]
                token = self.login(parts[1], parts[2], remark)
                result_entry["类型"] = "账号密码"
            elif count == 1:  # 纯Token
                token = parts[0]
                result_entry["类型"] = "Token(无备注)"
            else:
                raise Exception("格式错误")

            result_entry["备注"] = remark

            # 2. 任务执行阶段
            if not token: raise Exception("Token无效")

            # 使用独立Session保持连接复用
            local_session = requests.Session()
            local_session.headers.update({
                "host": "gw.yyzqsh.cn", "platform": "Android",
                "version": "v1.3.0", "content-type": "application/json; charset=UTF-8",
                "user-agent": "okhttp/4.10.0"
            })

            # 随机设备指纹，每个账号一个
            device_info = Utils.get_random_device_info()

            if STOP_EVENT.is_set(): return result_entry

            # 获取信息
            info_res = self._request("POST", "/member/getMemberCenterInfo", token=token, session=local_session)
            if info_res.get("result", {}).get("nickName"):
                # 如果获取到昵称，更新备注
                remark = info_res["result"]["nickName"]
                result_entry["备注"] = remark

            user_data = info_res.get("result", {})
            watched = user_data.get("watchedVideoCount", 0)
            total = user_data.get("videoCount", 0)

            self.log(f"📊 进度: {watched}/{total}", "INFO", remark)

            if watched >= total and total > 0:
                result_entry["状态"] = "✅ 已完成"
                return result_entry

            for i in range(watched, total):
                if STOP_EVENT.is_set(): break # 循环中检查停止信号

                ad_res = self._request("POST", "/member/get/internalAdvertisement", token=token, session=local_session)
                video_id = ad_res.get("result", {}).get("id")
                desc = ad_res.get("result", {}).get("description", "未知")

                if not video_id:
                    self.log("无广告ID，跳过", "WARN", remark)
                    continue

                self.log(f"📺 观看: {desc} ({Config.FIXED_WATCH_SEC}s)", "INFO", remark)
                
                # 关键修改：使用 STOP_EVENT.wait 代替 time.sleep
                if STOP_EVENT.wait(Config.FIXED_WATCH_SEC):
                    self.log("停止等待，准备退出", "WARN", remark)
                    break

                # 提交结果
                ts = str(int(time.time() * 1000))
                nonce = Utils.generate_random_string()
                sign = Utils.generate_sign(ts, nonce, video_id)

                headers = {
                    "timestamp": ts, "randomnumber": nonce, "sign": sign,
                    "phoneinfo": device_info  # 使用随机设备
                }

                unlock_res = self._request("POST", f"/newPeopleUnlock/receiveWelfareNineteen?videoId={video_id}",
                                           token=token, custom_headers=headers, session=local_session)

                if unlock_res.get("code") == 200:
                    contrib = unlock_res.get("result", {}).get("contributionPerVideo", 0)
                    self.log(f"💰 获得 {contrib} 贡献值", "SUCCESS", remark)
                else:
                    self.log(f"❌ 失败: {unlock_res.get('message')}", "WARN", remark)

                if i < total - 1:
                    Utils.random_sleep(3, 8)  # 随机延时

            if STOP_EVENT.is_set():
                result_entry["状态"] = "⭕ 已停止"
            else:
                result_entry["状态"] = "✅ 成功"
            return result_entry

        except Exception as e:
            self.log(f"💥 异常: {str(e)}", "ERROR", remark)
            result_entry["原因"] = str(e)
            return result_entry

    def display_results(self):
        if not self.results: return
        print("\n" + "=" * 30)
        print("       执行结果汇总       ")
        print("=" * 30)
        self.results.sort(key=lambda x: x.get("备注", ""))
        for idx, res in enumerate(self.results):
            print(f"[{idx + 1}] {res.get('备注', '未知')}")
            for k, v in res.items():
                if k != "备注" and v:
                    print(f"    {k}: {v}")
            print("-" * 30)
        print("=" * 30 + "\n")

    def run(self):
        # 注册信号
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        env_data = os.environ.get("ZXSH", "")
        items = Utils.parse_env_list(env_data)
        print("\n=================================================")
        print("          早纤生活 | 作者: YSJohnson         ")
        print("代码发布地址：https://github.com/YSJohnson/QingLongScripts-YSJ")
        print("=================================================\n")

        if not items:
            self.log("❌ 未设置 ZXSH 环境变量", "ERROR")
            return

        self.log(f"==== 启动任务 (并发数: {Config.MAX_WORKERS}, 目标: {len(items)}) ====", "CHECK")

        with ThreadPoolExecutor(max_workers=Config.MAX_WORKERS) as executor:
            futures = {executor.submit(self.process_user_task, item, idx): idx for idx, item in enumerate(items)}


            while not STOP_EVENT.is_set():
                if all(f.done() for f in futures):
                    break
                time.sleep(0.5)

            # 收集结果
            for future in as_completed(futures):
                try:
                    res = future.result()
                    self.results.append(res)
                except Exception as e:
                    self.log(f"线程异常: {e}", "ERROR")

        self.log("==== 所有任务执行完成 ====", "CHECK")
        self.display_results()


if __name__ == "__main__":
    runner = ZXSHRunner()
    runner.run()
