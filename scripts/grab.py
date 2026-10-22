#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    inhouse_req_headers = []
    inhouse_resp = []
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
                if(url && url.includes('itms')) return null;
                return _orig ? _orig.call(this,url,t) : null;
            };
        """)
        page = await ctx.new_page()

        # 拦截所有 inhouse 请求，记录请求和响应头
        async def on_request(req):
            if 'inhouse' in req.url:
                inhouse_req_headers.append({
                    'url': req.url,
                    'headers': dict(req.headers)
                })
                print(f"inhouse REQUEST headers: {dict(req.headers)}")

        async def on_response(resp):
            if 'inhouse' in resp.url:
                hdrs = dict(resp.headers)
                body = await resp.text()
                inhouse_resp.append({'url': resp.url, 'headers': hdrs, 'body': body[:500]})
                print(f"inhouse RESPONSE headers: {hdrs}")
                print(f"inhouse body: {body[:200]}")

        page.on("request", on_request)
        page.on("response", on_response)

        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        await asyncio.sleep(20)

        cookies = await ctx.cookies()
        print(f"cookies: {cookies}")
        opened = await page.evaluate("()=>window.__opened||[]")
        print(f"opened: {opened}")
        await browser.close()

asyncio.run(main())
