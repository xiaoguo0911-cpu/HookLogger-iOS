#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request
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
            window.__log=[];
            window.__opened=[];
            const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open=function(m,u){this._u=u;return _o.apply(this,arguments)};
            XMLHttpRequest.prototype.send=function(b){
                const s=this;
                s.addEventListener('readystatechange',function(){
                    if(s.readyState===4) window.__log.push({url:s._u,status:s.status,resp:(s.responseText||'').slice(0,8000)});
                });
                return _s.apply(this,arguments);
            };
            const _origOpen = window.open;
            window.open = function(url,target) {
                console.log('[window.open]', url, target);
                window.__opened.push(url||'');
                if(url && url.includes('itms-services')) return null;
                return _origOpen ? _origOpen.call(this, url, target) : null;
            };
        """)
        page = await ctx.new_page()
        console_msgs = []
        page.on("console", lambda m: console_msgs.append(m.text))

        async def on_itms(r):
            print(f"ITMS ROUTE: {r.request.url}")
            window.__opened = [r.request.url]
            await r.abort()
        await page.route("itms-services://**", on_itms)

        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        await asyncio.sleep(20)

        # 找所有 React root state
        state = await page.evaluate("""() => {
            const results = {};
            try {
                const root = document.getElementById('root');
                if(!root) return {err:'no root'};
                const k = Object.keys(root).find(k => k.startsWith('__react') || k.startsWith('__fiber'));
                if(!k) return {err:'no fiber key'};
                const fiber = root[k];
                const queue = [fiber];
                const seen = new WeakSet();
                let count = 0;
                while(queue.length > 0 && count < 500) {
                    count++;
                    const n = queue.shift();
                    if(!n || seen.has(n)) continue;
                    seen.add(n);
                    if(n.memoizedState) {
                        let s = n.memoizedState;
                        while(s) {
                            const v = s.memoizedState;
                            if(v !== null && v !== undefined && typeof v === 'object' && v.xl) {
                                results.found_xl = JSON.stringify(v).slice(0, 500);
                            }
                            if(typeof v === 'string' && v.length > 30 && (v.includes('itms') || v.includes('http'))) {
                                results.str_state = v.slice(0,200);
                            }
                            s = s.next;
                        }
                    }
                    if(n.child) queue.push(n.child);
                    if(n.sibling) queue.push(n.sibling);
                }
                results.searched = count;
            } catch(e) { results.err = e.message; }
            return results;
        }""")
        print(f"state: {state}")

        # 点击安装按钮
        btns = await page.query_selector_all("button")
        for btn in btns:
            if (await btn.inner_text()).strip() == "安装":
                print("Clicking install")
                await btn.click()
                break

        await asyncio.sleep(10)

        # 读 opened 和 state after click
        opened = await page.evaluate("()=>window.__opened||[]")
        print(f"opened: {opened}")
        print(f"console: {[m for m in console_msgs if 'open' in m.lower() or 'itms' in m.lower()][:5]}")

        # 再检查 state
        state2 = await page.evaluate("""() => {
            const results = {};
            try {
                const root = document.getElementById('root');
                const k = Object.keys(root).find(k => k.startsWith('__react'));
                if(!k) return {err:'no fiber'};
                const queue = [root[k]];
                const seen = new WeakSet();
                while(queue.length > 0) {
                    const n = queue.shift();
                    if(!n || seen.has(n)) continue;
                    seen.add(n);
                    if(n.memoizedState) {
                        let s = n.memoizedState;
                        while(s) {
                            const v = s.memoizedState;
                            if(v && typeof v === 'object' && (v.xl || v.helperLinks)) {
                                results.data_obj = JSON.stringify(v).slice(0,500);
                            }
                            if(typeof v === 'string' && v.length > 20) {
                                results.strings = results.strings || [];
                                results.strings.push(v.slice(0,100));
                            }
                            s = s.next;
                        }
                    }
                    if(n.child) queue.push(n.child);
                    if(n.sibling) queue.push(n.sibling);
                }
            } catch(e) { results.err = e.message; }
            return results;
        }""")
        print(f"state2: {json.dumps(state2, ensure_ascii=False)[:500]}")

        await browser.close()

asyncio.run(main())
