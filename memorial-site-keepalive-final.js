#!/usr/bin/env node

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// ==================== 自动安装 Chromium ====================
console.log('🔍 检查 Chromium 环境...');
try {
    try {
        execSync('chromium-browser --version', { stdio: 'pipe' });
        console.log('✅ Chromium 已安装，跳过安装步骤');
    } catch (checkErr) {
        console.log('📦 Chromium 未安装，正在自动安装（约需1-3分钟）...');
        execSync('apk add --no-cache chromium chromium-chromedriver', { 
            stdio: 'inherit',
            timeout: 600000
        });
        console.log('✅ Chromium 安装完成');
    }
} catch (err) {
    console.error('❌ Chromium 环境准备失败:', err.message);
    process.exit(1);
}
// ========================================================

const CONFIG = {
    url: 'https://reviews009.github.io/memorial-site/',
    duration: 3 * 60 * 1000,
    navigationTimeout: 60000,
    waitForStable: 10000,
    screenshotDir: process.env.QL_DATA_DIR 
        ? path.join(process.env.QL_DATA_DIR, 'scripts', 'memorial-site-screenshots')
        : path.join(__dirname, 'memorial-site-screenshots'),
    headless: true,
    saveScreenshots: true,
    screenshotKeepDays: 3,
    chromiumPath: '/usr/bin/chromium-browser',
};

// ... 后面你的原有代码保持不变

function sendNotify(title, content) {
    try {
        const notifyPaths = [
            '/ql/data/scripts/sendNotify.js',
            '/ql/scripts/sendNotify.js',
            path.join(__dirname, 'sendNotify.js'),
        ];
        for (const notifyPath of notifyPaths) {
            if (fs.existsSync(notifyPath)) {
                const { sendNotify } = require(notifyPath);
                sendNotify(title, content);
                return;
            }
        }
        console.log('[通知] ' + title + '\n' + content);
    } catch (e) {
        console.log('[通知失败] ' + e.message);
    }
}

function log(message, level) {
    level = level || 'INFO';
    const timestamp = new Date().toLocaleString('zh-CN');
    const logLine = '[' + timestamp + '] [' + level + '] ' + message;
    console.log(logLine);
    try {
        const logFile = path.join(CONFIG.screenshotDir, 'site-keepalive.log');
        fs.appendFileSync(logFile, logLine + '\n');
    } catch (e) {}
}

// 清理超过3天的截图
function cleanOldScreenshots() {
    try {
        if (!fs.existsSync(CONFIG.screenshotDir)) return;

        const files = fs.readdirSync(CONFIG.screenshotDir);
        const now = Date.now();
        const maxAge = CONFIG.screenshotKeepDays * 24 * 60 * 60 * 1000;
        let deletedCount = 0;

        for (const file of files) {
            if (file === 'site-keepalive.log') continue;

            const filePath = path.join(CONFIG.screenshotDir, file);
            const stats = fs.statSync(filePath);
            const fileAge = now - stats.mtime.getTime();

            if (fileAge > maxAge) {
                fs.unlinkSync(filePath);
                deletedCount++;
            }
        }

        if (deletedCount > 0) {
            log('已清理 ' + deletedCount + ' 个超过 ' + CONFIG.screenshotKeepDays + ' 天的旧截图');
        }
    } catch (e) {
        log('清理旧截图失败: ' + e.message, 'WARN');
    }
}

