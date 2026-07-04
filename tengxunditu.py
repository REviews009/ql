'''
new Env('腾讯地图小程序')
腾讯地图小程序每日签到
变量名：txdt，格式：user_id#备注，多个账号【换行隔开】
user_id值：我的-我的签到，抓包https://mmapgwh.map.qq.com/activity/v1
cron: 0 12 * * *
'''

'''
功能说明：腾讯地图小程序自动签到、抽奖、提现
修改：推送表格增加提现状态判断（≥15元可提现）
'''

import os,sys,time,uuid,base64,random,hashlib,requests,traceback,re
from multiprocessing import get_context
from typing import List

# ============ 内置随机User-Agent ============
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
    'Mozilla/5.0 (Linux; Android 14; vivo X200 Pro Build/UP1A.231005.007) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.64 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 14; Xiaomi 15 Build/UKQ1.230917.001) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.64 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.47',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.47',
]
def get_random_user_agent():
    return random.choice(USER_AGENTS)
# =============================================

# ============ 内置模块 ============
lmsg: List[str] = []

class ColorOutput:
    COLORS = {
        'red': '\033[91m', 'green': '\033[92m', 'yellow': '\033[93m',
        'blue': '\033[94m', 'magenta': '\033[95m', 'cyan': '\033[96m',
        'white': '\033[97m', 'reset': '\033[0m', 'bold': '\033[1m', 'underline': '\033[4m',
    }
    SYMBOLS = {
        'success': '✅', 'error': '❌', 'warning': '⚠️', 'info': 'ℹ️',
        'star': '⭐', 'arrow': '➤', 'check': '✓', 'cross': '✗', 'bullet': '●', 'diamond': '◆',
    }
    @staticmethod
    def print_header(title: str, width: int = 60) -> None:
        print("\n" + "=" * width)
        print(f"  {title}")
        print("=" * width)
    @staticmethod
    def print_success(text: str) -> None:
        print(f"{ColorOutput.SYMBOLS['success']} {text}")
    @staticmethod
    def print_error(text: str) -> None:
        print(f"{ColorOutput.SYMBOLS['error']} {text}")

def myprint(message: str) -> None:
    print(message)
    lmsg.append(message)

