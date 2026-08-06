# -*- coding: utf-8 -*-
"""
脚本名称: 店铛铛v2.0 1.17更新
作者: YSJohnson
变量名: DDD_TOKEN
变量值: 备注#手机号#密码 (多账号换行分隔)
"""

import os
import time
import hashlib
import requests
import urllib3
import asyncio
import base64
from datetime import datetime
from pyDes import des, ECB, PAD_PKCS5

# 禁用 SSL 安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= 配置区 =================
ENV_VAR_NAME = 'DDD_TOKEN'  # 环境变量名
TARGET_HOST = 'gw.jiudageapp.com'
BASE_URL = f'https://{TARGET_HOST}'


# ================= 核心工具函数 =================

def get_md5(text):
    """MD5 加密 (用于登录密码)"""
    return hashlib.md5(str(text).encode('utf-8')).hexdigest().upper()


def encrypt_video_id(video_id, key):
    """
    DES 加密：用于生成领奖所需的参数
    对应 Reqable 抓包中的 URL 编码处理
    """
    try:
        k = des(key.encode('utf-8'), ECB, padmode=PAD_PKCS5)
        en = k.encrypt(str(video_id).encode('utf-8'))
        res = base64.b64encode(en).decode('utf-8')
        # 模拟 URL 编码替换
        return res.replace('+', '%2B').replace('/', '%2F').replace('=', '%3D')
    except Exception as e:
        print(f"加密失败: {e}")
        return None


def log(name, msg):
    """标准日志输出"""
    time_str = datetime.now().strftime('%H:%M:%S')
    print(f"[{time_str}][{name}] {msg}")


# ================= 核心任务逻辑 =================

async def start_worker(account):
    name, phone, password = account['name'], account['phone'], account['password']
    result_record = {'name': name, 'status': '未开始', 'reward': 0, 'msg': ''}
    session = requests.Session()

    # 仿真请求头
    session.headers.update({
        'Host': TARGET_HOST,
        'version': 'v1.6.2',
        'platform': 'Android',
        'user-agent': 'okhttp/4.10.0',
        'content-type': 'application/json; charset=UTF-8',
        'accept-encoding': 'gzip'
    })

    try:
        # 1. 执行登录
        login_res = session.post(f"{BASE_URL}/api/web/auth/pwdLogin",
                                 json={"password": get_md5(password), "phone": phone}, verify=False).json()

        if login_res.get('code') != 200:
            result_record['status'] = '失败'
            log(name, f"❌ 登录失败: {login_res.get('message', '账号或密码错误')}")
            return result_record

        session.headers.update({'authorization': login_res['result']['token']})
        log(name, "✅ 登录成功")

        # 2. 提取账号专属密钥 (shardCode)
        # 该密钥用于后续视频ID的加密，必须获取
        member_info = session.post(f"{BASE_URL}/api/web/member/getMemberInfo", json={}, verify=False).json()
        if not member_info.get('result'):
            log(name, "❌ 获取用户信息失败")
            return result_record

        des_key = member_info['result']['shardCode'][:8]

        log(name, "🚀 任务开始...")
        total_gain = 0

        # 3. 任务循环
        while True:
            # 获取任务
            task_res = session.post(f"{BASE_URL}/api/web/member/get/internalAdvertisement", json={},
                                    verify=False).json()
            task = task_res.get('result')

            if not task:
                log(name, "🟢 广告已扫光")
                result_record['msg'] = '广告已扫光'
                break

            target_id = task['id']
            video_url = task['videoUrl']
            enc_id = encrypt_video_id(target_id, des_key)
            log(name, f"▶️ 观看: {task.get('title', '视频广告')} | 等待 45s")

            # 4. 模拟视频流请求 (增加真实度)
            try:
                session.get(video_url, headers={'user-agent': 'stagefright/1.2 (Linux;Android 11)'}, timeout=5,
                            verify=False)
            except:
                pass

            # 5. 仿真观看时长并发送心跳
            # 这里的 sleep 和心跳请求是为了维持服务器端的活跃判定
            for _ in range(3):
                await asyncio.sleep(15)
                try:
                    session.post(f"{BASE_URL}/api/web/member/getMemberCenterInfo", json={}, verify=False)
                except:
                    pass

            # 6. 提交领奖
            claim_url = f"{BASE_URL}/api/web/newPeopleUnlock/receiveWelfareNineteenV2?videoId={enc_id}"
            res = session.post(claim_url, json={}, headers={'Content-Length': '0'}, verify=False).json()

            if res.get('code') == 200:
                total_gain = res['result']['visitedVideoCount']
                log(name, f"   ✅ 领奖成功: 进度 {total_gain}/7")
                if total_gain >= 7:
                    log(name, "🎉 今日任务已完成")
                    break
            else:
                msg = res.get('message', '未知错误')
                log(name, f"   ❌ 领奖失败: {msg}")
                # 遇到关键错误停止
                if any(kw in msg for kw in ['领奖失败', '过期', '手动', '异常']):
                    result_record.update({'status': '停止', 'msg': f"异常退出({msg})"})
                    break

            await asyncio.sleep(3)  # 任务间隔

        result_record.update({'status': '完成', 'reward': total_gain})

    except Exception as e:
        result_record.update({'status': '错误', 'msg': str(e)})
        log(name, f"☢️ 运行出错: {str(e)}")

    return result_record


# ================= 主程序 =================

async def main():
    print("\n=================================================")
    print("        店铛铛v2.0 1.17更新 | 作者: YSJohnson         ")
    print("代码发布地址：https://github.com/YSJohnson/QingLongScripts-YSJ")
    print("=================================================\n")
    env_data = os.getenv(ENV_VAR_NAME, '')

    if not env_data:
        print(f"❌ 未找到环境变量 {ENV_VAR_NAME}，请先设置变量。")
        print("格式: 备注#手机号#密码 (多账号换行)")
        return

    # 解析账号
    accounts = []
    for line in env_data.splitlines():
        line = line.strip()
        if not line or '#' not in line:
            continue
        try:
            # 兼容可能存在的额外空格
            parts = line.split('#')
            if len(parts) >= 3:
                accounts.append({'name': parts[0], 'phone': parts[1], 'password': parts[2]})
        except Exception:
            continue

    if not accounts:
        print("❌ 未提取到有效账号，请检查变量格式。")
        return

    print(f"检测到 {len(accounts)} 个账号，开始执行任务...\n")

    # 并发执行
    tasks = [start_worker(acc) for acc in accounts]
    final_results = await asyncio.gather(*tasks)

    print(f"\n================== 任务汇总报表 ==================")
    print(f"{'备注名':<10}\t{'状态':<10}\t{'进度':<5}\t{'详情'}")
    print("-" * 50)
    for r in final_results:
        print(f"{r['name']:<10}\t{r['status']:<10}\t{r['reward']:<5}\t{r['msg']}")


if __name__ == '__main__':
    asyncio.run(main())