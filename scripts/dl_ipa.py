#!/usr/bin/env python3
import asyncio, hashlib, base64, json, sys, os, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from playwright.async_api import async_playwright

TARGET = os.environ.get("TARGET_URL", "")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

def aes_dec(enc_b64, nonce):
    key32 = hashlib.md5((nonce + "@&!36SECRET").encode()).hexdigest()
    key = key32[:16].encode()
    iv  = key32[16:32].encode()
    c   = AES.new(key, AES.MODE_CBC, iv)
    return json.loads(unpad(c.decrypt(base64.b64decode(enc_b64)), 16).decode())

def extract_ipa_url(plist_xml):
    root = ET.fromstring(plist_xml)
    def find_url(node):
        ch = list(node)
        for i, child in enumerate(ch):
            if child.tag == "key" and child.text == "url":
                return ch[i+1].text
            r = find_url(child)
            if r:
                return r
    return find_url(root)

async def main():
    captured = {}

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(user_agent=UA)
        page = await context.new_page()

        async def on_request(req):
            h = req.headers
            nonce = h.get("x-resp-enc") or h.get("X-RESP-ENC")
            if nonce:
                url = req.url
                print(f"[REQ nonce] {url}  nonce={nonce}")
                if "download_app_info" in url:
                    captured["app_nonce"] = nonce
                elif "getPlistPath" in url:
                    captured["plist_nonce"] = nonce

        async def on_response(resp):
            url = resp.url
            try:
                body = await resp.text()
            except Exception:
                return

            if "download_app_info" in url:
                print(f"[download_app_info] {body[:200]}")
                n = captured.get("app_nonce")
                if n:
                    try:
                        d = aes_dec(body.strip(), n)
                        print(f"[decoded app_info] {json.dumps(d)[:400]}")
                        captured["app_info"] = d
                    except Exception as e:
                        print(f"[dec err] {e}")

            elif "getPlistPath" in url:
                print(f"[getPlistPath] {body[:200]}")
                n = captured.get("plist_nonce")
                if n:
                    try:
                        d = aes_dec(body.strip(), n)
                        print(f"[decoded plist] {json.dumps(d)[:400]}")
                        captured["plist_data"] = d
                    except Exception as e:
                        print(f"[dec err] {e}")
                else:
                    print(f"[no plist_nonce yet, raw={body[:100]}]")

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"[*] goto {TARGET}")
        try:
            await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"[goto] {e}")

        await asyncio.sleep(10)
        cookies = await context.cookies()
        print(f"[cookies] {[c['name'] for c in cookies]}")
        await browser.close()

    print(f"\n[captured] {list(captured.keys())}")

    plist_url = None
    if "plist_data" in captured:
        raw = captured["plist_data"].get("plistFullPath", "")
        plist_url = urllib.parse.unquote(raw)
        print(f"[plist URL] {plist_url}")

    if not plist_url or not plist_url.startswith("http"):
        print("[!] 未获取到 plist URL")
        sys.exit(1)

    req = urllib.request.Request(plist_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        plist_xml = r.read().decode()
    print(f"[plist xml] {plist_xml[:300]}")

    ipa_url = extract_ipa_url(plist_xml)
    print(f"[IPA URL] {ipa_url}")
    if not ipa_url:
        print("[!] 未能从 plist 提取 IPA URL")
        sys.exit(1)

    out = "/tmp/downloaded.ipa"
    print(f"[*] 下载 IPA -> {out}")
    req2 = urllib.request.Request(ipa_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req2, timeout=300) as r:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        with open(out, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"  {done*100//total}%", end="\r", flush=True)
    size = os.path.getsize(out)
    magic = open(out, "rb").read(4).hex()
    print(f"\n[完成] {size:,} bytes  magic={magic} {'OK' if magic=='504b0304' else 'BAD'}")

asyncio.run(main())
