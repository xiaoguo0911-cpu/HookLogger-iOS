#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
BASE = "https://doe29x10dqvat.cloudfront.net"
APPID = "1cfhnSTQ1T3tLpjtE"

async def main():
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA, viewport={"width":390,"height":844},
            extra_http_headers={"Referer":"https://yjriz.nzctjvr.com/"}
        )
        await context.add_init_script("""
            Object.defineProperty(navigator,'platform',{get:()=>'iPhone'});
            Object.defineProperty(navigator,'maxTouchPoints',{get:()=>5});
            window.__log=[];
            const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open=function(m,u){this._u=u;return _o.apply(this,arguments)};
            XMLHttpRequest.prototype.send=function(b){
                const s=this;
                s.addEventListener('readystatechange',function(){
                    if(s.readyState===4) window.__log.push({url:s._u,status:s.status,resp:(s.responseText||'').slice(0,8000)});
                });
                return _s.apply(this,arguments);
            };
        """)
        page = await context.new_page()
        itms_urls = []
        async def on_itms(route):
            itms_urls.append(route.request.url)
            print(f"[ITMS] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)
        await page.goto(BASE+"/"+APPID, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(20)

        # 从 React fiber 深度搜索所有 itms 相关字符串
        result = await page.evaluate("""() => {
            const found = [];
            function search(obj, depth) {
                if (depth > 20 || !obj) return;
                if (typeof obj === 'string' && obj.includes('itms-services')) {
                    found.push(obj.slice(0, 500));
                    return;
                }
                if (typeof obj !== 'object') return;
                for (const k of Object.keys(obj).slice(0, 50)) {
                    try { search(obj[k], depth + 1); } catch(e) {}
                }
            }
            // 搜索 React root
            try {
                const root = document.querySelector('#root, [data-reactroot]');
                if (root) {
                    const k = Object.keys(root).find(k => k.startsWith('__react') || k.startsWith('__fiber'));
                    if (k) {
                        const queue = [root[k]];
                        const visited = new WeakSet();
                        while (queue.length > 0 && found.length === 0) {
                            const node = queue.shift();
                            if (!node || visited.has(node)) continue;
                            visited.add(node);
                            // 检查 memoizedState
                            if (node.memoizedState) {
                                let s = node.memoizedState;
                                while (s) {
                                    if (s.memoizedState) search(s.memoizedState, 0);
                                    s = s.next;
                                }
                            }
                            // 检查 memoizedProps
                            if (node.memoizedProps) search(node.memoizedProps, 0);
                            if (node.child) queue.push(node.child);
                            if (node.sibling) queue.push(node.sibling);
                        }
                    }
                }
            } catch(e) { return 'err: ' + e.message; }
            return found;
        }""")
        print(f"React fiber itms: {result}")

        # 也搜索整个 window 对象
        win_result = await page.evaluate("""() => {
            const found = [];
            for (const k of Object.getOwnPropertyNames(window)) {
                try {
                    const v = window[k];
                    if (typeof v === 'string' && v.includes('itms-services')) found.push(v.slice(0,500));
                    if (typeof v === 'object' && v !== null && JSON.stringify(v).includes('itms-services'))
                        found.push(k + ': ...');
                } catch(e) {}
            }
            return found;
        }""")
        print(f"window itms: {win_result}")

        print(f"route itms: {itms_urls}")
        await browser.close()

asyncio.run(main())
