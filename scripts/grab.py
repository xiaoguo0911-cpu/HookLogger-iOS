#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib, hashlib, base64
from playwright.async_api import async_playwright
try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ImportError:
    print("need pycryptodome"); sys.exit(1)

TARGET = os.environ.get("TARGET_URL","")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
BASE = "https://doe29x10dqvat.cloudfront.net"

def aes_dec(enc_b64, key_str):
    # 标准 AES CBC 解密，key 直接用字符串 (先试不同方法)
    # 方法1: key = key_str[:16], iv = key_str[16:32]
    try:
        key = key_str[:16].encode() if len(key_str) >= 32 else key_str.encode().ljust(16,b'\0')[:16]
        iv  = key_str[16:32].encode() if len(key_str) >= 32 else b'\0'*16
        c = AES.new(key, AES.MODE_CBC, iv)
        return unpad(c.decrypt(base64.b64decode(enc_b64)), 16).decode()
    except Exception as e:
        return f"err1: {e}"

def aes_dec2(enc_b64, nonce):
    # 方法2: 艳池风格 MD5(nonce + SECRET)
    for secret in ["@&!36SECRET", "@&!36secret", "secret", "12345678"]:
        try:
            key32 = hashlib.md5((nonce + secret).encode()).hexdigest()
            key = key32[:16].encode()
            iv  = key32[16:32].encode()
            c   = AES.new(key, AES.MODE_CBC, iv)
            return unpad(c.decrypt(base64.b64decode(enc_b64)), 16).decode()
        except: pass
    return None

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
        await page.goto(BASE+"/1cfhnSTQ1T3tLpjtE", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(15)
        xhr = await page.evaluate("()=>window.__log||[]")
        await browser.close()

    dk = None
    inhouse_resp = None
    inhouse_k = None

    for e in xhr:
        print(f"XHR [{e['status']}] {e['url']}")
        if 'getinfo' in e['url'] and 'downloadKey' in e.get('resp',''):
            try: dk = json.loads(e['resp'])['data']['downloadKey']
            except: pass
        if 'inhouse' in e['url']:
            inhouse_resp = e.get('resp','')
            # 从 URL 提取 k 参数
            m = re.search(r'[?&]k=([^&]+)', e['url'])
            if m: inhouse_k = m.group(1)
            print(f"  inhouse k={inhouse_k}")
            print(f"  inhouse resp={inhouse_resp[:200]}")

    if not inhouse_resp:
        print("no inhouse response"); sys.exit(1)

    # 解密 inhouse 响应
    try:
        resp_data = json.loads(inhouse_resp)
        enc = resp_data.get('data','')
        print(f"\nencrypted data: {enc[:50]}...")
    except:
        enc = inhouse_resp
        print(f"\nraw resp: {enc[:100]}")

    print(f"\ndownloadKey (as nonce): {dk}")
    print(f"inhouse k: {inhouse_k}")

    # 尝试解密
    for nonce in [dk, inhouse_k, dk.split('_')[1] if dk and '_' in dk else None]:
        if not nonce: continue
        result = aes_dec2(enc, nonce)
        if result:
            print(f"\nDECRYPTED with nonce={nonce}:")
            print(result[:500])
            # 找 itms 或 plist 或 ipa
            itms = re.findall(r'itms-services://[^\s"\']+', result)
            plists = re.findall(r'https?://[^\s"\']+\.plist[^\s"\']*', result)
            ipas = re.findall(r'https?://[^\s"\']+\.ipa[^\s"\']*', result)
            print(f"itms: {itms}\nplists: {plists}\nipas: {ipas}")
            if itms:
                download_from_itms(itms[0])
            elif plists:
                download_from_plist(plists[0])
            elif ipas:
                download_ipa(ipas[0])
            break
        else:
            print(f"dec failed with nonce={nonce[:20]}...")

    # 也试试 k 直接作为 key
    print(f"\ntrying direct key dec...")
    result = aes_dec(enc, inhouse_k or "")
    print(f"direct: {result[:100]}")

def download_from_itms(itms_url):
    m = re.search(r'url=([^&\s"]+)', itms_url)
    if m:
        plist_url = urllib.parse.unquote(m.group(1))
        download_from_plist(plist_url)

def download_from_plist(plist_url):
    print(f"plist: {plist_url}")
    r = urllib.request.urlopen(urllib.request.Request(plist_url, headers={"User-Agent": UA}), timeout=15)
    p = plistlib.loads(r.read())
    for a in p.get('items',[{}])[0].get('assets',[]):
        if a.get('kind')=='software-package':
            download_ipa(a['url'])
            break

def download_ipa(url):
    print(f"IPA URL: {url}")
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300)
    total = int(r.headers.get("Content-Length", 0))
    done = 0
    with open("/tmp/downloaded.ipa", "wb") as f:
        while True:
            c = r.read(65536)
            if not c: break
            f.write(c); done += len(c)
            if total: print(f"{done*100//total}%", end="\r", flush=True)
    print(f"\nDone: {os.path.getsize('/tmp/downloaded.ipa'):,} bytes")

asyncio.run(main())
