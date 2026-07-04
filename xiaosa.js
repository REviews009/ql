/*
 * 潇洒桐庐 青龙脚本 (xiaosa.js) - v3 点赞修复版
 * 
 * 环境变量：xiaosa
 * 格式：账号&密码（多账号用 @ 隔开）
 * 示例：export xiaosa="13800138000&password123@13900139000&password456"
 * 
 * 定时：18 10,19 * * *
 */

const crypto = require('crypto');

// ==================== 配置 ====================
const CLIENT_ID = '10017';
const TENANT_ID = '59';
const APP_KEY = 'FR*r!isE5W';
const API_HOST = 'vapp.tmuyun.com';
const PASSPORT_HOST = 'passport.tmuyun.com';
const WXAPI_HOST = 'wxapi.hoolo.tv';

// 活动相关配置
const ACTIVITY_ID = '428';

// 频道ID列表（9轮，从 main.js 提取）
const CHANNEL_CONFIG = [
    { round: 1, id: '6530daf779f6be358bba1522' },
    { round: 2, id: '6530dae171a9ed74577e4689' },
    { round: 3, id: '6530db1e71a9ed74577e468e' },
    { round: 4, id: '657fe99979f6be03b8fd7fb8' },
    { round: 5, id: '657fe9ad79f6be03b8fd7fb9' },
    { round: 6, id: '65a9e12879f6be03b8fd807d' },
    { round: 7, id: '65a9e13b79f6be03b8fd807e' },
    { round: 8, id: '65baf8d979f6be5b358ba618' },
    { round: 9, id: '65baf8ed79f6be5b358ba619' }
];

const PUBLIC_KEY = `-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQD6XO7e9YeAOs+cFqwa7ETJ+WXiz
PqQeXv68i5vqw9pFREsrqiBTRcg7wB0RIp3rJkDpaeVJLsZqYm5TW7FWx/iOiXFc
+zCPvaKZric2dXCw27EvlH5rq+zwIPDAJHGAfnn1nmQH7wR3PCatEIb8pz5GFlTHM
lluw4ZYmnOwg+thwIDAQAB
-----END PUBLIC KEY-----`;

// ==================== 工具函数 ====================
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function generateDeviceId() {
    const chars = '0123456789ABCDEF';
    let uuid = '';
    for (let i = 0; i < 36; i++) {
        if (i === 8 || i === 13 || i === 18 || i === 23) {
            uuid += '-';
        } else if (i === 14) {
            uuid += '4';
        } else if (i === 19) {
            uuid += chars[(Math.random() * 4) | 0 + 8];
        } else {
            uuid += chars[(Math.random() * 16) | 0];
        }
    }
    return uuid;
}

function encryptPassword(password) {
    const encrypted = crypto.publicEncrypt({
        key: PUBLIC_KEY,
        padding: crypto.constants.RSA_PKCS1_PADDING
    }, Buffer.from(password, 'utf-8'));
    return encodeURIComponent(encrypted.toString('base64'));
}

function generateSignature(path, sessionId, requestId, timestamp) {
    const sigStr = `${path}&&${sessionId}&&${requestId}&&${timestamp}&&${APP_KEY}&&${TENANT_ID}`;
    return crypto.createHash('sha256').update(sigStr).digest('hex');
}

function maskPhone(phone) {
    return phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2');
}

function getAccounts() {
    const env = process.env.xiaosa || '';
    if (!env) return [];

    return env.split('@').map(acc => {
        const parts = acc.split('&');
        if (parts.length === 2) return parts;
        return null;
    }).filter(Boolean);
}

function parseJsonp(text) {
    if (text.startsWith('(') && text.endsWith(')')) {
        return JSON.parse(text.slice(1, -1));
    }
    try {
        return JSON.parse(text);
    } catch (e) {
        // 尝试提取 JSONP 回调中的 JSON
        const match = text.match(/^\w+\((.*)\)$/s);
        if (match) {
            return JSON.parse(match[1]);
        }
        throw e;
    }
}

