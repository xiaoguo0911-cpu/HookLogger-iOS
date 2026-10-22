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
            const _orig = window.open;
            window.open = function(url,t) {
                window.__opened.push(url||'');
                console.log('[OPEN]', (url||'').slice(0,300));
                return null;
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

        # 通过 React fiber 找安装按钮的 onClick，直接调用它
        result = await page.evaluate("""() => {
            try {
                const btns = document.querySelectorAll('button');
                for(const btn of btns) {
                    const text = btn.innerText || '';
                    if(text.trim() === '安装') {
                        // 找 React fiber
                        const fk = Object.keys(btn).find(k => k.startsWith('__react') || k.startsWith('__fiber'));
                        if(!fk) return 'no fiber on btn';
                        const fiber = btn[fk];
                        
                        // BFS 找 onClick
                        const q = [fiber];
                        while(q.length > 0) {
                            const n = q.shift();
                            if(!n) continue;
                            const p = n.memoizedProps;
                            if(p && p.onClick && typeof p.onClick === 'function') {
                                // 直接调用 onClick (绕过 _0x522bba 检查)
                                // 但先看看有什么
                                return 'found onClick: ' + p.onClick.toString().slice(0, 200);
                            }
                            if(n.return) q.push(n.return);
                            if(n.child) q.push(n.child);
                        }
                        return 'no onClick found in fiber';
                    }
                }
                return 'no install btn';
            } catch(e) {
                return 'err: ' + e.message;
            }
        }""")
        print(f"React onClick: {result}")

        # 找 _0x59497a 函数直接调用
        result2 = await page.evaluate("""() => {
            try {
                // 找所有只包含 window.open 调用的函数
                const fns = [];
                for(const k of Object.keys(window)) {
                    if(typeof window[k] !== 'function') continue;
                    const src = window[k].toString();
                    if(src.includes("window['open']") || src.includes("window.open")) {
                        fns.push({k, src: src.slice(0,100)});
                    }
                }
                return fns.slice(0,5);
            } catch(e) {
                return 'err: ' + e.message;
            }
        }""")
        print(f"Functions with window.open: {result2}")

        # 正常点击按钮
        btns = await page.query_selector_all("button")
        for btn in btns:
            if (await btn.inner_text()).strip() == "安装":
                await btn.click()
                break
        await asyncio.sleep(10)
        opened = await page.evaluate("()=>window.__opened||[]")
        print(f"opened: {opened}")
        print(f"console: {[m for m in console_logs if 'OPEN' in m][:3]}")
        await browser.close()

asyncio.run(main())
