import requests, time, hashlib, urllib.parse, os, re, base64, random, json
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

def load_send():
    p = os.path.dirname(os.path.abspath(__file__)) + "/notify.py"
    if os.path.exists(p):
        try:
            from notify import send
            return send
        except:
            return None
    return None

send = load_send()

class QwyxBot:
    def __init__(self):
        self.key_salt = base64.b64decode("c3VwZXJqaW5n").decode()
        self.api_base = base64.b64decode("aHR0cHM6Ly9hcGkucXV3YXlvdXh1YW4uY29t").decode()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.56(0x1800383b) NetType/WIFI Language/zh_CN",
            "xweb_xhr": "1",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
            "Referer": "https://servicewechat.com/wxddaa0832e6acc5f1/134/page-frame.html"
        }
        self.base_params = {
            "os": "miniProgram",
            "deviceabout": "miniProgram",
            "version": "1.3.00",
            "miniprogram_os": "iOS"
        }
        self.session_key = None
        self.device_id = None

    def sign(self, data):
        keys = sorted(data.keys())
        raw = "".join([f"{k}={data[k]}" for k in keys])
        raw = (raw + self.key_salt).replace(" ", "")
        quoted = urllib.parse.quote(raw, safe='')
        escaped = re.sub(r"[!|'|\(|\)|\~|\*]", lambda m: "%" + "{:02X}".format(ord(m.group(0))), quoted)
        return hashlib.sha1(escaped.encode('utf-8')).hexdigest().lower()

    def rand_str(self, length=32):
        return "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", k=length))

    def ecdh_init(self, token, device_id):
        try:
            print("  [+] 正在进行ECDH密钥协商...")
            self.device_id = device_id

            priv_key = ec.generate_private_key(ec.SECP256R1())
            pub_key = priv_key.public_key()
            pub_bytes = pub_key.public_bytes(encoding=Encoding.X962, format=PublicFormat.UncompressedPoint)
            client_pub_b64 = base64.b64encode(pub_bytes).decode('utf-8')

            salt = os.urandom(32)
            salt_b64 = base64.b64encode(salt).decode('utf-8')

            req_data = {
                **self.base_params,
                "clientPublicKey": urllib.parse.quote(client_pub_b64),
                "timestamp": str(int(time.time())),
                "salt": salt_b64,
                "device": self.device_id,
                "token": token
            }
            req_data["key"] = self.sign(req_data)

            url = f"{self.api_base}/dynamic_key/getServerPublicKey.do"
            resp = requests.post(url, data=req_data, headers=self.headers, timeout=10)

            print(f"  [-] 协商HTTP状态: {resp.status_code}")
            try:
                result = resp.json()
            except:
                print(f"  [-] ❌ 协商响应非JSON: {resp.text[:200]}")
                return False

            if result.get("code") != 1:
                print(f"  [-] ❌ 协商失败: {result.get('message')}")
                return False

            server_pub_b64 = result.get("data", {}).get("publicKey")
            if not server_pub_b64:
                print("  [-] ❌ 响应中缺少 publicKey")
                return False

            server_pub = base64.b64decode(server_pub_b64)
            print(f"  [-] 服务器公钥长度: {len(server_pub)} bytes, 首字节: 0x{server_pub[0]:02x}")

            if len(server_pub) != 65 or server_pub[0] != 0x04:
                print(f"  [-] ⚠️ 警告: 公钥格式非标准65字节未压缩点")

            server_pub_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), server_pub)
            shared = priv_key.exchange(ec.ECDH(), server_pub_key)

            info = f'{{"device":"{self.device_id}","token":"{token}"}}'.encode('utf-8')
            hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info)
            self.session_key = hkdf.derive(shared)
            print("  [+] ✅ ECDH密钥协商成功")
            return True
        except Exception as e:
            print(f"  [-] ❌ 密钥协商异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def encrypt(self, payload_dict):
        iv = os.urandom(12)
        plaintext = json.dumps(payload_dict, separators=(',', ':'), ensure_ascii=False)
        aesgcm = AESGCM(self.session_key)
        ciphertext = aesgcm.encrypt(iv, plaintext.encode('utf-8'), b"")
        return base64.b64encode(iv + ciphertext).decode('utf-8')

    def decrypt(self, encrypted_b64):
        try:
            combined = base64.b64decode(encrypted_b64)
            iv, ciphertext = combined[:12], combined[12:]
            aesgcm = AESGCM(self.session_key)
            return aesgcm.decrypt(iv, ciphertext, b"").decode('utf-8')
        except:
            return None

    def api_call(self, url_path, biz_data, token):
        url = f"{self.api_base}{url_path}"
        full_data = {**self.base_params, "token": token, **biz_data}
        full_data["key"] = self.sign(full_data)

        headers = self.headers.copy()
        headers["X-Request-Id"] = self.rand_str(32)
        headers["X-Device-Id"] = self.device_id
        headers["X-Token"] = token

        if self.session_key:
            try:
                headers["X-Param"] = self.encrypt(full_data)
                resp = requests.post(url, data={}, headers=headers, timeout=10)
                res = resp.json()

                if res.get("code") == 4096:
                    self.session_key = None
                    if self.ecdh_init(token, self.device_id):
                        return self.api_call(url_path, biz_data, token)
                    return {"code": -1, "message": "ERR_TUNNEL"}

                if "data" in res and res.get("code") == 1 and isinstance(res["data"], str):
                    decrypted = self.decrypt(res["data"])
                    if decrypted:
                        res["data"] = json.loads(decrypted)
                return res
            except Exception:
                self.session_key = None

        print("  [-] ⚠️ 明文降级模式")
        return requests.post(url, data=full_data, headers=headers, timeout=10).json()

    def try_api(self, path, biz_data, token):
        """尝试调用接口，打印调试信息"""
        print(f"  [-] 尝试接口: {path}")
        res = self.api_call(path, biz_data, token)
        msg = res.get('message', '')
        code = res.get('code', -1)
        print(f"  [-] 返回: code={code}, message={msg}")
        if res.get('data'):
            print(f"  [-] data: {json.dumps(res['data'], ensure_ascii=False)[:300]}")
        return res

    def run_account(self, idx, acc_data):
        parts = acc_data.strip().split("#")

        if len(parts) >= 3:
            token = parts[0]
            device_id = parts[1]
            acc_name = parts[2]
        elif len(parts) == 2:
            token = parts[0]
            acc_name = parts[1]
            device_id = os.environ.get(f"QWYX_DEVICE_{idx}", "")
            if not device_id:
                return f"👤 {acc_name}: 缺少 openid"
        else:
            token = parts[0]
            acc_name = f"账号{idx}"
            device_id = os.environ.get(f"QWYX_DEVICE_{idx}", "")
            if not device_id:
                return f"👤 {acc_name}: 缺少 openid"

        print("\n" + "-"*35 + f"\n▶ 正在处理: {acc_name}")
        print(f"  [-] Token: {token[:16]}...")
        print(f"  [-] Device-ID: {device_id}")

        try:
            if not self.ecdh_init(token, device_id):
                return f"👤 {acc_name}: ECDH协商失败"

            # 获取任务列表
            biz = {"current_time": str(int(time.time() * 1000)), "source": "4"}
            task_list = self.api_call("/task/task/taskList.do", biz, token)

            if task_list.get("code") != 1:
                return f"👤 {acc_name}: Token失效 - {task_list.get('message', '未知')}"

            userinfo = task_list.get("data", {}).get("userinfo", {})
            real_name = userinfo.get("username", acc_name)
            initial_pts = userinfo.get("points", "0")
            print(f"  [-] 账户: {real_name} | 跑前积分: {initial_pts}")

            # 打印任务列表调试信息
            tasks = task_list.get("data", {}).get("tasklist", [])
            print(f"  [-] 任务列表: {len(tasks)} 个任务")
            for t in tasks[:5]:
                print(f"      taskid={t.get('taskid')}, name={t.get('taskname', '')[:20]}")

            # ===== 签到：尝试多个可能的接口 =====
            print("  [-] --- 尝试签到接口 ---")
            biz_signin = {"current_time": str(int(time.time() * 1000)), "taskid": "1", "subtask_id": "0"}

            sign_paths = [
                "/task/task/taskSuccess.do",
                "/task/task/complete.do",
                "/task/task/finish.do",
                "/task/task/submit.do",
                "/task/task/doTask.do",
                "/task/task/receive.do",
                "/task/task/sign.do",
                "/task/task/checkIn.do",
            ]

            sign_res = None
            sign_ok = False
            for path in sign_paths:
                res = self.try_api(path, biz_signin, token)
                msg = res.get('message', '')
                if 'does not exist' not in msg.lower() and '不存在' not in msg:
                    sign_res = res
                    if res.get('code') == 1 or any(k in msg for k in ["已", "完成", "成功", "ok"]):
                        sign_ok = True
                        print(f"  [+] ✅ 签到接口找到: {path}")
                        break
                    elif '上限' in msg or '不能重复' in msg or '已完成' in msg:
                        sign_ok = True
                        print(f"  [+] ✅ 签到已完成: {path}")
                        break
                time.sleep(0.5)

            if not sign_res:
                sign_res = {"message": "未找到有效签到接口"}
            sign_msg = sign_res.get('message', '未知')
            sign_status = "✅ 签到成功" if sign_ok else f"❌ {sign_msg}"
            print(f"  [-] 签到结果: {sign_status}")

            # ===== 视频任务：尝试多个可能的接口 =====
            print("  [-] --- 尝试视频任务接口 ---")
            biz_video = {"current_time": str(int(time.time() * 1000)), "taskid": "40", "subtask_id": "0"}

            video_paths = [
                "/task/task/taskSuccess.do",
                "/task/task/complete.do",
                "/task/task/finish.do",
                "/task/task/submit.do",
                "/task/task/doTask.do",
                "/task/task/receive.do",
            ]

            a_c = 0
            gained_pts = 0
            max_attempts = 30
            video_path = None

            # 先探测有效接口
            for path in video_paths:
                res = self.try_api(path, biz_video, token)
                msg = res.get('message', '')
                if 'does not exist' not in msg.lower() and '不存在' not in msg:
                    video_path = path
                    print(f"  [+] ✅ 视频接口找到: {path}")
                    # 如果第一次就成功，算一次
                    if res.get('code') == 1:
                        a_c += 1
                        pts = res.get("data", {}).get("points", 60)
                        gained_pts += int(pts) if str(pts).isdigit() else 60
                        print(f"      └─ 第{a_c}次: ✅ +{pts}积分 | 累计: {gained_pts}")
                    break
                time.sleep(0.5)

            # 如果找到接口，继续刷
            if video_path:
                for i in range(max_attempts - a_c):
                    wait_time = random.randint(160, 200)
                    print(f"         🛡️ 冷却中，等待 {wait_time} 秒...")
                    time.sleep(wait_time)

                    res = self.api_call(video_path, biz_video, token)
                    code = res.get("code")
                    msg = res.get("message", "未知错误")

                    if code == 1:
                        a_c += 1
                        pts = res.get("data", {}).get("points", 60)
                        gained_pts += int(pts) if str(pts).isdigit() else 60
                        print(f"      └─ 第{a_c}次: ✅ +{pts}积分 | 累计: {gained_pts}")
                    elif any(kw in msg for kw in ["上限", "已达", "超出"]):
                        print(f"      └─ 触发服务器上限，今日共成功 {a_c} 次")
                        break
                    elif any(kw in msg for kw in ["不能重复", "已完成", "已领取"]):
                        print(f"      └─ 任务已全部看完 ({msg})")
                        break
                    else:
                        print(f"      └─ 异常: {msg}")
                        break
            else:
                print(f"      └─ ❌ 未找到有效视频任务接口")

            v_s = f"🎬 执行({a_c}次) | 收益: +{gained_pts}分"
            print(f"  [√] 账号 [{real_name}] 处理完毕")
            return f"👤 昵称：{real_name}\n   ├ 原有：{initial_pts} 分\n   ├ 签到：{sign_status}\n   └ 视频：{v_s}"

        except Exception as e:
            print(f"  [x] 异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"⚠️ {acc_name}: 运行异常"

def main():
    _h = "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃  匠 心 忠 华 助 手 (v9.3 自动探测版) ┃\n┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"
    print(_h)
    _d = os.environ.get("QWYX_DATA", "")
    if not _d:
        print("\n❌ 未找到 QWYX_DATA，请配置环境变量")
        print("格式: token#openid#备注名")
        return

    _accs = [a for a in _d.replace("\n", "&").split("&") if a.strip()]
    bot = QwyxBot()
    _reps = []

    for i, a in enumerate(_accs, 1):
        _reps.append(bot.run_account(i, a))

    _f = "\n" + "="*35 + "\n🎯 任务汇总报告：\n\n" + "\n\n".join(_reps)
    print(_f)

    if send:
        send("匠心忠华v9.3任务报告", _h + "\n\n" + "\n\n".join(_reps))

if __name__ == "__main__":
    main()