// ==================== HTTP 请求封装 ====================
const axios = require('axios');

async function httpGet(url, headers, params) {
    const config = {
        url: url,
        method: 'GET',
        headers: headers,
        params: params,
        timeout: 15000,
        validateStatus: () => true
    };
    const res = await axios(config);
    return { body: JSON.stringify(res.data), statusCode: res.status, headers: res.headers };
}

async function httpPost(url, headers, body) {
    const cleanHeaders = { ...headers };
    delete cleanHeaders['Content-Length'];
    delete cleanHeaders['content-length'];

    const config = {
        url: url,
        method: 'POST',
        headers: cleanHeaders,
        data: body,
        timeout: 15000,
        validateStatus: () => true
    };
    const res = await axios(config);
    return { body: JSON.stringify(res.data), statusCode: res.status, headers: res.headers };
}

// ==================== 潇洒桐庐类 ====================
class XiaoSa {
    constructor(phone, password) {
        this.phone = phone;
        this.password = password;
        this.sessionId = '';
        this.accountId = '';
        this.msg = '';
        this.deviceId = generateDeviceId();
        this.wxOpenId = '';
        this.cnum = 0;
        this.points = 0;
        this.nickName = '';
        this.roundData = {};  // 存储每轮的文章数据 {round: {articles: [], readCount: 0}}
    }

    log(msg) {
        console.log(`[潇洒桐庐] ${msg}`);
        this.msg += msg + '\n';
    }

    getHeaders(path, requestId, timestamp) {
        const signature = generateSignature(path, this.sessionId, requestId, timestamp);
        return {
            'Host': API_HOST,
            'X-TIMESTAMP': timestamp,
            'JSSDK_FUNC_ID': '',
            'X-SESSION-ID': this.sessionId,
            'Accept': '*/*',
            'X-SIGNATURE': signature,
            'X-TENANT-ID': TENANT_ID,
            'JSSDK_APP_ID': '',
            'X-ACCOUNT-ID': this.accountId,
            'Accept-Language': 'zh-Hans-CN;q=1',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-REQUEST-ID': requestId,
            'User-Agent': `1.1.10;${this.deviceId};iPhone13,2;IOS;16.0;Appstore;7.3.2`,
            'Connection': 'keep-alive',
            'X-Auth-Token': '',
            'YI-TOKEN': '',
        };
    }

    getWxHeaders() {
        return {
            'Host': WXAPI_HOST,
            'Origin': 'https://tp.hoolo.tv',
            'Connection': 'keep-alive',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148;;xsb;xsb_xiaosatonglu;1.1.10;Appstore;native_app;7.3.2',
            'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
            'Referer': 'https://tp.hoolo.tv/',
            'Accept-Encoding': 'gzip, deflate, br'
        };
    }

