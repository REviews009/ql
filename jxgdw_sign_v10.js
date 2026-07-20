/**
 * 今视频签到脚本 v10 整合版（青龙面板适配）
 * 基于脚本B的最新接口 + 脚本A的日志优化
 * 
 * 青龙环境变量: JXGDW_DATA - 账号数据, 多账号用 @ 或换行分隔
 * 通知 JXGDW_NOTIFY - 通知开关 (1=是, 0=否, 默认1)
 * 
 * 抓 app.jxgdw.com 请求中的 Authorization: Bearer xxx
 */

const https = require('https');
const zlib = require('zlib');
const crypto = require('crypto');

// ============ 通知模块 ============
let notify;
try {
    notify = require('./sendNotify');
} catch (e) {
    notify = { sendNotify: async (t, m) => { console.log(`\n📢 ${t}\n${m}`); } };
}

// ============ 配置 ============
const API_BASE = 'https://app.jxgdw.com';
const UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 tvcVersion 6.1.2';
const APP_VERSION = '6.1.2';
const ENABLE_NOTIFY = (process.env.JXGDW_NOTIFY || '1') !== '0';

// 服务器限制单次最大上报时长（分钟）
const MAX_REPORT_DURATION = 60;

// ============ 工具函数 ============
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function randomDevice() {
    return String(Math.floor(Math.random() * 9000000000000) + 1000000000000);
}

// ============ HTTP 请求 ============
function request(url, method = 'GET', body = null, headers = {}) {
    return new Promise((resolve, reject) => {
        const parsed = new URL(url);
        const postData = body !== null ? (typeof body === 'string' ? body : JSON.stringify(body)) : '';

        const opts = {
            hostname: parsed.hostname,
            port: 443,
            path: parsed.pathname + parsed.search,
            method,
            headers: {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'User-Agent': UA,
                'appVersion': APP_VERSION,
                'Origin': 'https://share.jxgdw.com',
                'Referer': 'https://share.jxgdw.com/',
                'Connection': 'keep-alive',
                ...headers,
            },
            timeout: 15000,
        };

        if (body !== null) {
            if (!opts.headers['Content-Type']) opts.headers['Content-Type'] = 'application/json';
            opts.headers['Content-Length'] = Buffer.byteLength(postData);
        }

        const req = https.request(opts, (res) => {
            let stream = res;
            const encoding = res.headers['content-encoding'];
            if (encoding === 'gzip') stream = res.pipe(zlib.createGunzip());
            else if (encoding === 'deflate') stream = res.pipe(zlib.createInflate());
            else if (encoding === 'br') stream = res.pipe(zlib.createBrotliDecompress());

            let chunks = [];
            stream.on('data', c => chunks.push(c));
            stream.on('end', () => {
                const raw = Buffer.concat(chunks).toString();
                try { resolve(JSON.parse(raw)); }
                catch { resolve({ _raw: raw }); }
            });
            stream.on('error', reject);
        });

        req.on('error', reject);
        req.on('timeout', () => { req.destroy(); reject(new Error('请求超时')); });
        if (body !== null) req.write(postData);
        req.end();
    });
}

// ============ API 封装 ============
function authHeaders(token, device) {
    return {
        'Authorization': `Bearer ${token}`,
        'device': device,
        'os': 'ios',
    };
}

// 签到
async function doSign(token, device) {
    console.log('📝 执行签到...');
    return await request(API_BASE + '/api/app/user/sign', 'POST', '', {
        ...authHeaders(token, device),
        'Content-Length': '0',
    });
}

// 个人签到信息
async function getPersonalInfo(token, device) {
    return await request(API_BASE + '/api/app/user/sign/personal/info', 'GET', null, authHeaders(token, device));
}

// 观看任务列表
async function getWatchTasks(token, device) {
    return await request(API_BASE + '/api/app/user/sign/watch/task/my', 'GET', null, authHeaders(token, device));
}

// 分享次数
async function getShareTimes(token, device) {
    return await request(API_BASE + '/api/share/news/times', 'GET', null, authHeaders(token, device));
}

// 获取文章列表
async function getNewsFeed(token, device, pageSize = 20) {
    return await request(API_BASE + `/api/media/feed-video?pageNum=1&pageSize=${pageSize}`, 'GET', null, authHeaders(token, device));
}

// 获取文章详情
async function getMediaDetail(token, device, mediaId) {
    return await request(API_BASE + `/api/media/${mediaId}`, 'GET', null, authHeaders(token, device));
}

// 分享新闻
async function shareNews(token, device, mediaId) {
    return await request(API_BASE + `/api/share/news?mediaId=${mediaId}`, 'GET', null, authHeaders(token, device));
}

