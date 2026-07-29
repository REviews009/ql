/*
 * 外星仔加速器 - 请求日志
 * 打印所有 API 请求，方便调试
 */

const $ = new Env("ETalien-Log");

const url = $request.url;
const method = $request.method;

// 只打印关键接口
if (url.includes('/ad/callback') || url.includes('/remain/duration') || url.includes('/ad/config')) {
    $.log(`[ETalien] ${method} ${url}`);
    $.log(`[ETalien] Headers: ${JSON.stringify($request.headers)}`);
}

$done({});