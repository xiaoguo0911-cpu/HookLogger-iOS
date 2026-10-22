#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib, gzip, subprocess
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    cf_base = [None]
    js_urls = []
    itms_urls = []
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
            const _orig = window.open;
            window.open = function(url,t) {
                window.__opened.push(url||'');
                console.log('[OPEN]', url);
                if(url && url.includes('itms')) return null;
                return _orig ? _orig.call(this,url,t) : null;
            };
        """)
        page = await ctx.new_page()
        console_logs = []
        page.on("console", lambda m: console_logs.append(m.text))

        async def on_itms(r):
            itms_urls.append(r.request.url)
            print(f"ITMS: {r.request.url}")
            await r.abort()
        await page.route("itms-services://**", on_itms)

        async def on_resp(r):
            if '.js' in r.url and 'cloudfront' in r.url and 'static' in r.url:
                js_urls.append(r.url)
            if 'cloudfront' in r.url and cf_base[0] is None:
                m = re.match(r'(https://[^/]+cloudfront\.net)', r.url)
                if m: cf_base[0] = m.group(1)
        page.on("response", on_resp)

        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        await asyncio.sleep(15)

        # 用 Node.js 执行 JS 找 plist 路径
        if cf_base[0] and js_urls:
            js_url = js_urls[0]
            r = urllib.request.urlopen(urllib.request.Request(js_url, headers={"User-Agent":UA,"Accept-Encoding":"identity"}), timeout=15)
            jsc = r.read()
            try: jsc = gzip.decompress(jsc)
            except: pass
            js_str = jsc.decode('utf-8','replace')
            print(f"CF={cf_base[0]}, JS len={len(js_str)}")

            # 在 Node.js 里执行 JS 并找 plist URL
            node_code = """
const vm = require('vm');
const c = {
    window: {location: {host: '""" + cf_base[0].replace('https://','') + """', protocol:'https:',href:'""" + cf_base[0] + """/1cfhnSTQ1T3tLpjtE'}},
    document:{createElement:()=>({}),addEventListener:()=>{}},
    navigator:{userAgent:'iPhone',platform:'iPhone',maxTouchPoints:5},
    console:{log:()=>{},error:()=>{},warn:()=>{}},
    XMLHttpRequest:function(){this.open=()=>{};this.send=()=>{};this.setRequestHeader=()=>{};},
    setTimeout:()=>{},setInterval:()=>{},clearTimeout:()=>{},
    fetch:()=>Promise.resolve({json:()=>Promise.resolve({})}),
    Math:Math,JSON:JSON,Object:Object,Array:Array,String:String,Number:Number,
    parseInt:parseInt,parseFloat:parseFloat,isNaN:isNaN,
    decodeURIComponent:decodeURIComponent,encodeURIComponent:encodeURIComponent,
    Date:Date
};
c.window.window = c.window;
c.self = c;
c.globalThis = c;

try {
    vm.createContext(c);
    vm.runInContext(""" + json.dumps(js_str[:700000]) + """, c, {timeout:10000});
} catch(e) {
    process.stderr.write('VM: ' + e.message.slice(0,200) + '\n');
}

// 找所有以 /clientapi 开头的字符串
const found = [];
function searchStr(obj, depth) {
    if(depth > 10 || !obj) return;
    if(typeof obj === 'string' && obj.includes('/clientapi')) {
        found.push(obj.slice(0,300));
        return;
    }
    if(typeof obj === 'object') {
        for(const k of Object.keys(obj).slice(0,30)) {
            try { searchStr(obj[k], depth+1); } catch(e) {}
        }
    }
}
searchStr(c, 0);
process.stdout.write(JSON.stringify(found.slice(0,20)));
"""
            open('/tmp/findplist.js','w').write(node_code)
            res = subprocess.run(['node','/tmp/findplist.js'], capture_output=True, timeout=20)
            out = res.stdout.decode('utf-8','replace').strip()
            err = res.stderr.decode('utf-8','replace').strip()
            print(f"Node err: {err[:200]}")
            print(f"Node out: {out[:500]}")

        btns = await page.query_selector_all("button")
        for btn in btns:
            if (await btn.inner_text()).strip() == "安装":
                await btn.click()
                break
        await asyncio.sleep(10)
        opened = await page.evaluate("()=>window.__opened||[]")
        print(f"opened: {opened}")
        print(f"itms: {itms_urls}")
        print(f"console OPEN: {[m for m in console_logs if 'OPEN' in m][:3]}")
        await browser.close()

asyncio.run(main())