// ============ 收集可分享的新闻ID（日志优化版）============
async function collectShareableIds(token, device) {
    const ids = [];
    const feedResp = await getNewsFeed(token, device, 20);
    let startId = 1583000;
    if (feedResp.code === 0 && feedResp.result) {
        const list = feedResp.result.list || [];
        if (list.length > 0) startId = Math.max(...list.map(i => i.id));
    }
    for (let id = startId; id >= startId - 6000 && ids.length < 10; id -= 200) {
        try {
            const d = await getMediaDetail(token, device, id);
            if (d.code === 0 && d.result && d.result.contentType === 14) {
                ids.push(id);
            }
        } catch {}
    }
    if (ids.length > 0) {
        console.log(`   📋 找到 ${ids.length} 篇可分享文章`);
    }
    return ids;
}

// ============ 观看时长上报 ============
function md5(str) {
    return crypto.createHash('md5').update(str).digest('hex');
}

const WATCH_SALT = 'appkey=N9xu_&T4$qHjo#kV';
function generateSign(duration, t, userId) {
    const input = `duration=${duration}&jid=${userId}&t=${t}&${WATCH_SALT}&timestamp=${t}`;
    return md5(input);
}

// 观看时长上报
async function reportWatchDuration(token, device, duration = 5, userId = '') {
    const t = Math.floor(Date.now() / 1000);
    if (!userId) {
        console.log('⚠️ 无法获取用户ID, 跳过观看时长上报');
        return null;
    }
    const sign = generateSign(duration, t, userId);
    return await request(API_BASE + '/api/app/user/sign/watch/duration/report/v2', 'POST',
        { duration: Number(duration), t: Number(t), sign }, authHeaders(token, device));
}

// ============ 账号解析 ============
function parseAccounts(envStr) {
    if (!envStr) return [];
    const accounts = [];
    envStr.split(/[@\n]/).filter(Boolean).forEach(raw => {
        raw = raw.trim();
        if (!raw) return;
        if (raw.startsWith('{')) {
            try {
                const obj = JSON.parse(raw);
                if (obj.token) {
                    accounts.push({
                        token: obj.token.replace(/^Bearer\s+/i, ''),
                        name: obj.name || '',
                        device: obj.device || randomDevice(),
                    });
                }
                return;
            } catch {}
        }
        const token = raw.replace(/^Bearer\s+/i, '');
        accounts.push({ token, name: '', device: randomDevice() });
    });
    return accounts;
}

// ============ 解析JWT获取用户ID ============
function parseJwtSub(token) {
    try {
        const payload = token.split('.')[1];
        const decoded = JSON.parse(Buffer.from(payload, 'base64').toString());
        return decoded.sub || '';
    } catch {
        return '';
    }
}

// ============ 智能观看时长上报（日志优化版）============
async function smartWatchTasks(token, device, userId) {
    console.log('📺 开始智能观看任务...');

    let totalReported = 0;
    let round = 0;
    const SAFE_MAX_ROUNDS = 1000;

    while (round < SAFE_MAX_ROUNDS) {
        round++;

        // 1. 查询当前任务状态
        const tasksResp = await getWatchTasks(token, device);
        if (tasksResp.code !== 0 || !tasksResp.result) {
            console.log(`   ⚠️ 查询任务失败: ${tasksResp.message || '未知错误'}`);
            break;
        }

        const taskData = tasksResp.result;
        const taskList = taskData.taskList || [];
        const doneCount = taskList.filter(t => t.rewardFlag).length;
        const totalCount = taskList.length;

        const totalScore = taskList.reduce((sum, t) => sum + (t.score || 0), 0);
        const earnedScore = taskList.filter(t => t.rewardFlag).reduce((sum, t) => sum + (t.score || 0), 0);

        // 主要退出条件：所有任务已完成
        if (doneCount >= totalCount) {
            console.log(`   🎉 所有观看任务已完成! ${doneCount}/${totalCount} | 共获得${earnedScore}今豆`);
            break;
        }

        // 2. 获取下一任务信息
        const nextTaskDuration = taskData.nextTaskDuration;
        const currentTaskDuration = taskData.currentTaskDuration || 0;
        const nextTaskScore = taskData.nextTaskScore || 0;

        if (!nextTaskDuration && nextTaskDuration !== 0) {
            console.log(`   ⚠️ 无法获取下一任务信息`);
            break;
        }

        // 计算还需上报的时长
        const needDuration = nextTaskDuration - currentTaskDuration;

        if (needDuration <= 0) {
            console.log(`   [第${round}轮] 任务进度: ${doneCount}/${totalCount} | 已得${earnedScore}/${totalScore}今豆`);
            console.log(`   ⚠️ 计算需上报时长<=0，尝试上报5分钟`);
            const rpt = await reportWatchDuration(token, device, 5, userId);
            if (!rpt || rpt.code !== 0) break;
            totalReported += 5;
            if (rpt.result?.rewardFlag) {
                console.log(`   🎁 任务完成! +${rpt.result.taskScore || '?'}今豆`);
            }
            await sleep(1500);
            continue;
        }

        // 3. 确定本轮上报时长
        const reportDuration = Math.min(needDuration, MAX_REPORT_DURATION);

        console.log(`   [第${round}轮] 任务进度: ${doneCount}/${totalCount} | 已得${earnedScore}/${totalScore}今豆`);
        console.log(`   📊 目标${nextTaskDuration}分钟 | 当前${currentTaskDuration}分钟 | 本轮上报${reportDuration}分钟 | 奖励+${nextTaskScore}今豆`);

        // 4. 上报时长
        const rpt = await reportWatchDuration(token, device, reportDuration, userId);

        if (!rpt) {
            console.log(`   ❌ 上报请求失败`);
            break;
        }

        if (rpt.code !== 0) {
            console.log(`   ❌ 上报失败: ${rpt.message || '未知错误'}`);
            break;
        }

        totalReported += reportDuration;

        const result = rpt.result || {};
        if (result.rewardFlag) {
            console.log(`   🎁 任务完成! +${result.taskScore || nextTaskScore}今豆`);
        }

        // 检查是否还有下一任务
        if (!result.nextTaskDuration && result.nextTaskDuration !== 0) {
            console.log(`   🎉 所有观看任务已完成!`);
            break;
        }

        await sleep(1500);
    }

    if (round >= SAFE_MAX_ROUNDS) {
        console.log(`   ⚠️ 达到安全轮次限制(${SAFE_MAX_ROUNDS})，今日停止上报`);
    }

    console.log(`📺 本次共上报 ${totalReported} 分钟，执行了 ${round} 轮`);
    return totalReported;
}