    async login() {
        this.log('🔐 开始登录...');

        const encryptedPwd = encryptPassword(this.password);
        const loginUrl = `https://${PASSPORT_HOST}/web/oauth/credential_auth`;

        const loginHeaders = {
            'Host': PASSPORT_HOST,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cookie': 'acw_tc=781bad1c17830715746595888eef6464a415fcf4d97523ccc61afaae70ae67',
            'Connection': 'keep-alive',
            'Accept': '*/*',
            'User-Agent': `1.1.10;${this.deviceId};iPhone13,2;IOS;16.0;Appstore;7.3.2`,
            'X-REQUEST-ID': generateUUID(),
            'Accept-Language': 'zh-CN,zh-Hans;q=0.9'
        };

        const loginData = `client_id=${CLIENT_ID}&password=${encryptedPwd}&phone_number=${this.phone}`;

        this.log('📤 发送登录请求...');
        const loginRes = await httpPost(loginUrl, loginHeaders, loginData);
        const loginJson = JSON.parse(loginRes.body);

        if (loginJson.code !== 0) {
            throw new Error(`登录失败: ${loginJson.message || JSON.stringify(loginJson)}`);
        }

        const authCode = loginJson.data.authorization_code.code;
        this.log('✅ 获取授权码成功');

        const sessionUrl = `https://${API_HOST}/api/zbtxz/login`;
        const requestId = generateUUID();
        const timestamp = Date.now().toString();

        const sessionPath = '/api/zbtxz/login';
        const anonymousSessionId = '6a47833410cc1900024a8340';
        const fixedSignature = generateSignature(sessionPath, anonymousSessionId, requestId, timestamp);

        const sessionHeaders = {
            'Host': API_HOST,
            'X-TIMESTAMP': timestamp,
            'JSSDK_FUNC_ID': '',
            'X-SESSION-ID': anonymousSessionId,
            'Accept': '*/*',
            'X-SIGNATURE': fixedSignature,
            'X-TENANT-ID': TENANT_ID,
            'JSSDK_APP_ID': '',
            'Accept-Language': 'zh-Hans-CN;q=1',
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-REQUEST-ID': requestId,
            'User-Agent': `1.1.10;${this.deviceId};iPhone13,2;IOS;16.0;Appstore;7.3.2`,
            'Connection': 'keep-alive',
            'X-Auth-Token': '',
            'YI-TOKEN': '',
            'Cookie': 'acw_tc=0000000017830715403991086e26207be318d3eea4279beae4ab57a2b3eb25'
        };

        const sessionData = `code=${authCode}`;

        this.log('📤 换取session...');
        const sessionRes = await httpPost(sessionUrl, sessionHeaders, sessionData);
        const sessionJson = JSON.parse(sessionRes.body);

        if (sessionJson.code !== 0) {
            throw new Error(`换取session失败: ${sessionJson.message || JSON.stringify(sessionJson)}`);
        }

        this.sessionId = sessionJson.data.session.id;
        this.accountId = sessionJson.data.account.id;
        this.nickName = sessionJson.data.account.nick_name || '';

        this.log('✅ 登录成功');
        this.log(`📱 账号ID: ${this.accountId}`);
        this.log(`👤 昵称: ${this.nickName}`);
    }

    async getUserInfo() {
        this.log('📋 获取用户信息...');

        const url = `https://${WXAPI_HOST}/event/dtqp/index.php`;
        const headers = this.getWxHeaders();

        const params = {
            s: '/home/TmApi/getUserInformation',
            accountId: this.accountId,
            username: this.nickName,
            type: 'jsonp'
        };

        try {
            const res = await httpGet(url, headers, params);
            const json = parseJsonp(res.body);

            if (json.code === '0' && json.data) {
                this.wxOpenId = json.data.userid || '';
                this.cnum = parseInt(json.data.cnum) || 0;
                this.points = parseInt(json.data.points) || 0;

                this.log(`💰 当前积分: ${this.points}`);
                this.log(`🎲 可抽奖次数: ${this.cnum}`);
                this.log(`${this.wxOpenId ? '✅ 已绑定微信' : '⚠️ 未绑定微信'}`);
            }
        } catch (e) {
            this.log(`⚠️ 获取用户信息失败: ${e.message}`);
        }
    }

    async getChannelCounts() {
        this.log('📊 获取任务完成情况...');

        const url = `https://${WXAPI_HOST}/event/dtqp/index.php`;
        const headers = this.getWxHeaders();

        const params = { s: '/home/TmApi/channelCounts' };

        try {
            const res = await httpGet(url, headers, params);
            const json = parseJsonp(res.body);

            if (Array.isArray(json) && json.length >= 9) {
                this.log(`📈 各轮完成人数:`);
                for (let i = 0; i < 9; i++) {
                    this.log(`  第${i+1}轮: ${json[i]} 人`);
                }
            }
        } catch (e) {}
    }

    // ==================== 点赞功能 ====================

