# -*- coding: utf-8 -*-
"""
脚本名称: 科普中国 v2.0
作者：YSJohnson
功能：科普中国APP每日自动完成签到、浏览、分享、点赞任务 自动抽奖 随机1-5现金红包或不中

积分可以拿来兑换或者抽奖
积分想拿来兑换的可以关闭抽奖功能 在下面的配置区 lottery_enabled 改成 False 默认开启

【注意】
要先完成科普人员信息认证 单位地址就写街道办 实名要是本人的！
脚本某些功能若失效 请先去github查看是否有新版本 若没有 再提issue反馈
有其他功能需求也欢迎提issue

【变量配置说明】
1. 账号变量 (kpzg):
   格式：手机号#密码
   多账号用 & 或换行隔开
   示例：18888888888#123456

更新记录:
v2.0:
- [Add] 增加抽奖功能
"""

import os
import time
import json
import hashlib
import random
import uuid
import requests
import urllib.parse
import signal
import threading
import logging
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

STOP_EVENT = threading.Event()

CONFIG = {
    "name": "科普中国",
    "variable": "kpzg",
    "proxyApi": os.environ.get("kpzg_proxy", ""),
    "concurrency": 3,  # 并发数量
    "apiHost": "api.kepuchina.cn",
    "lottery_enabled": True,  # 是否开启抽奖功能，True=开启，False=关闭
    "lottery_threshold": 500
}


def signal_handler(signum, frame):
    logger.info("接收到停止信号，正在退出...")
    STOP_EVENT.set()


def md5_encrypt(text):
    md5_1 = hashlib.md5(text.encode('utf-8')).hexdigest()
    md5_2 = hashlib.md5(md5_1.encode('utf-8')).hexdigest()
    return md5_2


def get_timestamp():
    return str(int(time.time()))


def random_string(length, chars="abcdef0123456789"):
    return ''.join(random.choice(chars) for _ in range(length))


def random_pattern(pattern, charset="abcdef0123456789"):
    res = ""
    for char in pattern:
        if char == "x":
            res += random.choice(charset)
        elif char == "X":
            res += random.choice(charset).upper()
        else:
            res += char
    return res


def wait(milliseconds):
    STOP_EVENT.wait(milliseconds / 1000.0)


def generate_random_user_agent():
    """生成随机的User-Agent，保持与抽奖接口相同的格式"""
    # 随机Android版本 (13-16)
    android_version = random.choice(["13", "14", "15", "16"])

    # 随机设备型号
    device_models = [
        "PLC110", "PFM110", "PLE110", "PLM110", "PCC110",
        "PBV110", "PAV110", "PNX110", "PKV110", "PHH110"
    ]
    device_model = random.choice(device_models)

    # 随机Build号
    build_parts = [random_string(4, "0123456789ABCDEF") for _ in range(3)]
    build_id = ".".join(build_parts)

    # 随机Chrome版本 (130-145)
    chrome_main = random.randint(130, 145)
    chrome_sub = random.randint(1, 99)
    chrome_build = random.randint(1, 999)

    # App版本固定为10.1.0
    app_version = "10.1.0"

    user_agent = (f"Mozilla/5.0 (Linux; Android {android_version}; {device_model} Build/{build_id}; wv) "
                  f"AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/{chrome_main}.{chrome_sub}.{chrome_build} "
                  f"Mobile Safari/537.36 scienceChina/{app_version}")

    return user_agent


