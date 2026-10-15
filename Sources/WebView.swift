import SwiftUI
import WebKit

class WebStore: NSObject, ObservableObject, WKNavigationDelegate {
    /// 独立进程池：SDWebuiopser 采集完毕释放钩子后，
    /// 后续 H5 网络请求走此独立池，与主 app 进程完全隔离
    private static let isolatedPool = WKProcessPool()

    let webView: WKWebView
    private var pendingURL: String?

    override init() {
        let cfg = WKWebViewConfiguration()
        cfg.processPool = WebStore.isolatedPool
        cfg.allowsInlineMediaPlayback = true
        cfg.mediaTypesRequiringUserActionForPlayback = []

        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.scrollView.bounces = false
        wv.scrollView.showsVerticalScrollIndicator = false
        wv.isOpaque = false
        webView = wv
        super.init()
        wv.navigationDelegate = self
    }

    /// 由 RootView 在 acqhook_done 之后调用
    func load(_ urlStr: String) {
        guard let url = URL(string: urlStr) else { return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 30
        req.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        webView.load(req)
    }

    // 加载失败 3 秒后重试
    func webView(_ wv: WKWebView,
                 didFailProvisionalNavigation _: WKNavigation!,
                 withError error: Error) {
        let url = wv.url?.absoluteString ?? ""
        guard !url.isEmpty, url != "about:blank" else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
            wv.reload()
        }
    }
}

struct WebView: UIViewRepresentable {
    @ObservedObject var store: WebStore

    func makeUIView(context: Context) -> WKWebView { store.webView }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
}