    // 获取文章列表（带点赞状态）
    async getArticlesWithLikeStatus(channelId) {
        // 方案1: 从频道API获取文章列表
        const url = `https://${API_HOST}/api/article/channel`;
        const requestId = generateUUID();
        const timestamp = Date.now().toString();
        const path = '/api/article/channel';
        const headers = this.getHeaders(path, requestId, timestamp);

        try {
            const res = await httpGet(url, headers, {
                channel_id: channelId,
                channel_type: '2',
                is_up: '1',
                size: '20',
                start: '0'
            });
            const json = JSON.parse(res.body);
            if (json.code === 0 && json.data && json.data.article_list && json.data.article_list.length > 0) {
                this.log(`📰 从频道API获取到 ${json.data.article_list.length} 篇文章`);
                return json.data.article_list || [];
            }
        } catch (e) {
            this.log(`⚠️ 频道API获取失败: ${e.message}`);
        }

        // 方案2: 如果频道API返回空，从已缓存的阅读文章列表中获取
        this.log('📰 频道API无数据，尝试从阅读任务文章列表获取...');

        let allArticles = [];
        for (const config of CHANNEL_CONFIG) {
            const roundData = this.roundData[config.round];
            if (roundData && roundData.all && roundData.all.length > 0) {
                // 将阅读任务的文章格式转换为点赞需要的格式
                const formatted = roundData.all.map(a => ({
                    id: a.id || a.article_id,
                    article_id: a.id || a.article_id,
                    list_title: a.doc_title || a.list_title || a.title,
                    doc_title: a.doc_title || a.list_title || a.title,
                    title: a.doc_title || a.list_title || a.title,
                    is_favorite: a.is_favorite || false,
                    liked: a.liked || false
                }));
                allArticles = allArticles.concat(formatted);
            }
        }

        if (allArticles.length > 0) {
            this.log(`📰 从阅读任务缓存获取到 ${allArticles.length} 篇文章`);
            return allArticles;
        }

        // 方案3: 如果缓存也没有，尝试直接获取各频道文章
        this.log('📰 尝试直接获取各频道文章...');
        for (const config of CHANNEL_CONFIG) {
            try {
                const articles = await this.fetchChannelArticlesDirect(config.id);
                if (articles.length > 0) {
                    this.log(`📰 从频道 ${config.round} 获取到 ${articles.length} 篇文章`);
                    allArticles = allArticles.concat(articles);
                }
            } catch (e) {
                // 继续下一个频道
            }
        }

        return allArticles;
    }

    // 直接获取频道文章（备用方案）
    async fetchChannelArticlesDirect(channelId) {
        const url = `https://${API_HOST}/api/article/channel`;
        const requestId = generateUUID();
        const timestamp = Date.now().toString();
        const path = '/api/article/channel';
        const headers = this.getHeaders(path, requestId, timestamp);

        try {
            const res = await httpGet(url, headers, {
                channel_id: channelId,
                channel_type: '2',
                is_up: '1',
                size: '20',
                start: '0'
            });
            const json = JSON.parse(res.body);
            if (json.code === 0 && json.data) {
                return json.data.article_list || [];
            }
        } catch (e) {}
        return [];
    }