def mynotify(title: str, messages: List[str]) -> None:
    # 控制台打印汇总
    print(f"\n{'='*60}")
    print(f"【{title}】执行完成")
    print(f"{'='*60}")
    if messages:
        print(f"共 {len(messages)} 条消息")
    print("="*60)

    # 解析消息构建表格数据
    accounts = []
    current = None
    for line in messages:
        match = re.match(r'\*+\s*(.+?)\s*\*+', line)
        if match:
            if current:
                accounts.append(current)
            current = {
                'remark': match.group(1).strip(),
                'sign_prizes': [],
                'lottery_tickets': None,
                'lottery_results': [],
                'balance': None,
                'withdrawable': None
            }
        elif current:
            if line.startswith('每日签到：'):
                prize = line.replace('每日签到：', '').strip()
                current['sign_prizes'].append(prize)
            elif line.startswith('抽奖券：'):
                current['lottery_tickets'] = line.replace('抽奖券：', '').strip()
            elif line.startswith('第') and '次抽奖结果：' in line:
                result = line.split('次抽奖结果：')[-1].strip()
                current['lottery_results'].append(result)
            elif line.startswith('金币余额：'):
                parts = line.split('，')
                if len(parts) >= 1:
                    balance_part = parts[0].replace('金币余额：', '').replace('元', '').strip()
                    current['balance'] = balance_part
                if len(parts) >= 2:
                    withdraw_part = parts[1].replace('可提现金额：', '').replace('元', '').strip()
                    current['withdrawable'] = withdraw_part
    if current:
        accounts.append(current)

    # 构建 Markdown 表格，增加提现状态列
    if accounts:
        table_rows = [
            "| 账号 | 昵称 | 签到奖品 | 抽奖券 | 抽奖结果 | 余额(元) | 可提现(元) | 提现状态 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |"
        ]
        for idx, acc in enumerate(accounts, 1):
            sign_str = "+".join(acc['sign_prizes']) if acc['sign_prizes'] else "-"
            lottery_result_str = ",".join(acc['lottery_results']) if acc['lottery_results'] else "-"
            tickets = acc['lottery_tickets'] if acc['lottery_tickets'] is not None else "-"
            balance = acc['balance'] if acc['balance'] else "-"
            withdrawable = acc['withdrawable'] if acc['withdrawable'] else "-"
            
            # 提现状态判断（门槛15元）
            try:
                withdrawable_num = float(withdrawable) if withdrawable != "-" else 0.0
                if withdrawable_num >= 15.0:
                    withdraw_status = "✅ 可提现"
                else:
                    withdraw_status = f"❌ 不足15元 (差{15.0 - withdrawable_num:.1f}元)"
            except:
                withdraw_status = "无法判断"
            
            if len(sign_str) > 20:
                sign_str = sign_str[:17] + "..."
            if len(lottery_result_str) > 20:
                lottery_result_str = lottery_result_str[:17] + "..."
            table_rows.append(f"| {idx} | {acc['remark']} | {sign_str} | {tickets} | {lottery_result_str} | {balance} | {withdrawable} | {withdraw_status} |")
        content = "\n".join(table_rows)
    else:
        content = "\n".join(messages)

    # PUSHPLUS 推送
    token = os.getenv('PUSH_PLUS_TOKEN')
    if token and messages:
        full_content = f"## 📍 {title} 签到报告\n\n**时间**：{time.strftime('%Y-%m-%d %H:%M:%S')}\n\n{content}"
        try:
            resp = requests.post(
                'https://www.pushplus.plus/send',
                json={'token': token, 'title': title, 'content': full_content, 'template': 'markdown'},
                timeout=10
            )
            if resp.status_code == 200:
                result = resp.json()
                if result.get('code') == 200:
                    print("PUSHPLUS 推送成功！")
                else:
                    print(f"PUSHPLUS 推送失败：{result.get('msg')}")
            else:
                print(f"PUSHPLUS 请求失败，状态码：{resp.status_code}")
        except Exception as e:
            print(f"PUSHPLUS 发送异常：{str(e)}")
# =============================================

def myexcept(mytype,myvalue,mytraceback):
    for exceptstr in traceback.format_exception(mytype,myvalue,mytraceback):
        myprint(exceptstr.strip())
    mynotify('腾讯地图小程序',lmsg)

