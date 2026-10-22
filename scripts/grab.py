#!/usr/bin/env python3
import asyncio, sys, os, json, re, subprocess, urllib.request, urllib.parse, plistlib, gzip
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def get_itms():
    itms_urls = []
    cf_base = [None]
    js_urls = []

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, viewport={"width":390,"height":844})
        await ctx.add_init_script("""
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
        page = await ctx.new_page()

        async def on_itms(route):
            itms_urls.append(route.request.url)
            print(f"[ITMS] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)

        async def on_resp(resp):
            if '.js' in resp.url and 'cloudfront' in resp.url and 'static' in resp.url:
                js_urls.append(resp.url)
            if 'cloudfront' in resp.url and cf_base[0] is None:
                m = re.match(r'(https://[^/]+cloudfront\.net)', resp.url)
                if m: cf_base[0] = m.group(1)
        page.on("response", on_resp)

        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        await asyncio.sleep(20)
        print(f"CF: {cf_base[0]}, JS: {js_urls[:1]}")

        btns = await page.query_selector_all("button")
        print(f"Buttons: {len(btns)}")
        for btn in btns:
            txt = await btn.inner_text()
            if txt.strip() == '安装':
                print(f"Clicking install")
                await btn.click()
                break

        await asyncio.sleep(10)
        xhr = await page.evaluate("()=>window.__log||[]")
        dk = None
        enc = None
        for e in xhr:
            print(f"XHR [{e['status']}] {e['url']}")
            if 'getinfo' in e['url']:
                try: dk = json.loads(e['resp'])['data']['downloadKey']
                except: pass
            if 'inhouse' in e['url']:
                try: enc = json.loads(e['resp']).get('data','')
                except: pass

        print(f"dk={dk}, enc={enc[:40] if enc else None}, itms={itms_urls}")
        await browser.close()

    if itms_urls: return itms_urls[0]

    if cf_base[0] and js_urls and enc and dk:
        js_url = js_urls[0]
        print(f"Downloading JS: {js_url}")
        r = urllib.request.urlopen(urllib.request.Request(js_url, headers={"User-Agent":UA,"Accept-Encoding":"identity"}), timeout=15)
        jsc = r.read()
        try: jsc = gzip.decompress(jsc)
        except: pass
        js_str = jsc.decode('utf-8','replace')
        print(f"JS len={len(js_str)}")

        node_code = "const enc=" + json.dumps(enc) + ";\nconst dk=" + json.dumps(dk) + ";\nconst vm=require('vm');\nconst c={window:{},document:{createElement:()=>({}),addEventListener:()=>{}},navigator:{userAgent:'iPhone',platform:'iPhone',maxTouchPoints:5},location:{href:'',host:'',protocol:'https:'},console:{log:()=>{},error:()=>{},warn:()=>{}},XMLHttpRequest:function(){},setTimeout:()=>{},setInterval:()=>{},clearTimeout:()=>{},fetch:()=>Promise.resolve({json:()=>Promise.resolve({})})};\nc.window=c;c.self=c;\ntry{vm.createContext(c);vm.runInContext(" + json.dumps(js_str[:500000]) + ",c,{timeout:5000});}catch(e){}\nlet result=null;\nfor(const k of Object.keys(c)){if(typeof c[k]!=='function')continue;try{const r=c[k](enc,dk);if(r&&typeof r==='string'&&r.includes('itms')){result=r;break;}}catch(e){}}\nif(result)process.stdout.write(result);\nelse process.stderr.write('NOT FOUND');\n"

        with open('/tmp/decrypt.js','w') as f:
            f.write(node_code)
        res = subprocess.run(['node','/tmp/decrypt.js'], capture_output=True, timeout=30)
        out = res.stdout.decode('utf-8','replace').strip()
        err = res.stderr.decode('utf-8','replace').strip()
        print(f"Node stdout: {out[:200]}")
        print(f"Node stderr: {err[:200]}")
        if 'itms-services' in out: return out

    return None

def download_ipa(itms_url):
    m = re.search(r'url=([^&\s"]+)', itms_url)
    if not m: print(f"No url="); return False
    plist_url = urllib.parse.unquote(m.group(1))
    print(f"plist: {plist_url}")
    r = urllib.request.urlopen(urllib.request.Request(plist_url,headers={"User-Agent":UA}), timeout=15)
    p = plistlib.loads(r.read())
    for a in p.get('items',[{}])[0].get('assets',[]):
        if a.get('kind')=='software-package':
            ipa_url = a['url']
            print(f"IPA URL: {ipa_url}")
            r2 = urllib.request.urlopen(urllib.request.Request(ipa_url,headers={"User-Agent":UA}), timeout=300)
            total = int(r2.headers.get("Content-Length",0))
            done = 0
            with open("/tmp/downloaded.ipa","wb") as f:
                while True:
                    c=r2.read(65536)
                    if not c: break
                    f.write(c); done+=len(c)
                    if total: print(f"{done*100//total}%",end="\r",flush=True)
            print(f"\nDone: {os.path.getsize('/tmp/downloaded.ipa'):,} bytes")
            return True
    return False

itms = asyncio.run(get_itms())
if itms:
    print(f"itms: {itms[:100]}")
    ok = download_ipa(itms)
    if not ok: sys.exit(1)
else:
    print("No itms"); sys.exit(1)
