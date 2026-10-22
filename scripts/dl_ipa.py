#!/usr/bin/env python3
"""
直接下载流程：
1. 访问落地页取 appid
2. 调 getinfo 取 downloadKey
3. 调 inhouse 取 itms-services URL（明文，不走浏览器加密）
4. 解析 plist 取 IPA URL
5. 下载 IPA
"""
import asyncio, sys, os, re, urllib.request, urllib.parse, json
import xml.etree.ElementTree as ET
from playwright.async_api import async_playwright

TARGET = os.environ.get("TARGET_URL", "")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"


def http_get(url, headers=None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")


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


async def get_download_key_via_playwright(target_url):
    """用 Playwright 加载页面，获取 base_domain、appid 和 downloadKey"""
    result = {}
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA,
            viewport={"width": 390, "height": 844},
            extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
        )
        await context.add_init_script("""
            () => {
                Object.defineProperty(navigator, 'platform', {get: () => 'iPhone'});
                Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 5});
            }
        """)
        page = await context.new_page()

        async def on_response(resp):
            url = resp.url
            if "getinfo" in url:
                try:
                    body = await resp.text()
                    data = json.loads(body)
                    info = data.get("data", data)
                    result["downloadKey"] = info.get("downloadKey")
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    result["base"] = f"{parsed.scheme}://{parsed.netloc}"
                    m = re.search(r"appid=([^&]+)", url)
                    if m:
                        result["appid"] = m.group(1)
                    print(f"[getinfo] key={result['downloadKey']}  base={result['base']}  appid={result.get('appid')}")
                except Exception as e:
                    print(f"[getinfo err] {e}")

        page.on("response", on_response)
        try:
            await page.goto(target_url, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"[goto] {e}")
        await asyncio.sleep(10)
        await browser.close()
    return result


def main():
    print(f"[*] 目标: {TARGET}")

    # Step 1: 获取 downloadKey
    print("[*] 获取 downloadKey...")
    info = asyncio.run(get_download_key_via_playwright(TARGET))

    if not info.get("downloadKey"):
        print("[!] 未获取 downloadKey")
        sys.exit(1)

    download_key = info["downloadKey"]
    base = info["base"]
    appid = info.get("appid", "")
    print(f"[*] downloadKey={download_key}")

    # Step 2: 调用 inhouse API（curl 方式，返回明文 itms URL）
    # 注意: 不加 zh=1 参数，否则服务器返回 AES 加密数据
    inhouse_url = f"{base}/clientapi/app/inhouse?appid={appid}&k={download_key}&c=&lang=zh_CN"
    print(f"[*] 调 inhouse: {inhouse_url}")
    body = http_get(inhouse_url)
    print(f"[inhouse resp] {body[:300]}")

    data = json.loads(body)
    itms_or_url = data.get("data", "")

    if not itms_or_url:
        print("[!] inhouse 返回空")
        sys.exit(1)

    print(f"[inhouse data] {itms_or_url}")

    # Step 3: 从 itms-services 提取 plist URL
    plist_url = None
    if "itms-services" in itms_or_url:
        m = re.search(r"url=([^&\s]+)", itms_or_url)
        if m:
            plist_url = urllib.parse.unquote(m.group(1))
    elif itms_or_url.startswith("http"):
        plist_url = itms_or_url

    if not plist_url:
        print("[!] 未获取 plist URL")
        sys.exit(1)

    print(f"[*] plist URL: {plist_url}")
    plist_xml = http_get(plist_url)
    print(f"[plist] {plist_xml[:300]}")

    # Step 4: 从 plist 提取 IPA URL
    ipa_url = extract_ipa_url(plist_xml)
    if not ipa_url:
        print("[!] 未从 plist 提取 IPA URL")
        sys.exit(1)

    print(f"[*] IPA URL: {ipa_url}")

    # Step 5: 下载 IPA
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
                    print(f"  {done*100//total}%  {done//1024//1024}MB/{total//1024//1024}MB", end="\r", flush=True)

    size = os.path.getsize(out)
    magic = open(out, "rb").read(4).hex()
    print(f"\n[完成] {size:,} bytes  magic={magic} {'OK' if magic=='504b0304' else 'BAD'}")


main()