    // 上报点赞事件（行为统计）
    async reportLikeEvent(articleId, articleTitle) {
        const url = `https://bggt.tmuyun.com/iop-ps/sdk/ued`;

        const eventData = {
            os: "ios",
            datetime: Date.now(),
            ext: "",
            sessionId: this.sessionId,
            gtcid: `gtc_${crypto.randomBytes(16).toString('hex')}`,
            properties: {
                $screen_width: 390,
                $app_version: "1.1.10",
                $firstvisittime: new Date().toISOString().split('T')[0],
                $model: "iPhone13,2",
                $network_type: "WIFI",
                $carrier: "中国电信",
                $wifi: true,
                $channelId: "appstore",
                $screen_height: 844,
                account_id: this.accountId,
                $lib_version: "IOS-GSIOP-1.2.9.0,IOS-3.0.1.0",
                $os_version: "16.0",
                $manufacturer: "Apple",
                $os: "iOS",
                EventCode: "A0021",
                EventName: "点击点赞",
                EventObjectId: articleId,
                EventObjectType: "C01",
                EventObjectName: articleTitle || "文章标题",
                EventChannelClassId: "636b478cad61a40b77d4c057",
                EventChannelClassName: "推荐",
                PageType: "新闻详情页",
                SelfObjectId: articleId,
                EventLinkUrl: `https://vapp.tmuyun.com/webDetails/news?id=${articleId}&tenantId=${TENANT_ID}`
            },
            eventId: "A0021",
            appid: "ZO8gqw51k27k9jBxG4lS2E"
        };

        const headers = {
            'Host': 'bggt.tmuyun.com',
            'Content-Type': 'application/json',
            'Connection': 'keep-alive',
            'Accept': '*/*',
            'User-Agent': `ZMCApplicationProject/1 CFNetwork/1390 Darwin/22.0.0`,
            'Accept-Language': 'zh-CN,zh-Hans;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br'
        };

        try {
            await httpPost(url, headers, JSON.stringify(eventData));
        } catch (e) {
            // 事件上报失败不影响主流程
        }
    }

    // 点赞单篇文章
    async likeArticle(articleId, articleTitle) {
        const url = `https://${API_HOST}/api/favorite/like`;
        const requestId = generateUUID();
        const timestamp = Date.now().toString();
        const path = '/api/favorite/like';
        const headers = this.getHeaders(path, requestId, timestamp);

        // 先上报点赞事件（模拟真实行为）
        await this.reportLikeEvent(articleId, articleTitle);

        try {
            const res = await httpPost(url, headers, `action=1&id=${articleId}`);
            const json = JSON.parse(res.body);

            if (json.code === 0 && json.success) {
                this.log(`  ❤️ 点赞成功 《${(articleTitle || '未知').slice(0, 18)}...》`);
                return true;
            } else {
                this.log(`  ⚠️ 点赞失败: ${json.message || json.code}`);
                return false;
            }
        } catch (e) {
            this.log(`  ❌ 点赞异常: ${e.message}`);
            return false;
        }
    }

    // 批量点赞任务
    async doLikeTask(maxLikes = 10) {
        this.log(`👍 开始执行点赞任务 (目标: ${maxLikes}篇)...`);

        // 如果还没有获取文章列表，先获取
        let hasData = false;
        for (const config of CHANNEL_CONFIG) {
            if (this.roundData[config.round] && this.roundData[config.round].all && this.roundData[config.round].all.length > 0) {
                hasData = true;
                break;
            }
        }

        if (!hasData) {
            this.log('📰 先获取文章列表...');
            await this.getAllArticles();
        }

        // 使用频道配置中的ID获取文章
        const targetChannelId = CHANNEL_CONFIG[0].id; // 使用第1轮频道
        const articles = await this.getArticlesWithLikeStatus(targetChannelId);

        if (!articles.length) {
            this.log('⚠️ 未获取到可点赞文章');
            return 0;
        }

        this.log(`📰 获取到 ${articles.length} 篇文章`);

        let successCount = 0;
        let skippedCount = 0;

        for (let i = 0; i < Math.min(articles.length, maxLikes); i++) {
            const article = articles[i];
            const articleId = article.id || article.article_id;
            const articleTitle = article.list_title || article.doc_title || article.title || '未知';

            // 跳过已点赞的
            if (article.is_favorite || article.liked) {
                skippedCount++;
                continue;
            }

            const success = await this.likeArticle(articleId, articleTitle);
            if (success) successCount++;

            // 随机延迟 1-3 秒
            await new Promise(r => setTimeout(r, 1000 + Math.random() * 2000));
        }

        this.log(`👍 点赞完成: ${successCount}成功, ${skippedCount}已赞跳过`);
        return successCount;
    }

