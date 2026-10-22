#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, viewport={"width":390,"height":844})
        await ctx.add_init_script("""
            Object.defineProperty(navigator,'platform',{get:()=>'iPhone'});
            Object.defineProperty(navigator,'maxTouchPoints',{get:()=>5});
            window.__opened=[];
            window.__called=[];
            const _orig = window.open;
            window.open = function(url,t) {
                window.__opened.push(url||'');
                console.log('[OPEN]', url);
                return null;
            };
            // 拦截所有 setTimeout (window.open 在 setTimeout 里)
            const _origST = window.setTimeout;
            window.setTimeout = function(fn, delay) {
                // 执行函数时记录所有 window.open 调用
                return _origST.call(this, fn, delay);
            };
            // 拦截 String.prototype.indexOf 找 helper 属性检查
            const _origIdx = String.prototype.indexOf;
            String.prototype.indexOf = function(s) {
                if(s && (s.includes('helpe') || s.includes('Links') || s.includes('Paths'))) {
                    window.__called.push({method:'indexOf', str:this.slice(0,50), search:s});
                }
                return _origIdx.call(this, s);
            };
        """)
        page = await ctx.new_page()
        console_logs = []
        page.on("console", lambda m: console_logs.append(m.text))

        async def on_itms(r):
            print(f"ITMS: {r.request.url}")
            await r.abort()
        await page.route("itms-services://**", on_itms)

        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        await asyncio.sleep(20)

        # 直接在页面里找 _0x11e234 函数
        # 通过搜索所有返回字符串包含 cloudfront/plist 的函数
        plist_path = await page.evaluate("""() => {
            const results = [];
            for(const k of Object.keys(window)) {
                if(typeof window[k] !== 'function') continue;
                try {
                    const r = window[k]();
                    if(r && typeof r === 'string' && (r.includes('/clientapi') || r.includes('plist') || r.includes('cloudfront'))) {
                        results.push({k, r: r.slice(0,200)});
                    }
                } catch(e) {}
            }
            return results;
        }""")
        print(f"plist_path candidates: {plist_path[:5]}")

        # 找按钮点击
        btns = await page.query_selector_all("button")
        for btn in btns:
            if (await btn.inner_text()).strip() == "安装":
                await btn.click()
                break
        await asyncio.sleep(10)

        opened = await page.evaluate("()=>window.__opened||[]")
        called = await page.evaluate("()=>window.__called||[]")
        print(f"opened: {opened}")
        print(f"called: {called[:5]}")
        print(f"console: {[m for m in console_logs if 'OPEN' in m][:3]}")
        await browser.close()

asyncio.run(main())
