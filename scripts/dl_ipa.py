#!/usr/bin/env python3
import asyncio, sys, os, re, urllib.request, urllib.parse, json
import xml.etree.ElementTree as ET
from playwright.async_api import async_playwright

TARGET = os.environ.get("TARGET_URL", "")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

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
    ipa_url = None
    plist_url = None
    itms_url = None
    download_key = None
    base_domain = None

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(user_agent=UA, viewport={"width": 390, "height": 844})
        page = await context.new_page()

        async def on_response(resp):
            nonlocal ipa_url, plist_url, itms_url, download_key, base_domain
            url = resp.url
            try:
                body = await resp.text()
            except Exception:
                return

            if "getinfo" in url or "app/info" in url:
                print(f"[getinfo] {url}")
                print(f"  body: {body[:400]}")
                try:
                    data = json.loads(body)
                    info = data.get("data", data)
                    download_key = info.get("downloadKey") or info.get("download_key")
                    print(f"  downloadKey={download_key}")
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    base_domain = f"{parsed.scheme}://{parsed.netloc}"
                except Exception:
                    pass

            if "plist" in url.lower() and resp.status == 200:
                print(f"[PLIST] {url}")
                plist_url = url

            if ".ipa" in url and resp.status in [200, 302]:
                print(f"[IPA] {url}")
                ipa_url = url

        page.on("response", on_response)

        print(f"[*] goto {TARGET}")
        try:
            await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"[goto] {e}")

        await asyncio.sleep(5)

        # 点击下载按钮
        print("[*] 找下载按钮...")
        clicked = False
        for selector in ["button", "a", "[class*='download']", "[class*='btn']"]:
            try:
                for el in await page.query_selector_all(selector):
                    text = (await el.inner_text()).strip()
                    href = await el.get_attribute("href") or ""
                    if any(w in text for w in ["下载", "安装", "Install", "Download", "获取"]) or "itms" in href:
                        print(f"  >> 点击: {text!r}")
                        await el.click()
                        await asyncio.sleep(3)
                        clicked = True
                        break
            except Exception:
                pass
            if clicked:
                break

        await asyncio.sleep(5)

        # 扫描页面内容
        content = await page.content()
        for pattern, label in [
            (r'itms-services://[^\s"\'<>]+', "itms"),
            (r'https?://[^\s"\'<>]+\.plist[^\s"\'<>]*', "plist"),
            (r'https?://[^\s"\'<>]+\.ipa[^\s"\'<>]*', "ipa"),
        ]:
            matches = re.findall(pattern, content)
            if matches:
                print(f"[{label} in page] {matches[0]}")
                if label == "itms" and not itms_url:
                    itms_url = matches[0]
                elif label == "plist" and not plist_url:
                    plist_url = matches[0]
                elif label == "ipa" and not ipa_url:
                    ipa_url = matches[0]

        # 打印所有链接
        links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a,button')).map(e => ({
                t: e.innerText.trim().substring(0,40), h: e.href||''
            })).filter(e => e.t || e.h)
        """)
        print(f"[links] {links[:8]}")

        await browser.close()

    print(f"\n[summary] key={download_key} base={base_domain} plist={plist_url} ipa={ipa_url} itms={itms_url}")

    # 用 downloadKey 试各种下载 API
    if download_key and base_domain and not ipa_url:
        for path in [
            f"/clientapi/app/ipaurl?downloadKey={download_key}",
            f"/clientapi/ipa/download?key={download_key}",
            f"/ipa/url?key={download_key}",
        ]:
            url = base_domain + path
            print(f"[*] 试 {url}")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=10) as r:
                    rb = r.read().decode()
                print(f"  -> {rb[:200]}")
                d = json.loads(rb)
                candidate = d.get("url") or d.get("downloadUrl") or (d.get("data") or {}).get("url")
                if candidate:
                    ipa_url = candidate
                    break
            except Exception as e:
                print(f"  err: {e}")

    # 从 itms 提取 plist
    if itms_url and not ipa_url:
        m = re.search(r'url=([^&\s"\']+)', itms_url)
        if m:
            plist_url = urllib.parse.unquote(m.group(1))
            print(f"[*] itms plist: {plist_url}")

    # 从 plist 获取 IPA URL
    if plist_url and not ipa_url:
        print(f"[*] 获取 plist: {plist_url}")
        req = urllib.request.Request(plist_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            plist_xml = r.read().decode()
        print(f"[plist] {plist_xml[:300]}")
        ipa_url = extract_ipa_url(plist_xml)
        print(f"[IPA URL] {ipa_url}")

    if not ipa_url:
        print("[!] 未能获取 IPA URL")
        sys.exit(1)

    out = "/tmp/downloaded.ipa"
    print(f"[*] 下载 -> {out}")
    req = urllib.request.Request(ipa_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
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