    // ==================== 阅读功能 ====================

    // 获取单轮文章列表
    async getRoundArticles(round, channelId) {
        const url = `https://${WXAPI_HOST}/event/dtqp/index.php`;
        const headers = this.getWxHeaders();

        const params = {
            s: '/home/TmApi/channelList',
            channelId: channelId,
            userId: this.accountId,
            sessionId: this.sessionId
        };

        try {
            const res = await httpGet(url, headers, params);
            const json = parseJsonp(res.body);

            if (Array.isArray(json)) {
                const unreadArticles = json.filter(a => a.is_read === 'no');
                const readArticles = json.filter(a => a.is_read === 'ok');

                this.roundData[round] = {
                    all: json,
                    unread: unreadArticles,
                    read: readArticles,
                    channelId: channelId
                };

                return {
                    total: json.length,
                    unread: unreadArticles.length,
                    read: readArticles.length
                };
            }
        } catch (e) {
            this.log(`  ⚠️ 第${round}轮获取失败: ${e.message}`);
        }
        return { total: 0, unread: 0, read: 0 };
    }

    // 获取所有轮次文章
    async getAllArticles() {
        this.log('📰 获取阅读任务文章列表...');

        let totalUnread = 0;

        for (const config of CHANNEL_CONFIG) {
            const result = await this.getRoundArticles(config.round, config.id);

            if (result.total > 0) {
                this.log(`  第${config.round}轮: ${result.read}/${result.total} 已读, ${result.unread} 未读`);
                totalUnread += result.unread;
            }

            await new Promise(r => setTimeout(r, 300 + Math.random() * 300));
        }

        this.log(`📋 共 ${totalUnread} 篇未读文章`);
    }

    // 检查文章阅读状态
    async getArticleReadStatus(articleId) {
        const url = `https://${WXAPI_HOST}/event/dtqp/index.php`;
        const headers = this.getWxHeaders();

        const params = {
            s: '/home/TmApi/getUserRead',
            accountId: this.accountId,
            articleId: articleId,
            type: 'jsonp'
        };

        try {
            const res = await httpGet(url, headers, params);
            const json = parseJsonp(res.body);
            return json.read_effective === 1;
        } catch (e) {
            return false;
        }
    }

    // 上报阅读完成
    async postReadComplete(articleId, round) {
        const url = `https://${WXAPI_HOST}/event/dtqp/index.php`;
        const headers = this.getWxHeaders();

        const params = {
            s: 'home/baoming/postBaoming/',
            activityId: ACTIVITY_ID,
            name: this.accountId,
            city: articleId,
            gender: round,
            cellphone: this.phone,
            type: 'jsonp'
        };

        try {
            const res = await httpGet(url, headers, params);
            const json = parseJsonp(res.body);
            return json.code === '0';
        } catch (e) {
            return false;
        }
    }

    // 完成一轮后增加抽奖次数
    async addPrizeNum(round, num) {
        const url = `https://${WXAPI_HOST}/event/dtqp/index.php`;
        const headers = this.getWxHeaders();

        const params = {
            s: '/home/TmApi/addPrizenum',
            accountId: this.accountId,
            round: round,
            num: num,
            type: 'jsonp'
        };

        try {
            const res = await httpGet(url, headers, params);
            const json = parseJsonp(res.body);

            if (json.code === '0') {
                this.log(`🎁 第${round}轮完成，获得抽奖次数！`);
                return true;
            }
        } catch (e) {
            this.log(`⚠️ 增加抽奖次数失败: ${e.message}`);
        }
        return false;
    }