class KepuUser:
    def __init__(self, user_str, index):
        self.index = index
        parts = user_str.split("#")
        self.ck = parts[0]
        self.password = parts[1] if len(parts) > 1 else ""

        self.masked_ck = self.ck[:3] + "****" + self.ck[-4:] if len(self.ck) >= 11 else self.ck

        self.ud = random_pattern("XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX")
        self.model = random_string(12, "NIWADINRL921847Y2190")
        self.v = "9.1.0"
        self.token = ""
        self.proxy_ip = ""
        self.tm = ""

        self.headers = {
            "Host": CONFIG["apiHost"],
            "Connection": "keep-alive",
            "Accept": "*/*",
            "User-Agent": "ScienceChinaRel/8.6.0 (iPhone; iOS 15.4.1; Scale/3.00)",
            "Accept-Language": "zh-Hans-CN;q=1",
        }

        self.article_list = []
        self.nickname = ""
        self.total_score = 0
        self.money = 0
        self.login_status = False
        self.lottery_result = ""

    def log(self, message):
        logger.info(f"[{self.masked_ck}] {message}")

    def get_proxy(self):
        if not CONFIG["proxyApi"] or STOP_EVENT.is_set():
            return
        try:
            res = requests.get(CONFIG["proxyApi"], timeout=10)
            text = res.text.strip()
            if text and any(char.isdigit() for char in text) and "." in text:
                self.proxy_ip = text.split("\n")[0].strip()
                self.log(f"获取代理IP成功: {self.proxy_ip}")
        except Exception:
            self.log("获取代理IP失败，将使用直连")

    def sign(self, path, params=None):
        if params is None:
            params = {}

        sign_str = ""

        if path == '/account/login':
            sign_str = (f"app_v={self.v}&channel=huawei&country_code=86&from=android&log_channel=huawei&"
                        f"log_model={self.model}&log_system=android10&login_device={self.model}&login_from=4&"
                        f"mobile={self.ck}&password={self.password}&path=/account/login&requestTime=0&sdk_int=29&"
                        f"source=3&system_v=10&timestamp={self.tm}&unique_identifier={self.ud}&uuid={self.ud}&"
                        f"v={self.v}&secretkey=PC3937!@*&YZF")
        else:
            sign_str = (f"from=android&log_channel=huawei&log_model={self.model}&log_system=android10&"
                        f"path={path}&requestTime=0&sdk_int=29&timestamp={self.tm}&token={self.token}&"
                        f"unique_identifier={self.ud}&uuid={self.ud}&v={self.v}&secretkey=PC3937!@*&YZF")

        return md5_encrypt(sign_str)

    def get_url_params(self, sn):
        return (f"?timestamp={self.tm}&v={self.v}&from=android&log_model={self.model}&log_channel=huawei&"
                f"log_system=android10&sdk_int=29&unique_identifier={self.ud}&uuid={self.ud}&"
                f"token={self.token}&sn={sn}")

    def http_request(self, method, url, headers, body=None):
        if STOP_EVENT.is_set(): return {}

        proxies = None
        if self.proxy_ip:
            proxies = {
                "http": f"http://{self.proxy_ip}",
                "https": f"http://{self.proxy_ip}"
            }

        req_headers = headers.copy()
        if method.upper() == 'POST' and 'Content-Type' not in req_headers:
            req_headers['Content-Type'] = 'application/x-www-form-urlencoded'

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=req_headers,
                data=body,
                proxies=proxies,
                timeout=20
            )
            try:
                return response.json()
            except:
                return {"msg": response.text}

        except Exception:
            if self.proxy_ip and not STOP_EVENT.is_set():
                self.log("请求失败，正在更换代理重试...")
                self.get_proxy()
                if self.proxy_ip:
                    proxies = {"http": f"http://{self.proxy_ip}", "https": f"http://{self.proxy_ip}"}
                try:
                    response = requests.request(
                        method=method,
                        url=url,
                        headers=req_headers,
                        data=body,
                        proxies=proxies,
                        timeout=20
                    )
                    try:
                        return response.json()
                    except:
                        return {"msg": response.text}
                except:
                    return {"msg": "请求失败"}
            else:
                return {"msg": "请求失败"}

    def login(self):
        if STOP_EVENT.is_set(): return False
        try:
            self.tm = get_timestamp()
            sign_str = self.sign('/account/login')
            url_params = (f"?timestamp={self.tm}&v={self.v}&from=android&log_model={self.model}&"
                          f"log_channel=huawei&log_system=android10&sdk_int=29&unique_identifier={self.ud}&"
                          f"uuid={self.ud}&sn={sign_str}")

            body = (f"unique_identifier={self.ud}&requestTime=0&app_v={self.v}&channel=huawei&country_code=86&"
                    f"login_device={urllib.parse.quote(self.model)}&login_from=4&mobile={self.ck}&"
                    f"password={self.password}&source=3&system_v=10")

            url = f"https://{CONFIG['apiHost']}/account/login{url_params}"
            result = self.http_request("post", url, self.headers, body)

            if result.get("msg") == "成功":
                self.token = result.get("data", {}).get("token")
                self.login_status = True
                self.log("登录成功")
                return True
            else:
                self.log(f"登录失败: {result.get('msg')}")
                return False
        except Exception as e:
            self.log(f"登录异常: {e}")
            return False

    def get_user_info(self, silent=False):
        if STOP_EVENT.is_set(): return False
        try:
            self.tm = get_timestamp()
            path = "/user/userinfo"
            sn = self.sign(path)
            url = f"https://{CONFIG['apiHost']}{path}{self.get_url_params(sn)}"
            body = f"unique_identifier={self.ud}&token={self.token}&requestTime=0"

            result = self.http_request("post", url, self.headers, body)

            data = result.get("data", {})
            if data and data.get("nickname"):
                self.nickname = data.get("nickname")
                self.total_score = int(data.get("total_score", 0))
                self.money = int(data.get("current_money", 0))
                if not silent:
                    self.log(f"用户: {self.nickname} | 当前积分: {self.total_score}")
                return True
            return False
        except Exception as e:
            return False

    def sign_in(self):
        if STOP_EVENT.is_set(): return
        try:
            self.tm = get_timestamp()
            path = "/Signin/addSignIn"
            sn = self.sign(path)
            url = f"https://{CONFIG['apiHost']}{path}{self.get_url_params(sn)}"
            body = f"unique_identifier={self.ud}&token={self.token}&requestTime=0"

            result = self.http_request("post", url, self.headers, body)
            if result.get("msg") == "成功":
                self.log("签到成功")
            else:
                self.log(f"签到结果: {result.get('msg')}")
        except Exception:
            pass

    def do_task(self):
        if STOP_EVENT.is_set(): return
        try:
            self.tm = get_timestamp()
            path = "/score/scoretask"
            sn = self.sign(path)
            url = f"https://{CONFIG['apiHost']}{path}{self.get_url_params(sn)}"
            body = f"unique_identifier={self.ud}&token={self.token}&requestTime=0"

            result = self.http_request("post", url, self.headers, body)

            if result.get("msg") == "成功" and result.get("data", {}).get("list"):
                all_tasks = result["data"]["list"]
                daily_list = next((x["list"] for x in all_tasks if x.get("name") == "日常奖励"), None)

                if not daily_list:
                    return

                self.fetch_article_list()

                for task in daily_list:
                    if STOP_EVENT.is_set(): break

                    if task.get("redirect_status") == 0:
                        continue

                    limit = int(task.get("limit", 0))
                    score = int(task.get("score", 0))

                    if task.get("title") == "浏览内容":
                        count = int((limit - score) / 5)
                        self.run_loop_task(count, 'read')
                    elif task.get("title") == "分享内容":
                        count = int((limit - score) / 10)
                        self.run_loop_task(count, 'share')
                    elif task.get("title") == "点赞内容":
                        count = int((limit - score) / 2)
                        self.run_loop_task(count, 'like')
        except Exception:
            self.log("获取任务列表失败")

    def fetch_article_list(self):
        if STOP_EVENT.is_set(): return
        try:
            path = "/channel/channellist"
            sn = self.sign(path)
            url = f"https://{CONFIG['apiHost']}{path}{self.get_url_params(sn)}"
            body = f"unique_identifier={self.ud}&token={self.token}&requestTime=0"

            ch_res = self.http_request("post", url, self.headers, body)

            channel_id = "0"
            if ch_res.get("data") and ch_res["data"].get("my_channel"):
                target = random.choice(ch_res["data"]["my_channel"])
                channel_id = target.get("at_id", "0")

            self.tm = get_timestamp()
            idx_sign_str = (f"at_id={channel_id}&from=android&log_channel=huawei&log_model={self.model}&"
                            f"log_system=android10&page=1&path=/index/index&requestTime={self.tm}&sdk_int=29&"
                            f"size=10&timestamp={self.tm}&token={self.token}&unique_identifier={self.ud}&"
                            f"uuid={self.ud}&v={self.v}&secretkey=PC3937!@*&YZF")
            idx_sn = md5_encrypt(idx_sign_str)

            idx_url = f"https://{CONFIG['apiHost']}/index/index{self.get_url_params(idx_sn)}"
            idx_body = (f"unique_identifier={self.ud}&token={self.token}&requestTime={self.tm}&"
                        f"at_id={channel_id}&page=1&size=10")

            res = self.http_request("post", idx_url, self.headers, idx_body)

            if res.get("data") and res["data"].get("list"):
                self.article_list = [x for x in res["data"]["list"] if x.get("type") == 2 or x.get("type") == "2"]
                self.log(f"获取到文章 {len(self.article_list)} 篇")
        except Exception:
            self.log("获取文章列表失败")
            self.article_list = []

    def run_loop_task(self, times, type_name):
        if not self.article_list:
            return

        count = 0
        for article in self.article_list:
            if STOP_EVENT.is_set(): break
            if count >= times:
                break

            self.tm = get_timestamp()
            article_id = article.get("id")

            try:
                if type_name == 'read':
                    sign_str = (f"ar_id={article_id}&from=android&is_thumb=0&log_channel=huawei&"
                                f"log_model={self.model}&log_system=android10&path=/scientificwebsite/articleinfo&"
                                f"requestTime=0&sdk_int=29&timestamp={self.tm}&token={self.token}&"
                                f"unique_identifier={self.ud}&uuid={self.ud}&v={self.v}&secretkey=PC3937!@*&YZF")
                    sn = md5_encrypt(sign_str)
                    url = f"https://{CONFIG['apiHost']}/scientificwebsite/articleinfo{self.get_url_params(sn)}"
                    body = (f"unique_identifier={self.ud}&token={self.token}&requestTime=0&"
                            f"ar_id={article_id}&is_thumb=0")
                    self.http_request("post", url, self.headers, body)
                    self.log(f"文章 {count + 1}/{times}: 完成")

                elif type_name == 'share':
                    sign_str = (f"from=android&id={article_id}&log_channel=huawei&log_model={self.model}&"
                                f"log_system=android10&path=/share/shareaddscore&requestTime=0&sdk_int=29&"
                                f"timestamp={self.tm}&token={self.token}&type=4&unique_identifier={self.ud}&"
                                f"uuid={self.ud}&v={self.v}&secretkey=PC3937!@*&YZF")
                    sn = md5_encrypt(sign_str)
                    url = f"https://{CONFIG['apiHost']}/share/shareaddscore{self.get_url_params(sn)}"
                    body = (f"unique_identifier={self.ud}&token={self.token}&requestTime=0&"
                            f"id={article_id}&type=4&")
                    res = self.http_request("post", url, self.headers, body)
                    self.log(f"文章 {count + 1}/{times}: 分享成功")
                    wait(5000)

                elif type_name == 'like':
                    drop_str = (f"ar_id={article_id}&from=android&log_channel=huawei&log_model={self.model}&"
                                f"log_system=android10&path=/like/droppraise&requestTime=0&sdk_int=29&"
                                f"timestamp={self.tm}&token={self.token}&type=4&unique_identifier={self.ud}&"
                                f"uuid={self.ud}&v={self.v}&secretkey=PC3937!@*&YZF")
                    drop_sn = md5_encrypt(drop_str)
                    url_drop = f"https://{CONFIG['apiHost']}/like/droppraise{self.get_url_params(drop_sn)}"
                    body_drop = (f"unique_identifier={self.ud}&token={self.token}&requestTime=0&"
                                 f"ar_id={article_id}&type=4&unique_identifier={self.ud}")
                    self.http_request("post", url_drop, self.headers, body_drop)
                    self.log(f"文章 {count + 1}/{times}: 取消点赞成功")
                    wait(2000)

                    add_str = (f"ar_id={article_id}&from=android&log_channel=huawei&log_model={self.model}&"
                               f"log_system=android10&path=/like/addpraise&requestTime=0&sdk_int=29&"
                               f"timestamp={self.tm}&token={self.token}&type=4&unique_identifier={self.ud}&"
                               f"uuid={self.ud}&v={self.v}&secretkey=PC3937!@*&YZF")
                    add_sn = md5_encrypt(add_str)
                    url_add = f"https://{CONFIG['apiHost']}/like/addpraise{self.get_url_params(add_sn)}"
                    body_add = (f"unique_identifier={self.ud}&token={self.token}&requestTime=0&"
                                f"ar_id={article_id}&type=4&unique_identifier={self.ud}")
                    res = self.http_request("post", url_add, self.headers, body_add)
                    self.log(f"文章 {count + 1}/{times}: 点赞成功")

                count += 1
                wait(2500)
            except Exception as e:
                pass

    def lottery_draw(self):
        """抽奖功能"""
        if STOP_EVENT.is_set(): return
        if not CONFIG.get("lottery_enabled", False):
            return

        threshold = CONFIG.get("lottery_threshold", 500)
        if self.total_score < threshold:
            self.log(f"当前积分 {self.total_score} < {threshold}，不满足抽奖条件")
            return

        try:
            self.tm = get_timestamp()
            url = "https://h5.kepuchina.cn/lotterydraw/lotterydraw"
            body = f"lottery_id=102&token={self.token}"

            random_ua = generate_random_user_agent()

            lottery_headers = {
                "Host": "h5.kepuchina.cn",
                "Connection": "keep-alive",
                "Accept": "*/*",
                "User-Agent": random_ua,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://h5.kepuchina.cn",
                "Referer": "https://h5.kepuchina.cn/prize/prize?lottery_id=102"
            }

            result = self.http_request("post", url, lottery_headers, body)

            if result.get("msg") == "成功" or result.get("code") == 0:
                data = result.get("data", {})
                lottery_name = data.get("name", "未知")
                self.lottery_result = lottery_name
                self.total_score = int(data.get("score", self.total_score))
                self.log(f"抽奖结果: {lottery_name}，当前积分: {self.total_score}")
            else:
                self.log(f"抽奖失败: {result.get('msg')}")
        except Exception as e:
            self.log(f"抽奖异常: {e}")

    def start(self):
        self.get_proxy()
        if self.login():
            self.get_user_info()
            self.sign_in()
            self.do_task()
            self.get_user_info(silent=True)
            self.lottery_draw()
            self.log(f"抽奖完成，剩余积分: {self.total_score}")


