#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
BASE = "https://doe29x10dqvat.cloudfront.net"
APPID = "1cfhnSTQ1T3tLpjtE"

async def main():
    itms_urls = []
    inhouse_info = {}

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

        async def on_itms(route):
            itms_urls.append(route.request.url)
            print(f"[ITMS] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)

        print("loading...")
        try:
            await page.goto(BASE+"/"+APPID, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")
            sys.exit(1)

        await asyncio.sleep(20)

        xhr = await page.evaluate("()=>window.__log||[]")
        dk = None
        enc_data = None
        for e in xhr:
            print(f"XHR [{e['status']}] {e['url']}")
            if 'getinfo' in e['url']:
                try: dk = json.loads(e['resp'])['data']['downloadKey']
                except: pass
            if 'inhouse' in e['url']:
                enc_data = json.loads(e['resp']).get('data','')
                print(f"  inhouse enc={enc_data[:50]}...")

        print(f"dk={dk}, itms={itms_urls}")
        if not enc_data:
            print("no enc data"); sys.exit(1)

        # 关键：直接在浏览器里调用解密函数
        # 找到 _0x3672a3 等函数
        dec = await page.evaluate("""(encData) => {
            // 找所有全局 _0x 函数并测试
            const results = [];
            for (const k of Object.keys(window)) {
                if (typeof window[k] !== 'function') continue;
                if (!k.startsWith('_0x') && !k.startsWith('_$')) continue;
                try {
                    // 用 encData 和各种 key 调用
                    for (const key of ['1cfhnSTQ1T3tLpjtE', '5bhabw', 'com.Jiaqi.RetryP', '']) {
                        const r = window[k](encData, key);
                        if (r && typeof r === 'string' && r.length > 30 && r.length < 500) {
                            results.push({func: k, key, result: r.slice(0, 300)});
                            if (r.includes('itms') || r.includes('http')) break;
                        }
                    }
                } catch(e) {}
            }
            return results.slice(0, 10);
        }""", enc_data)
        print(f"dec candidates: {dec}")

        # 也直接调 inhouse API 然后等 itms
        print(f"route itms: {itms_urls}")
        await browser.close()

asyncio.run(main())