    // 阅读单篇文章（通过vapp模拟真实阅读）
    async readOneArticle(article, round) {
        const articleId = article.id;
        const title = article.doc_title || article.list_title || '未知';

        try {
            // 1. 获取文章详情
            const detailPath = `/api/article/detail`;
            const detailRequestId = generateUUID();
            const detailTimestamp = Date.now().toString();
            const detailUrl = `https://${API_HOST}${detailPath}`;
            const detailHeaders = this.getHeaders(detailPath, detailRequestId, detailTimestamp);

            const isVideo = article.doc_type === 9 || article.list_type === 108;
            const urlPath = isVideo ? '/webDetails/video' : '/webDetails/news';

            await httpGet(detailUrl, detailHeaders, { 
                id: articleId, 
                tenantId: TENANT_ID,
                url_Path: urlPath,
                vr: 'false'
            });

            // 2. 模拟阅读停留
            await new Promise(r => setTimeout(r, 3000 + Math.random() * 2000));

            // 3. 上报阅读时长
            const readTimePath = `/api/article/read_time`;
            const readTimeRequestId = generateUUID();
            const readTimeTimestamp = Date.now().toString();
            const readTimeUrl = `https://${API_HOST}${readTimePath}`;
            const readTimeHeaders = this.getHeaders(readTimePath, readTimeRequestId, readTimeTimestamp);

            await httpGet(readTimeUrl, readTimeHeaders, {
                channel_article_id: articleId,
                is_end: '1',
                read_time: Math.floor(2000 + Math.random() * 3000).toString()
            });

            // 4. 通过微信活动接口上报阅读完成
            await new Promise(r => setTimeout(r, 500));
            const success = await this.postReadComplete(articleId, round);

            if (success) {
                this.log(`  ✅ 《${title.slice(0, 18)}...》`);
                return true;
            } else {
                this.log(`  ⚠️ 《${title.slice(0, 18)}...》上报失败`);
                return false;
            }

        } catch (e) {
            this.log(`  ❌ 《${title.slice(0, 18)}...》${e.message}`);
            return false;
        }
    }

    // 按轮次阅读文章
    async readByRounds() {
        this.log('👀 开始按轮次阅读文章...');

        let totalRead = 0;
        let totalAddedPrize = 0;

        for (const config of CHANNEL_CONFIG) {
            const round = config.round;
            const data = this.roundData[round];

            if (!data || data.unread.length === 0) {
                continue;
            }

            this.log(`📖 第${round}轮 (${data.unread.length}篇未读)...`);

            let roundRead = 0;

            for (const article of data.unread) {
                const success = await this.readOneArticle(article, round);
                if (success) {
                    roundRead++;
                    totalRead++;
                }
                await new Promise(r => setTimeout(r, 2000 + Math.random() * 1500));
            }

            // 检查该轮是否全部完成
            const allRead = data.read.length + roundRead;
            if (allRead >= data.all.length && data.all.length > 0) {
                this.log(`  🎯 第${round}轮全部完成 (${allRead}/${data.all.length})`);
                const added = await this.addPrizeNum(round, allRead);
                if (added) totalAddedPrize++;
                await new Promise(r => setTimeout(r, 1000));
            } else {
                this.log(`  ⏳ 第${round}轮进度 ${allRead}/${data.all.length}`);
            }
        }

        this.log(`✅ 共阅读 ${totalRead} 篇，${totalAddedPrize} 轮完成获得抽奖次数`);
        return totalAddedPrize;
    }