def run_user(user):
    try:
        user.start()
    except Exception as e:
        logger.info(f"[{user.masked_ck}] 账号运行出错: {e}")


if __name__ == "__main__":
    logger.info("=================================================")
    logger.info("          科普中国    | 作者: YSJohnson         ")
    logger.info("代码发布地址：https://github.com/YSJohnson/QingLongScripts-YSJ")
    logger.info("=================================================")

    if not os.environ.get(CONFIG["variable"]):
        logger.info(f"未检测到环境变量 {CONFIG['variable']}")
        exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    env_data = [x for x in os.environ[CONFIG["variable"]].split("\n") if x]
    if len(env_data) == 1 and "&" in env_data[0]:
        env_data = env_data[0].split("&")

    logger.info(f"成功加载 {len(env_data)} 个账号，并发线程数: {CONFIG['concurrency']}")

    if CONFIG["proxyApi"]:
        logger.info("已启用代理 API")

    user_list = [KepuUser(data, i + 1) for i, data in enumerate(env_data)]

    with ThreadPoolExecutor(max_workers=CONFIG["concurrency"]) as executor:
        futures = [executor.submit(run_user, user) for user in user_list]

        while not STOP_EVENT.is_set():
            if all(f.done() for f in futures):
                break
            time.sleep(0.5)

    logger.info("所有账号任务执行完毕，准备推送...")

    push_contents = []
    for user in user_list:
        if user.login_status:
            if user.lottery_result:
                push_contents.append(f"账号: {user.masked_ck}\n抽奖结果：{user.lottery_result}\n当前积分：{user.total_score}")
            else:
                push_contents.append(f"账号: {user.masked_ck}\n积分不足 未进行抽奖\n当前积分：{user.total_score}")

    if push_contents:
        notify_content = "\n\n--------------------\n\n".join(push_contents)
        QLAPI.notify("科普中国", notify_content)

    logger.info(">>> ✅ 所有任务执行完毕 <<<")
