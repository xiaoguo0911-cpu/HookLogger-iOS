#!/usr/bin/env python3
import asyncio, sys, os, json
from playwright.async_api import async_playwright

CF_URL = "https://doe29x10dqvat.cloudfront.net/1cfhnSTQ1T3tLpjtE"
REFERER = "https://yjriz.nzctjvr.com/"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
BASE = "https://doe29x10dqvat.cloudfront.net"
APPID = "1cfhnSTQ1T3tLpjtE"

async def main():
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA, viewport={"width": 390, "height": 844},
            extra_http_headers={"Referer": REFERER}
        )
        await context.add_init_script("""
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
        await page.goto(CF_URL, wait_until="networkidle", timeout=45000)
        await asyncio.sleep(8)

        # 完整 HTML
        html = await page.evaluate("() => document.documentElement.outerHTML")
        print(f"=== FULL HTML ({len(html)}) ===")
        print(html[:5000])

        # 所有可见元素
        print("\n=== ALL ELEMENTS WITH TEXT ===")
        els = await page.evaluate("""() => {
            const result = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
            let node = walker.nextNode();
            while (node) {
                const text = node.textContent.trim();
                const rect = node.getBoundingClientRect();
                if (text && text.length < 50 && rect.width > 0 && rect.height > 0) {
                    result.push({
                        tag: node.tagName, 
                        text: text.slice(0,40),
                        x: Math.round(rect.x), 
                        y: Math.round(rect.y),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height),
                        cls: node.className ? node.className.toString().slice(0,60) : ''
                    });
                }
                node = walker.nextNode();
            }
            return result;
        }""")
        for el in els:
            print(f"  <{el['tag']}> '{el['text']}' @ ({el['x']},{el['y']}) {el['w']}x{el['h']} cls={el['cls']}")

        await browser.close()

asyncio.run(main())
