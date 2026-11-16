// 抓取平台各功能页面截图（报告插图用）
// 用法： node shot.js
//   · 服务地址可用环境变量覆盖：BASE_URL=http://127.0.0.1:5000 node shot.js
//   · Chrome 路径可用环境变量覆盖：CHROME_PATH=... node shot.js
//   · 输出目录固定为本文件同级的 ui/ 目录，随工程整体迁移
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:5000';
const OUT = path.join(__dirname, 'ui');

// 优先使用本机已安装的 Chrome（避免额外下载 Playwright 自带浏览器）。
// 新版 Chrome 默认位置；若装在别处，请用 CHROME_PATH 环境变量指定。
const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean);

const PAGES = [
  ['login',        '/login',        false, 1280, 800],
  ['dashboard',    '/',             true,  1680, 2100],
  ['disease',      '/disease',      true,  1680, 1500],
  ['peak',         '/peak',         true,  1680, 1450],
  ['dept',         '/dept',         true,  1680, 1450],
  ['drug',         '/drug',         true,  1680, 1450],
  ['los',          '/los',          true,  1680, 1550],
  ['infectious',   '/infectious',   true,  1680, 1550],
  ['desensitize',  '/desensitize',  true,  1680, 1400],
  ['realtime',     '/realtime',     true,  1680, 1350],
  ['ml',           '/ml',           true,  1680, 1750],
  ['network',      '/network',      true,  1680, 1900],
  ['report',       '/report',       true,  1680, 1100],
  ['about',        '/about',        true,  1680, 1600],
];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const exe = CHROME_CANDIDATES.find(p => fs.existsSync(p));
  if (!exe) {
    console.error('未找到可用的 Chrome / Edge，请设置 CHROME_PATH 环境变量指向浏览器可执行文件');
    process.exit(1);
  }
  console.log('使用浏览器：' + exe);
  console.log('目标服务：' + BASE);

  const browser = await chromium.launch({ channel: undefined, executablePath: exe });
  const ctx = await browser.newContext({ viewport: { width: 1680, height: 950 }, deviceScaleFactor: 1.4 });
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error') console.log('  [console error]', m.text()); });

  for (const [name, url, needLogin, w, h] of PAGES) {
    try {
      if (needLogin) {
        await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' });
        await page.fill('input[name=username]', 'admin');
        await page.fill('input[name=password]', 'admin123');
        await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }).catch(() => {}), page.click('button[type=submit]')]);
      }
      await page.setViewportSize({ width: w, height: h });
      await page.goto(BASE + url, { waitUntil: 'networkidle' });
      await page.waitForTimeout(needLogin ? 2600 : 800);
      const file = path.join(OUT, `${name}.png`);
      await page.screenshot({ path: file, fullPage: true });
      console.log(`OK  ${name.padEnd(14)} -> ${file}`);
    } catch (e) {
      console.log(`ERR ${name}: ${e.message}`);
    }
  }
  await browser.close();
})();