// ============ 分享任务（日志优化版）============
async function doShareTasks(token, device) {
    console.log('📤 开始分享任务...');

    // 查询剩余分享次数
    const timesResp = await getShareTimes(token, device);
    if (timesResp.code !== 0 || !timesResp.result) {
        console.log('   ⚠️ 查询分享次数失败');
        return { success: 0, attempted: 0 };
    }

    const st = timesResp.result;
    const remaining = (st.shareTimesLimit || 3) - (st.times || 0);
    const beanCount = st.beanCount || 5;

    if (remaining <= 0) {
        console.log(`   📤 今日分享已完成 ${st.times}/${st.shareTimesLimit} 篇`);
        return { success: 0, attempted: 0, limitReached: true };
    }

    console.log(`   📊 今日已分享 ${st.times}/${st.shareTimesLimit} 篇，还可分享 ${remaining} 篇`);

    // 收集可分享文章
    const candidates = await collectShareableIds(token, device);
    if (candidates.length === 0) {
        console.log('   ❌ 未找到可分享的文章');
        return { success: 0, attempted: 0 };
    }

    // 逐个尝试分享
    let successCount = 0;
    let limitReached = false;
    const MAX_SHARE = remaining;
    const MAX_ATTEMPT = Math.min(candidates.length, 10);

    for (let i = 0; i < MAX_ATTEMPT && successCount < MAX_SHARE && !limitReached; i++) {
        const mediaId = candidates[i];
        await sleep(1000);

        try {
            const sr = await shareNews(token, device, mediaId);

            if (sr.code === 0) {
                successCount++;
                console.log(`   ✅ 分享成功 (${successCount}/${MAX_SHARE}) +${beanCount}今豆`);
            } else {
                const msg = sr.message || '未知错误';

                // 检测到上限，立即停止
                if (/上限|限制|已达|超过|max|limit|今日已|已完成|次数不足|最大次数/i.test(msg)) {
                    console.log(`   ⛔ ${msg.replace('分享失败，', '')}`);
                    limitReached = true;
                    break;
                }

                // 其他错误只显示一次
                if (i === 0 || !msg.includes('不是新闻')) {
                    console.log(`   ❌ ${msg}`);
                }
            }
        } catch (e) {
            if (i === 0) console.log(`   ❌ 分享异常: ${e.message}`);
        }
    }

    // 汇总输出
    if (limitReached) {
        console.log(`📤 分享结束 | 成功${successCount}篇 | 今日已达上限`);
    } else if (successCount >= MAX_SHARE) {
        console.log(`📤 分享结束 | 成功${successCount}篇 | 任务完成`);
    } else {
        console.log(`📤 分享结束 | 成功${successCount}篇 | 候选文章不足`);
    }

    return { success: successCount, attempted: successCount + (limitReached ? 1 : 0), limitReached };
}

