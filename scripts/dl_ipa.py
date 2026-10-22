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
    app_id = None

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA,
            viewport={"width": 390, "height": 844},
            extra_http_headers={
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )
        page = await context.new_page()

        async def on_response(resp):
            nonlocal ipa_url, plist_url, itms_url, download_key, base_domain, app_id
            url = resp.url
            try:
                body = await resp.text()
            except Exception:
                return

            if "getinfo" in url:
                print(f"[getinfo] {url}")
                try:
                    data = json.loads(body)
                    info = data.get("data", data)
                    download_key = info.get("downloadKey")
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    base_domain = f"{parsed.scheme}://{parsed.netloc}"
                    # 从 URL 提取 appid
                    m = re.search(r'appid=([^&]+)', url)
                    if m:
                        app_id = m.group(1)
                    print(f"  downloadKey={download_key}  appid={app_id}  base={base_domain}")
                    print(f"  installMode={info.get('installMode')}  downloadMode={info.get('downloadMode')}")
                except Exception as e:
                    print(f"  parse err: {e}, body={body[:100]}")

            if "plist" in url.lower() and resp.status == 200 and len(body) > 100:
                print(f"[PLIST] {url}")
                plist_url = url

            if ".ipa" in url and resp.status in [200, 302]:
                print(f"[IPA] {url}")
                ipa_url = url

        def on_request(req):
            nonlocal itms_url
            url = req.url
            if "itms-services" in url:
                print(f"[ITMS] {url}")
                itms_url = url

        page.on("response", on_response)
        page.on("request", on_request)

        print(f"[*] 访问 {TARGET}")
        try:
            await page.goto(TARGET, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"[goto] {e}")

        # 等 React 初始化和 API 完成
        print("[*] 等待 25 秒...")
        await asyncio.sleep(25)

        print(f"[*] downloadKey={download_key}  base={base_domain}")

        # 打印页面文字
        try:
            texts = await page.evaluate("""
                () => Array.from(document.querySelectorAll('*'))
                    .filter(e => !e.children.length && e.innerText && e.innerText.trim().length > 0 && e.innerText.trim().length < 80)
                    .map(e => e.innerText.trim())
                    .slice(0, 20)
            """)
            print(f"[页面文字] {texts}")
        except Exception:
            pass

        # 用 JS 直接调用下载函数
        print("[*] 尝试 JS 触发下载...")
        try:
            result = await page.evaluate("""
                () => {
                    // 找所有函数和对象中包含 download/install 的
                    const found = [];
                    for (const key of Object.keys(window)) {
                        if (typeof window[key] === 'function') {
                            const s = window[key].toString();
                            if (s.includes('downloadKey') || s.includes('itms-services') || s.includes('plist')) {
                                found.push(key);
                            }
                        }
                    }
                    return found;
                }
            """)
            print(f"[JS funcs] {result}")
        except Exception as e:
            print(f"[JS] {e}")

        # 点击所有按钮
        print("[*] 点击所有可见元素...")
        try:
            count = await page.evaluate("""
                () => {
                    const clickable = document.querySelectorAll('button, a, [onclick], [role=button]');
                    clickable.forEach(el => {
                        try { el.click(); } catch(e) {}
                    });
                    return clickable.length;
                }
            """)
            print(f"  点击了 {count} 个元素")
        except Exception:
            pass

        await asyncio.sleep(5)

        # 检查页面内容中是否有 plist/ipa/itms
        content = await page.content()
        for pattern, label in [
            (r'itms-services://[^\s"\'<>&\\]+', "itms"),
            (r'https?://[^\s"\'<>&\\]+\.plist[^\s"\'<>&\\]*', "plist"),
            (r'https?://[^\s"\'<>&\\]+\.ipa[^\s"\'<>&\\]*', "ipa"),
            (r'https?://[^\s"\'<>&\\]+/ipa/[^\s"\'<>&\\]+', "ipa-path"),
        ]:
            for m in re.findall(pattern, content):
                print(f"[{label} in HTML] {m}")
                if label == "itms" and not itms_url:
                    itms_url = m
                elif label == "plist" and not plist_url:
                    plist_url = m
                elif label in ("ipa", "ipa-path") and not ipa_url:
                    ipa_url = m

        await browser.close()

    print(f"\n[summary] key={download_key} itms={itms_url} plist={plist_url} ipa={ipa_url}")

    # 用 downloadKey 尝试已知的 API 路径（参考平台常见格式）
    if download_key and base_domain and not ipa_url and not plist_url:
        paths = [
            f"/clientapi/app/ipa?downloadKey={download_key}&appid={app_id or ''}",
            f"/clientapi/app/plist?downloadKey={download_key}",
            f"/clientapi/ipa/plist?downloadKey={download_key}",
            f"/clientapi/app/manifest?downloadKey={download_key}",
            f"/ipa/plist?downloadKey={download_key}",
            f"/plist?downloadKey={download_key}",
        ]
        for path in paths:
            url = base_domain + path
            print(f"[*] 试 {url}")
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": UA,
                    "Referer": base_domain,
                    "Accept": "application/json, text/plain, */*",
                })
                with urllib.request.urlopen(req, timeout=10) as r:
                    rb = r.read().decode()
                print(f"  OK -> {rb[:300]}")
                try:
                    d = json.loads(rb)
                    inner = d.get("data") or d
                    candidate_ipa = inner.get("url") or inner.get("downloadUrl") or inner.get("ipaUrl")
                    candidate_plist = inner.get("plistUrl") or inner.get("plist")
                    if candidate_ipa:
                        ipa_url = candidate_ipa
                        break
                    if candidate_plist:
                        plist_url = candidate_plist
                        break
                except Exception:
                    if "plist" in rb and "<?xml" in rb:
                        plist_url = url
                        break
                    if rb.startswith("https://") and ".ipa" in rb:
                        ipa_url = rb.strip()
                        break
            except Exception as e:
                print(f"  err: {e}")

    # itms -> plist -> IPA
    if itms_url and not ipa_url and not plist_url:
        m = re.search(r'url=([^&\s"\']+)', itms_url)
        if m:
            plist_url = urllib.parse.unquote(m.group(1))
            print(f"[plist from itms] {plist_url}")

    if plist_url and not ipa_url:
        print(f"[*] 获取 plist: {plist_url}")
        req = urllib.request.Request(plist_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            xml_data = r.read().decode()
        print(f"[plist] {xml_data[:400]}")
        ipa_url = extract_ipa_url(xml_data)
        print(f"[IPA URL] {ipa_url}")

    if not ipa_url:
        print("[!] 未获取 IPA URL")
        sys.exit(1)

    out = "/tmp/downloaded.ipa"
    print(f"\n[*] 下载: {ipa_url}")
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
                    print(f"  {done*100//total}%  {done//1024//1024}MB/{total//1024//1024}MB", end="\r", flush=True)
    size = os.path.getsize(out)
    magic = open(out, "rb").read(4).hex()
    print(f"\n[完成] {size:,} bytes  magic={magic} {'OK' if magic=='504b0304' else 'BAD'}")

asyncio.run(main())