class Run:
    def setproxies(self):
        os.environ['http_proxy']=os.environ['https_proxy']=os.environ['HTTP_PROXY']=os.environ['HTTPS_PROXY']=''
        try:
            jbdl=os.getenv('jbdl')
            apiurl=random.choice(jbdl.split('@'))
            providers={'juliangip':'巨量IP','ipzan':'品赞代理','xiequ':'携趣网络','xiongmaodaili':'熊猫代理','xkdaili':'星空代理'}
            for key,value in providers.items():
                if key in apiurl:
                    break
                else:
                    value='未知代理'
            proxyservers=requests.get(apiurl).text.split('\n')
            proxyserver=random.choice(proxyservers).split(' ')[0].strip()
            os.environ['http_proxy']=os.environ['https_proxy']=os.environ['HTTP_PROXY']=os.environ['HTTPS_PROXY']=proxyserver
            self.lfm.append('设置代理服务器成功-%s：%s'%(value,proxyserver))
        except:
            self.lfm.append('设置代理服务器失败：%s'%traceback.format_exc())
    def getheaders(self,urlparams):
        reqid=str(uuid.uuid4())
        reqtime=str(int(time.time()*1000))
        tmapdefaultstr='mapinst=0&mapnonce=0&reqid=%s&reqtime=%s%s03a9875e795c3ecff15f617085e72d4cc'%(reqid,reqtime,urlparams)
        tmapdefaultsign=hashlib.md5(tmapdefaultstr.encode()).hexdigest()
        timestamp=reqtime[0:-3]
        signstr='request_id=%s&from_source=wx7643d5f831302ab0&timestamp=%s&token=e643d512f085d621bf6c9e80310d0498'%(reqid,timestamp)
        sign=hashlib.sha256(signstr.encode()).hexdigest().upper()
        headers={'user-agent': get_random_user_agent(),'from_source':'wx7643d5f831302ab0','request_id':reqid,'tmap-nonce':'0','tmap-engine':'web','tmap-reqid':reqid,'sign':sign,'user_id':self.txdtaccount,'tmap-reqtime':reqtime,'timestamp':timestamp,'tmap-install-id':'0','tmap-default-sign':tmapdefaultsign}
        return headers
    def main(self,txdtaccountdata):
        self.lfm=[]
        values=txdtaccountdata.split('#',1)
        self.txdtaccount,remark = values[0],values[1] if len(values)>1 else "无名账号"
        self.lfm.append('********%s********'%remark)
        if globals().get('setproxy'):
            self.setproxies()
        resp=requests.post('https://mmapgwh.map.qq.com/activity/v1/checkin',headers=self.getheaders('/activity/v1/checkin'),json={'activity_id':1721983577,'game_id':1}).json()
        message=resp['message']
        if message=='ok':
            for prize in resp['data']['prizes']:
                self.lfm.append('每日签到：%s'%prize['name'])
        else:
            self.lfm.append('每日签到：%s'%message)
        resp=requests.post('https://mmapgwh.map.qq.com/activity/v1/lottery/detail',headers=self.getheaders('/activity/v1/lottery/detail'),json={'activity_id':1721983577,'game_id':3,'rule_id':'tencent_map_lottery'}).json()
        availableticketnumber=resp['data']['available_ticket_number']
        self.lfm.append('抽奖券：%s'%availableticketnumber)
        for i in range(1,availableticketnumber+1):
            resp=requests.post('https://mmapgwh.map.qq.com/activity/v1/lottery',headers=self.getheaders('/activity/v1/lottery'),json={'activity_id':1721983577,'game_id':3}).json()
            message=resp['message']
            if message=='ok':
                for prize in resp['data']['prizes']:
                    self.lfm.append('第%s次抽奖结果：%s'%(i,prize['name']))
            else:
                self.lfm.append('第%s次抽奖结果：%s'%(i,message))
        resp=requests.post('https://mmapgwh.map.qq.com/activity/v1/withdraw/home',headers=self.getheaders('/activity/v1/withdraw/home'),json={'activity_id':1721983577,'game_id':4,'rule_id':'tencent_map_withdraw'}).json()
        data=resp['data']
        coins,currentwithdrawthreshold,withdrawableamount=data['coins'],data['current_withdraw_threshold'],data['withdrawable_amount']
        self.lfm.append('金币余额：%s元，可提现金额：%s元'%(coins/100,withdrawableamount/100))
        if withdrawableamount>=currentwithdrawthreshold:
            resp=requests.post('https://mmapgwh.map.qq.com/activity/v1/withdraw',headers=self.getheaders('/activity/v1/withdraw'),json={'activity_id':1721983577,'game_id':4}).json()
            self.lfm.append('提现结果：%s'%resp['message'])
        return self.lfm

if __name__ == '__main__':
    out = ColorOutput()
    out.print_header("腾讯地图小程序自动签到")
    sys.excepthook=myexcept
    txdt=os.getenv('txdt','')
    txdt = txdt.replace('&','\n')
    txdtaccounts = [i.strip() for i in txdt.splitlines() if i.strip()]
    txdtaccountsnums=len(txdtaccounts)
    with get_context('spawn').Pool(maxtasksperchild=1) as pool:
        lallresults=[]
        for txdtaccountdata in txdtaccounts:
            results=pool.apply_async(func=Run().main,args=[txdtaccountdata])
            lallresults.append(results)
        for index,allresults in enumerate(lallresults,1):
            myprint('>>>>>>>>账号【%s/%s】<<<<<<<<'%(index,txdtaccountsnums))
            try:
                results=allresults.get()
                for result in results:
                    myprint(result)
            except:
                myprint(traceback.format_exc())
    mynotify('腾讯地图小程序',lmsg)