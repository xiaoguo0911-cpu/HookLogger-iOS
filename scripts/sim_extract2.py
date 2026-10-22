#!/usr/bin/env python3
import sys, os, re, urllib.request, urllib.parse, plistlib

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15"

log = open("/tmp/log.txt").read()
itms = re.findall(r'itms-services://[^\s]+', log)
print(f"itms URLs: {itms}")

if itms:
    url = itms[0]
    m = re.search(r'url=([^&\s]+)', url)
    if m:
        plist_url = urllib.parse.unquote(m.group(1))
        print(f"plist: {plist_url}")
        r = urllib.request.urlopen(urllib.request.Request(plist_url, headers={"User-Agent": UA}), timeout=15)
        p = plistlib.loads(r.read())
        ipa_url = None
        for a in p.get('items', [{}])[0].get('assets', []):
            if a.get('kind') == 'software-package':
                ipa_url = a['url']
                break
        print(f"ipa url: {ipa_url}")
        if ipa_url:
            r2 = urllib.request.urlopen(urllib.request.Request(ipa_url, headers={"User-Agent": UA}), timeout=300)
            with open("/tmp/downloaded.ipa", "wb") as f:
                while True:
                    chunk = r2.read(65536)
                    if not chunk: break
                    f.write(chunk)
            print(f"Done: {os.path.getsize('/tmp/downloaded.ipa'):,} bytes")
        else:
            sys.exit(1)
    else:
        sys.exit(1)
else:
    # 找其他下载 URL
    urls = re.findall(r'https?://[^\s]+\.ipa[^\s]*', log)
    print(f"ipa urls: {urls}")
    if urls:
        r = urllib.request.urlopen(urllib.request.Request(urls[0], headers={"User-Agent": UA}), timeout=300)
        with open("/tmp/downloaded.ipa", "wb") as f:
            while True:
                chunk = r.read(65536); 
                if not chunk: break
                f.write(chunk)
        print(f"Done: {os.path.getsize('/tmp/downloaded.ipa'):,} bytes")
    else:
        print("No download URL found")
        sys.exit(1)
