#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    itms_urls = []

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA, viewport={"width":390,"height":844},
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

        async def on_itms(route):
            itms_urls.append(route.request.url)
            print(f"[ITMS] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)

        # 直接访问原始 URL，让它自动跳转到最新的 CF 域名
        print(f"goto {TARGET}")
        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"goto err: {e}")

        print(f"after goto: {page.url}")

        # 等待 CF 页面的 API 调用
        await asyncio.sleep(20)
        print(f"final url: {page.url}")

        xhr = await page.evaluate("()=>window.__log||[]")
        dk = None
        enc_data = None
        for e in xhr:
            print(f"XHR [{e['status']}] {e['url']}")
            if 'getinfo' in e['url']:
                try: dk = json.loads(e['resp'])['data']['downloadKey']
                except: pass
            if 'inhouse' in e['url']:
                try: enc_data = json.loads(e['resp']).get('data','')
                except: pass

        print(f"dk={dk}")
        print(f"enc_data={enc_data[:50] if enc_data else None}")
        print(f"itms_urls={itms_urls}")

        if enc_data:
            # 在页面中调用解密函数
            dec = await page.evaluate("""(encData) => {
                const results = [];
                for (const k of Object.keys(window)) {
                    if (typeof window[k] !== 'function') continue;
                    try {
                        // 尝试用不同 key 调用所有可能的解密函数
                        for (const key of ['1cfhnSTQ1T3tLpjtE', '5bhabw', 'com.Jiaqi.RetryP', '']) {
                            const r = window[k](encData, key);
                            if (r && typeof r === 'string' && r.includes('itms')) {
                                results.push({func: k, key, r: r.slice(0,300)});
                            }
                        }
                    } catch(e) {}
                }
                return results;
            }""", enc_data)
            print(f"decrypt results: {dec}")

        await browser.close()

asyncio.run(main())
