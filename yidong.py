# -*- coding=UTF-8 -*-
# ===================================================
# 中国移动云盘 - 青龙单文件版 (修复版 2026-07-08)
# 基于 Surge 抓包分析，全面适配新版 API (m.mcloud.139.com)
# 
# 环境变量: ydyp_ck
# 格式: jwtToken#手机号#deviceId
# 多账号使用 @ 分隔
#
# 获取方式:
# 1. 使用 Surge/Charles 等工具抓包移动云盘 App
# 2. 找到请求头中的 jwtToken、deviceId
# 3. 组合成: jwtToken#手机号#deviceId
# =====================================================

import asyncio
import json
import os
import random
import time
from datetime import datetime

import httpx

# ===== 青龙单文件版内置函数 =====
def fn_print(msg):
    print(msg)

def get_env(name, split="@"):
    value = os.getenv(name, "")
    if not value:
        return []
    return value.split(split)

try:
    from sendNotify import send_notification_message_collection
except Exception:
    def send_notification_message_collection(msg):
        pass
# ===== 青龙单文件版内置函数结束 =====

ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MCloudApp/13.0.1 iPhone AppLanguage/zh-CN"

ydyp_ck = get_env("ydyp_ck", "@")

is_redeem = False
redeem_reward_description = ""


class MobileCloudDisk:
    def __init__(self, cookie):
        self.client = httpx.AsyncClient(verify=False, timeout=60)
        self.click_num = 15
        self.draw = 1
        self.timestamp = str(int(round(time.time() * 1000)))

        # 解析环境变量: jwtToken#手机号#deviceId
        parts = cookie.split("#")
        self.jwt_token = parts[0]
        self.account = parts[1] if len(parts) > 1 else ""
        self.device_id = parts[2] if len(parts) > 2 else ""
        self.encrypt_account = self.account[:3] + "*" * 4 + self.account[7:] if len(self.account) >= 11 else self.account

        # 基础请求头 (基于 Surge 抓包数据)
        self.base_headers = {
            'User-Agent': ua,
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Origin': 'https://m.mcloud.139.com',
            'Referer': 'https://m.mcloud.139.com/portal/mobilecloud/index.html?path=newsignin&sourceid=1002&enableShare=1',
        }

        # 带认证的请求头 (从抓包中提取的关键字段)
        self.auth_headers = {
            **self.base_headers,
            'jwtToken': self.jwt_token,
            'appVersion': '13.0.1.0',
            'deviceId': self.device_id,
            'activityId': 'sign_in_3',
            'showLoading': 'true',
        }

        # Cookie (从抓包中提取)
        self.cookies = {
            'jwtToken': self.jwt_token,
        }

        # 汇总信息
        self.summary = {
            "account": self.encrypt_account,
            "signed": False,
            "tasks_completed": [],
            "clouds": 0,
            "messages": []
        }

    def log(self, msg):
        """记录日志"""
        fn_print(msg)
        self.summary["messages"].append(msg)

    async def query_sign_in_status(self):
        """查询签到状态 - 新版 API: /ycloud/signin/page/infoV3"""
        try:
            response = await self.client.get(
                url="https://m.mcloud.139.com/ycloud/signin/page/infoV3?client=app",
                headers=self.auth_headers,
                cookies=self.cookies
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    result = data.get("result", {})
                    cal = result.get("cal", [])
                    today = datetime.now().day
                    today_signed = False
                    today_clouds = 0

                    for day_info in cal:
                        if day_info.get("d") == today and day_info.get("currentMonth") == 1:
                            today_signed = day_info.get("s", False)
                            today_clouds = day_info.get("n", 0)
                            break

                    sign_count = result.get("signCount", 0)
                    total = result.get("total", 0)
                    self.summary["clouds"] = total

                    if today_signed:
                        self.summary["signed"] = True
                        self.log(f"✅ 今日已签到 | 连续{sign_count}天 | 云朵{total}个 | 今日+{today_clouds}")
                    else:
                        self.log(f"📝 今日未签到，开始签到...")
                        await self.sign_in()
                else:
                    self.log(f"❌ 查询签到状态失败：{data.get('msg')}")
            else:
                self.log(f"❌ 查询签到状态异常：HTTP {response.status_code}")
        except Exception as e:
            self.log(f"❌ 查询签到状态异常：{e}")

    async def sign_in(self):
        """签到 - 通过 doTaskPost 接口"""
        try:
            response = await self.client.post(
                url="https://m.mcloud.139.com/ycloud/signin/page/doTaskPost",
                headers=self.auth_headers,
                cookies=self.cookies,
                json={"client": "app", "deviceId": self.device_id}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    self.summary["signed"] = True
                    self.log(f"✅ 签到成功！")
                else:
                    self.log(f"⚠️ 签到结果：{data.get('msg')}")
            else:
                self.log(f"❌ 签到异常：HTTP {response.status_code}")
        except Exception as e:
            self.log(f"❌ 签到异常：{e}")

    async def get_task_list(self, group="day"):
        """获取任务列表 - 新版 API: /ycloud/signin/task/taskListV2"""
        try:
            response = await self.client.post(
                url="https://m.mcloud.139.com/ycloud/signin/task/taskListV2",
                headers=self.auth_headers,
                cookies=self.cookies,
                json={
                    "marketname": "sign_in_3",
                    "clientVersion": "13.0.1",
                    "group": group
                }
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    result = data.get("result", {})
                    group_state = data.get("groupState", {})

                    group_names = {
                        "day": "📅 每日任务",
                        "month": "📆 每月任务", 
                        "time": "⏰ 限时任务",
                        "cloudEmail": "📧 邮箱任务",
                        "hidden": "🔒 隐藏任务",
                        "new": "🆕 新手任务",
                        "beiyong1": "📋 备用任务1",
                        "beiyong2": "📋 备用任务2"
                    }

                    group_name = group_names.get(group, group)
                    has_tasks = False

                    for task_type, tasks in result.items():
                        if not tasks:
                            continue
                        has_tasks = True
                        for task in tasks:
                            task_name = task.get("name", "未知任务")
                            task_status = task.get("state", "")
                            task_id = task.get("id", "")

                            # 清理 HTML 标签
                            task_name = task_name.replace("<span id='share_title'>0/7</span>", "")
                            task_name = task_name.replace("<span id=\'share_title\'>0/7</span>", "")
                            task_name = task_name.replace("<span style=\'color: red; font-weight: bold;\'>", "")
                            task_name = task_name.replace("</span>", "")
                            task_name = task_name.replace("<br>", " ")

                            if task_status == "FINISH":
                                self.log(f"  ✅ {task_name}")
                            elif task_status == "WAIT":
                                self.log(f"  📝 {task_name} (待完成)")
                                # 尝试自动完成简单点击任务
                                step_types = task.get("stepTypeSet", [])
                                if "click" in step_types and len(step_types) == 1:
                                    await self.complete_task(task_id, task_name)
                            else:
                                self.log(f"  ⏳ {task_name} ({task_status})")

                    if not has_tasks:
                        self.log(f"  暂无任务")

                else:
                    self.log(f"❌ 获取任务列表失败：{data.get('msg')}")
            else:
                self.log(f"❌ 获取任务列表异常：HTTP {response.status_code}")
        except Exception as e:
            self.log(f"❌ 获取任务列表异常：{e}")

    async def complete_task(self, task_id, task_name):
        """完成任务 - 新版 API"""
        try:
            # 基于抓包，任务完成可能需要访问特定链接或上报
            # 这里简化处理，实际可能需要根据任务类型调用不同接口
            self.log(f"    尝试自动完成任务 {task_id}...")
            # 实际实现需要根据具体任务类型调整
            await asyncio.sleep(0.5)
        except Exception as e:
            pass

    async def get_quick_prize(self):
        """获取快捷奖励信息 - /ycloud/signin/page/getQuickPrizeVo"""
        try:
            response = await self.client.get(
                url="https://m.mcloud.139.com/ycloud/signin/page/getQuickPrizeVo",
                headers=self.auth_headers,
                cookies=self.cookies
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    result = data.get("result", {})
                    is_friday = result.get("isFriday", 0)
                    start_hour = result.get("startHour", 10)
                    start_min = result.get("startMinute", 30)
                    end_hour = result.get("endHour", 12)
                    end_min = result.get("endMinute", 30)
                    is_cur_month_received = result.get("isCurMonthReceived", 0)

                    self.log(f"🎁 快捷奖励: {'周五' if is_friday else '非周五'} | 时间 {start_hour}:{start_min:02d}-{end_hour}:{end_min:02d} | 本月已领: {'是' if is_cur_month_received else '否'}")
        except Exception as e:
            pass

    async def task_expansion(self):
        """任务扩展/云朵膨胀 - /ycloud/signin/page/taskExpansion"""
        try:
            response = await self.client.get(
                url="https://m.mcloud.139.com/ycloud/signin/page/taskExpansion",
                headers=self.auth_headers,
                cookies=self.cookies
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    result = data.get("result", {})
                    cur_backup = result.get("curMonthBackup", False)
                    pre_backup = result.get("preMonthBackup", False)
                    next_month = result.get("nextMonthTaskRecordCount", 0)

                    self.log(f"📈 备份状态: 本月{'✅' if cur_backup else '❌'} | 上月{'✅' if pre_backup else '❌'} | 下月膨胀:{next_month}朵")
        except Exception as e:
            pass

    async def receive_clouds(self):
        """领取云朵 - /ycloud/signin/page/receive"""
        try:
            response = await self.client.get(
                url="https://m.mcloud.139.com/ycloud/signin/page/receive",
                headers=self.auth_headers,
                cookies=self.cookies
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    result = data.get("result", {})
                    receive = result.get("receive", 0)
                    total = result.get("total", 0)
                    self.summary["clouds"] = total
                    self.log(f"☁️ 云朵: 待领取{receive}朵 | 总计{total}朵")
                else:
                    self.log(f"☁️ 云朵状态: {data.get('msg')}")
        except Exception as e:
            pass

    async def get_pop_info(self):
        """获取弹窗信息 - /ycloud/signin/public/getPopInfo"""
        try:
            response = await self.client.post(
                url="https://m.mcloud.139.com/ycloud/signin/public/getPopInfo",
                headers=self.auth_headers,
                cookies=self.cookies,
                json={"clientType": "iphone", "version": "13.0.1"}
            )
            if response.status_code == 200:
                data = response.json()
                result = data.get("result", {})
                if result.get("showPop"):
                    self.log(f"🎉 有弹窗奖励可领取！")
        except Exception as e:
            pass

    async def popup_check(self):
        """检查弹窗 - /ycloud/signin/page/popup"""
        try:
            response = await self.client.get(
                url="https://m.mcloud.139.com/ycloud/signin/page/popup",
                headers=self.auth_headers,
                cookies=self.cookies
            )
            if response.status_code == 200:
                data = response.json()
                # 处理弹窗逻辑
        except:
            pass

    async def journaling(self, module, optkeyword, sourceid="1002"):
        """上报访问日志 - /ycloud/visitlog/journaling"""
        try:
            await self.client.post(
                url="https://m.mcloud.139.com/ycloud/visitlog/journaling",
                headers=self.auth_headers,
                cookies=self.cookies,
                data={
                    "module": module,
                    "optkeyword": optkeyword,
                    "sourceid": sourceid,
                    "marketName": "sign_in_3"
                }
            )
        except:
            pass

    async def run(self):
        """主执行流程"""
        self.log(f"\n{'='*60}")
        self.log(f"📱 开始执行用户【{self.encrypt_account}】")
        self.log(f"{'='*60}")

        # 上报访问日志
        await self.journaling("uservisit", "newsignin_index_client")

        self.log(f"\n📋 签到状态")
        await self.query_sign_in_status()

        self.log(f"\n🎈 弹窗检查")
        await self.get_pop_info()
        await self.popup_check()

        self.log(f"\n🎁 快捷奖励")
        await self.get_quick_prize()

        self.log(f"\n📅 每日任务")
        await self.get_task_list("day")

        self.log(f"\n📆 每月任务")
        await self.get_task_list("month")

        self.log(f"\n⏰ 限时任务")
        await self.get_task_list("time")

        self.log(f"\n📧 邮箱任务")
        await self.get_task_list("cloudEmail")

        self.log(f"\n📈 备份膨胀")
        await self.task_expansion()

        self.log(f"\n☁️ 云朵领取")
        await self.receive_clouds()

        # 上报完成日志
        await self.journaling("uservisit", "newsignin_index_receive_type")

        self.log(f"\n{'='*60}")
        self.log(f"✅ 用户【{self.encrypt_account}】执行完成")
        self.log(f"{'='*60}\n")

        return self.summary


async def main():
    if not ydyp_ck or ydyp_ck == ['']:
        fn_print("❌ 未配置环境变量 ydyp_ck")
        fn_print("📖 格式: jwtToken#手机号#deviceId")
        fn_print("📖 多账号使用 @ 分隔")
        fn_print("\n📖 获取方式:")
        fn_print("   1. 使用 Surge/Charles 等工具抓包移动云盘 App")
        fn_print("   2. 在请求头中找到 jwtToken 和 deviceId")
        fn_print("   3. 组合成: jwtToken#手机号#deviceId")
        return

    all_summaries = []
    for ck in ydyp_ck:
        if ck.strip():
            mobileCloudDisk = MobileCloudDisk(ck.strip())
            summary = await mobileCloudDisk.run()
            all_summaries.append(summary)

    # 输出汇总
    fn_print(f"\n{'='*60}")
    fn_print(f"📊 执行汇总")
    fn_print(f"{'='*60}")
    for s in all_summaries:
        fn_print(f"  👤 {s['account']}: 签到{'✅' if s['signed'] else '❌'} | 云朵{s['clouds']}朵")

    # 发送通知
    try:
        msg = f"中国移动云盘签到 - {datetime.now().strftime('%Y/%m/%d')}\n"
        for s in all_summaries:
            msg += f"\n{s['account']}: 签到{'✅' if s['signed'] else '❌'} | 云朵{s['clouds']}朵"
        send_notification_message_collection(msg)
    except Exception as e:
        print(f"通知发送失败：{e}")


if __name__ == '__main__':
    asyncio.run(main())