    // 抽奖
    async drawLottery() {
        if (!this.wxOpenId) {
            this.log('⚠️ 未绑定微信，跳过抽奖');
            return;
        }

        // 重新获取最新抽奖次数
        await this.getUserInfo();

        if (this.cnum <= 0) {
            this.log('⏰ 当前无抽奖次数');
            return;
        }

        this.log(`🎲 开始抽奖 (次数: ${this.cnum})...`);

        const url = `https://${WXAPI_HOST}/event/dtqp/index.php`;
        const headers = this.getWxHeaders();

        let drawCount = 0;

        for (let i = 0; i < this.cnum; i++) {
            const params = {
                s: '/Home/ChoujiangNew/apiChoujiang',
                openId: this.accountId,
                action: 'cj',
                typeId: '122',
                address: '',
                userid: this.wxOpenId
            };

            try {
                const res = await httpGet(url, headers, params);
                const json = parseJsonp(res.body);

                if (json.code === '1') {
                    this.log(`🎉 中奖！${json.prizename || '获得奖品'}`);
                    drawCount++;
                } else if (json.code === '-200') {
                    this.log('⏰ 今日抽奖次数已用完');
                    break;
                } else if (json.code === '-49') {
                    this.log('⏳ 人数过多，稍后重试');
                    i--; // 重试
                } else if (['-3', '-4', '-5', '-202', '-201'].includes(json.code)) {
                    this.log('😔 未中奖');
                    drawCount++;
                } else {
                    this.log(`ℹ️ 结果: ${json.code} ${json.message || ''}`);
                }
            } catch (e) {
                this.log(`⚠️ 抽奖请求失败: ${e.message}`);
            }

            await new Promise(r => setTimeout(r, 2000 + Math.random() * 1000));
        }

        this.log(`🎲 抽奖完成，参与 ${drawCount} 次`);
    }

    // 获取中奖记录
    async getPrizeRecords() {
        this.log('🎁 查询中奖记录...');

        const url = `https://${WXAPI_HOST}/event/dtqp/index.php`;
        const headers = this.getWxHeaders();

        const params = {
            s: 'home/ChoujiangNew/getUserCj/',
            openid: this.accountId,
            type_id: '122'
        };

        try {
            const res = await httpGet(url, headers, params);
            const json = parseJsonp(res.body);

            if (json.code === '0' && json.msg && json.msg.length > 0) {
                this.log(`📜 中奖记录 (${json.msg.length} 条):`);
                for (const record of json.msg.slice(0, 5)) {
                    this.log(`  🏆 ${record.prize_name} - ${record.create_time}`);
                }
            } else {
                this.log('📭 暂无中奖记录');
            }
        } catch (e) {
            this.log('📭 暂无中奖记录');
        }
    }
}

// ==================== 主函数 ====================
!(async () => {
    const accounts = getAccounts();
    if (!accounts.length) {
        console.log('========== 潇洒桐庐 ==========');
        console.log('❌ 未配置环境变量 xiaosa');
        console.log('格式: export xiaosa="手机号&密码@手机号&密码"');
        console.log('脚本执行完毕');
        process.exit(0);
    }

    let allMsg = [];

    for (let i = 0; i < accounts.length; i++) {
        const [phone, password] = accounts[i];
        console.log(`\n========== 账号 ${i + 1}: ${maskPhone(phone)} ==========`);

        const user = new XiaoSa(phone, password);
        try {
            await user.login();
            await user.getUserInfo();
            await user.getChannelCounts();

            // ===== 执行点赞任务 =====
            await user.doLikeTask(10); // 每天点赞10篇

            await user.getAllArticles();
            await user.readByRounds();
            await user.drawLottery();
            await user.getPrizeRecords();
            allMsg.push(user.msg);
        } catch (e) {
            console.log(`❌ 账号 ${maskPhone(phone)} 执行出错: ${e.message}`);
            allMsg.push(`❌ ${maskPhone(phone)}: ${e.message}`);
        }

        if (i < accounts.length - 1) {
            await new Promise(r => setTimeout(r, 5000));
        }
    }

    const summary = allMsg.join('\n\n');
    console.log(`\n========== 潇洒桐庐 执行汇总 ==========\n${summary}`);

    // ========== 青龙通知调用 ==========
    try {
        const { sendNotify } = require('./sendNotify');
        if (typeof sendNotify === 'function') {
            await sendNotify('潇洒桐庐', summary);
            console.log('✅ 青龙通知发送成功');
        } else {
            console.log('⚠️ sendNotify 不是函数，通知未发送');
        }
    } catch (e) {
        console.log(`⚠️ 通知发送失败: ${e.message}`);
    }

    console.log('脚本执行完毕');
    process.exit(0);
})();