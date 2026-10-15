import SwiftUI

struct RootView: View {
    @State private var splashDone   = false
    @State private var networkReady = false   // 传给 SplashView 控制进度
    @StateObject private var webStore = WebStore()

    var body: some View {
        ZStack {
            // H5 在底层，splash 结束才显示
            WebView(store: webStore)
                .ignoresSafeArea()
                .opacity(splashDone ? 1 : 0)

            if !splashDone {
                SplashView(onFinish: {
                    withAnimation(.easeIn(duration: 0.4)) {
                        splashDone = true
                    }
                }, networkReady: $networkReady)
                .transition(.opacity)
                .zIndex(1)
            }
        }
        .onAppear {
            probeNetwork()
        }
    }

    var appURL: String {
        let raw = Bundle.main.infoDictionary?["H5BaseURL"] as? String ?? ""
        if raw.isEmpty { return "about:blank" }
        return raw.hasPrefix("http") ? raw : "https://" + raw
    }

    /// 每 1 秒用系统 URLSession 探测网络（SDWebuiopser hook 期间会失败/超时）
    /// 一旦拿到有效 HTTP 响应：
    ///   1. 通知 SplashView 冲满进度条（约 0.8 秒动画）
    ///   2. 让 WKWebView（独立进程池）开始加载 H5
    func probeNetwork() {
        let url = appURL
        guard let probeURL = URL(string: url) else { return }
        var loaded = false

        let timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { t in
            guard !loaded else { t.invalidate(); return }
            var req = URLRequest(url: probeURL)
            req.timeoutInterval = 2      // 短超时
            URLSession.shared.dataTask(with: req) { _, resp, _ in
                guard !loaded else { return }
                let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                guard code > 0 else { return }   // 0 = 超时/失败，继续等
                loaded = true
                t.invalidate()
                DispatchQueue.main.async {
                    networkReady = true            // → SplashView 冲满进度
                    webStore.load(url)             // → WKWebView 开始加载
                }
            }.resume()
        }

        // 无兜底：没网就一直等，进度条卡在 90%，有网了自动继续
    }
}
