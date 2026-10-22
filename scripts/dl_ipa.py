#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from playwright.async_api import async_playwright

CF_URL = "https://doe29x10dqvat.cloudfront.net/1cfhnSTQ1T3tLpjtE"
REFERER = "https://yjriz.nzctjvr.com/"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA, viewport={"width": 390, "height": 844},
            extra_http_headers={"Referer": REFERER}
        )
        # 模拟真实 iOS 设备特性
        await context.add_init_script("""
            Object.defineProperty(navigator, 'platform', {get: () => 'iPhone'});
            Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 5});
            window.__xhrLog = [];
            const _o = XMLHttpRequest.prototype.open;
            const _s = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(m, u) { this._u = u; return _o.apply(this, arguments); };
            XMLHttpRequest.prototype.send = function(b) {
                const s = this;
                s.addEventListener('readystatechange', function() {
                    if (s.readyState === 4) window.__xhrLog.push({url: s._u, status: s.status, resp: (s.responseText||'').slice(0,3000)});
                });
                return _s.apply(this, arguments);
            };
        """)

        page = await context.new_page()
        await page.goto(REFERER, wait_until="commit", timeout=10000)
        await asyncio.sleep(1)
        await page.goto(CF_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(10)

        # 截图
        await page.screenshot(path="/tmp/screen.png", full_page=True)

        # 找所有 canvas（二维码通常是 canvas 渲染的）
        result = await page.evaluate("""() => {
            const canvases = document.querySelectorAll('canvas');
            const imgs = document.querySelectorAll('img');
            const svgs = document.querySelectorAll('svg');
            
            // 找 React 组件的 props
            const findItms = (el) => {
                if (!el) return null;
                const keys = Object.keys(el).filter(k => k.startsWith('__react'));
                for (const k of keys) {
                    const fiber = el[k];
                    if (!fiber) continue;
                    const str = JSON.stringify(fiber);
                    if (str.includes('itms-services')) {
                        const m = str.match(/itms-services:\/\/[^"'\s]+/);
                        if (m) return m[0];
                    }
                }
                return null;
            };
            
            // 搜索整个 DOM
            const all = document.querySelectorAll('*');
            const itmsUrls = [];
            for (const el of all) {
                const r = findItms(el);
                if (r && !itmsUrls.includes(r)) itmsUrls.push(r);
            }
            
            return {
                canvases: canvases.length,
                imgs: Array.from(imgs).map(i => ({src: i.src.slice(0,100), cls: i.className})),
                svgs: svgs.length,
                itmsUrls: itmsUrls,
                allText: document.body.innerText.slice(0,500)
            };
        }""")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        # XHR log
        xhr = await page.evaluate("() => window.__xhrLog || []")
        print(f"\nXHR ({len(xhr)}):")
        for e in xhr:
            print(f"  [{e['status']}] {e['url']}")
            if e['url'] != '/clientapi/app/getinfo?appid=1cfhnSTQ1T3tLpjtE&android=false':
                print(f"    {e['resp'][:300]}")

        await browser.close()

asyncio.run(main())