async function main() {
    const startTime = Date.now();
    let success = false;
    let errorMsg = '';

    log('========================================');
    log('网站保活脚本启动');
    log('目标URL: ' + CONFIG.url);
    log('计划运行时长: ' + (CONFIG.duration / 1000) + '秒');
    log('========================================');

    let browser = null;
    let context = null;
    let page = null;

    try {
        if (!fs.existsSync(CONFIG.screenshotDir)) {
            fs.mkdirSync(CONFIG.screenshotDir, { recursive: true });
        }

        cleanOldScreenshots();

        log('正在启动 Chromium 浏览器...');

        browser = await chromium.launch({
            executablePath: CONFIG.chromiumPath,
            headless: CONFIG.headless,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--window-size=1920,1080',
                '--disable-software-rasterizer',
                '--disable-features=IsolateOrigins,site-per-process',
            ],
        });

        log('浏览器启动成功');

        context = await browser.newContext({
            viewport: { width: 1920, height: 1080 },
            userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            locale: 'zh-CN',
            timezoneId: 'Asia/Shanghai',
        });

        page = await context.newPage();
        page.setDefaultTimeout(CONFIG.navigationTimeout);
        page.setDefaultNavigationTimeout(CONFIG.navigationTimeout);

        page.on('request', function(request) {
            const url = request.url();
            if (url.indexOf('supabase') !== -1 || url.indexOf('firebase') !== -1 ||
                url.indexOf('api') !== -1) {
                log('数据请求: ' + url.split('?')[0]);
            }
        });

        log('正在访问目标网站...');
        const response = await page.goto(CONFIG.url, {
              waitUntil: 'domcontentloaded',  // ← 从 'networkidle' 改过来
             timeout: 30000                   // ← 建议改小，或者写 CONFIG.navigationTimeout
        });

        log('页面加载完成，状态码: ' + response.status());

        log('等待页面稳定 ' + (CONFIG.waitForStable / 1000) + '秒...');
        await page.waitForTimeout(CONFIG.waitForStable);

        if (CONFIG.saveScreenshots) {
            const screenshotPath = path.join(CONFIG.screenshotDir, 'screenshot-start-' + Date.now() + '.png');
            await page.screenshot({ path: screenshotPath, fullPage: true });
            log('已保存初始截图: ' + screenshotPath);
        }

        log('开始模拟真实用户浏览行为...');

        const pageTitle = await page.title();
        log('页面标题: ' + pageTitle);

        const hasAlbum = (await page.locator('text=回忆相册').count()) > 0;
        const hasDiary = (await page.locator('text=心事日志').count()) > 0;
        const hasWall = (await page.locator('text=留言墙').count()) > 0;
        log('页面元素检查 - 相册:' + hasAlbum + ' 日志:' + hasDiary + ' 留言墙:' + hasWall);

        log('模拟页面滚动...');
        await page.evaluate(function() { window.scrollTo(0, document.body.scrollHeight / 3); });
        await page.waitForTimeout(2000);

        await page.evaluate(function() { window.scrollTo(0, document.body.scrollHeight * 2 / 3); });
        await page.waitForTimeout(2000);

        await page.evaluate(function() { window.scrollTo(0, document.body.scrollHeight); });
        await page.waitForTimeout(2000);

        try {
            const diarySection = await page.locator('text=心事日志').first();
            if ((await diarySection.count()) > 0) {
                log('点击"心事日志"区域...');
                await diarySection.click();
                await page.waitForTimeout(3000);
                log('心事日志区域点击完成');
            }
        } catch (e) {
            log('点击心事日志失败: ' + e.message, 'WARN');
        }

        try {
            const wallSection = await page.locator('text=留言墙').first();
            if ((await wallSection.count()) > 0) {
                log('点击"留言墙"区域...');
                await wallSection.click();
                await page.waitForTimeout(3000);
                log('留言墙区域点击完成');
            }
        } catch (e) {
            log('点击留言墙失败: ' + e.message, 'WARN');
        }

        try {
            const addPhotoBtn = await page.locator('text=点击添加照片').first();
            if ((await addPhotoBtn.count()) > 0) {
                log('点击"添加照片"按钮...');
                await addPhotoBtn.click();
                await page.waitForTimeout(2000);
                await page.keyboard.press('Escape');
                await page.waitForTimeout(1000);
                log('添加照片按钮点击完成');
            }
        } catch (e) {
            log('点击添加照片失败: ' + e.message, 'WARN');
        }

        if (CONFIG.saveScreenshots) {
            const screenshotPath = path.join(CONFIG.screenshotDir, 'screenshot-interaction-' + Date.now() + '.png');
            await page.screenshot({ path: screenshotPath, fullPage: true });
            log('已保存交互后截图: ' + screenshotPath);
        }

        log('进入保活循环，持续保持页面活跃...');
        const endTime = startTime + CONFIG.duration;
        let cycleCount = 0;

        while (Date.now() < endTime) {
            cycleCount++;
            const remaining = Math.ceil((endTime - Date.now()) / 1000);
            log('保活循环 #' + cycleCount + '，剩余 ' + remaining + '秒');

            const scrollY = Math.floor(Math.random() * 1000);
            await page.evaluate(function(y) { window.scrollTo(0, y); }, scrollY);

            const waitTime = 10000 + Math.floor(Math.random() * 10000);
            await page.waitForTimeout(Math.min(waitTime, endTime - Date.now()));

            try {
                const isActive = await page.evaluate(function() { return document.readyState === 'complete'; });
                if (!isActive) {
                    log('页面状态异常，尝试刷新...', 'WARN');
                    await page.reload({ waitUntil: 'networkidle' });
                }
            } catch (e) {
                log('页面活跃检查失败: ' + e.message, 'WARN');
            }
        }

        log('保活时间已到，准备结束...');

        if (CONFIG.saveScreenshots) {
            const screenshotPath = path.join(CONFIG.screenshotDir, 'screenshot-final-' + Date.now() + '.png');
            await page.screenshot({ path: screenshotPath, fullPage: true });
            log('已保存最终截图: ' + screenshotPath);
        }

        success = true;

        log('========================================');
        log('网站保活脚本执行完成');
        log('总运行时间: ' + ((Date.now() - startTime) / 1000).toFixed(1) + '秒');
        log('保活循环次数: ' + cycleCount);
        log('========================================');

    } catch (error) {
        errorMsg = error.message;
        log('脚本执行出错: ' + errorMsg, 'ERROR');
        log(error.stack, 'ERROR');

        if (page && CONFIG.saveScreenshots) {
            try {
                const errorScreenshot = path.join(CONFIG.screenshotDir, 'screenshot-error-' + Date.now() + '.png');
                await page.screenshot({ path: errorScreenshot, fullPage: true });
                log('已保存错误截图: ' + errorScreenshot);
            } catch (e) {
                log('保存错误截图失败: ' + e.message, 'WARN');
            }
        }
    } finally {
        if (context) {
            log('关闭浏览器上下文...');
            await context.close().catch(function() {});
        }
        if (browser) {
            log('关闭浏览器...');
            await browser.close().catch(function() {});
        }
        log('资源清理完成，脚本结束');

        const duration = ((Date.now() - startTime) / 1000).toFixed(1);
        if (success) {
            sendNotify(
                '时光信箱保活成功',
                '运行时长: ' + duration + '秒\n网站: ' + CONFIG.url + '\n状态: 保活成功，数据库已唤醒'
            );
        } else {
            sendNotify(
                '时光信箱保活失败',
                '运行时长: ' + duration + '秒\n网站: ' + CONFIG.url + '\n错误: ' + errorMsg + '\n请检查日志'
            );
        }
    }
}

main().catch(function(error) {
    console.error('未捕获的错误:', error);
    sendNotify('时光信箱保活异常', '脚本发生未捕获错误: ' + error.message);
    process.exit(1);
});