// ============ 单账号处理 ============
async function processAccount(acc, label) {
    const { token, device } = acc;
    const uid = parseJwtSub(token);
    console.log(`🆔 用户ID: ${uid || '未知'}`);

    let resultMsg = '';

    // 1. 签到
    try {
        const resp = await doSign(token, device);
        if (resp.code === 0) {
            const reward = resp.result || 0;
            console.log(`✅ 签到成功! 获得 ${reward} 今豆`);
            resultMsg = `✅ +${reward}今豆`;
        } else {
            const msg = resp.message || JSON.stringify(resp).substring(0, 100);
            console.log(`⚠️ 签到: ${msg}`);
            resultMsg = `⚠️ ${msg}`;
        }
    } catch (e) {
        console.log(`❌ 签到异常: ${e.message}`);
        resultMsg = `❌ ${e.message}`;
    }

    await sleep(500);

    // 2. 智能观看时长上报
    try {
        await smartWatchTasks(token, device, uid);
    } catch (e) {
        console.log(`⚠️ 时长上报异常: ${e.message}`);
    }

    await sleep(500);

    // 3. 分享文章
    let shareResult = { success: 0 };
    try {
        shareResult = await doShareTasks(token, device);
    } catch (e) {
        console.log(`⚠️ 分享异常: ${e.message}`);
    }

    await sleep(500);

    // 4. 查询个人信息
    let beanCount = 0;
    let continueDays = 0;
    try {
        const info = await getPersonalInfo(token, device);
        if (info.code === 0 && info.result) {
            const r = info.result;
            beanCount = r.jspBeanCount || 0;
            continueDays = r.continueDays || 0;
            console.log(`💰 今豆余额: ${beanCount} | 连签: ${continueDays}天`);
            resultMsg += ` | 余额:${beanCount} | 连签:${continueDays}天`;
        }
    } catch (e) {
        console.log(`⚠️ 查询个人信息失败: ${e.message}`);
    }

    await sleep(500);

    // 5. 查询观看任务
    try {
        const tasks = await getWatchTasks(token, device);
        if (tasks.code === 0 && tasks.result) {
            const r = tasks.result;
            const done = r.taskList.filter(t => t.rewardFlag).length;
            const total = r.taskList.length;
            const totalScore = r.taskList.reduce((sum, t) => sum + (t.score || 0), 0);
            const earnedScore = r.taskList.filter(t => t.rewardFlag).reduce((sum, t) => sum + (t.score || 0), 0);
            console.log(`📺 观看任务: ${done}/${total} | 已得${earnedScore}/${totalScore}今豆`);
            if (r.nextTaskDuration) {
                console.log(`   下个任务: 再看${r.nextTaskDuration}分钟 +${r.nextTaskScore}今豆`);
            } else {
                console.log(`   观看任务已全部完成!`);
            }
        }
    } catch (e) {
        console.log(`⚠️ 查询观看任务失败: ${e.message}`);
    }

    // 6. 查询分享次数
    try {
        const st = await getShareTimes(token, device);
        if (st.code === 0 && st.result) {
            const r = st.result;
            console.log(`📤 分享任务: ${r.times}/${r.shareTimesLimit} 篇`);
        }
    } catch (e) {
        console.log(`⚠️ 查询分享次数失败: ${e.message}`);
    }

    return `${label}: ${resultMsg} | 分享:${shareResult.success}篇`;
}

// ============ 主流程 ============
async function main() {
    console.log('📺 今视频签到 开始');
    console.log('='.repeat(40));

    const envData = process.env.JXGDW_DATA || '';
    const accounts = parseAccounts(envData);

    if (!accounts.length) {
        console.log('⚠️ 未设置环境变量 JXGDW_DATA');
        console.log('  Token模式: JXGDW_DATA=eyJhbGci...');
        console.log('  多账号用 @ 或换行分隔');
        console.log('');
        console.log('  抓包方法:');
        console.log('  今视频APP → 抓 app.jxgdw.com 请求');
        console.log('  取 Authorization: Bearer 后面的JWT');
        return;
    }

    console.log(`📋 共 ${accounts.length} 个账号\n`);
    const results = [];

    for (let i = 0; i < accounts.length; i++) {
        const acc = accounts[i];
        const label = acc.name || `账号${i + 1}`;
        console.log(`===== ${label} =====`);

        try {
            const msg = await processAccount(acc, label);
            results.push(msg);
        } catch (e) {
            console.log(`❌ 处理异常: ${e.message}`);
            results.push(`${label}: ❌ ${e.message}`);
        }

        if (i < accounts.length - 1) {
            console.log('');
            await sleep(3000);
        }
    }

    // 汇总通知
    const summary = results.join('\n');
    console.log(`\n===== 汇总 =====\n${summary}`);
    if (ENABLE_NOTIFY && notify?.sendNotify) {
        await notify.sendNotify('今视频签到', summary);
    }
}

main().catch(e => {
    console.log('❌ 脚本异常:', e.message || e);
    process.exit(1);
});
