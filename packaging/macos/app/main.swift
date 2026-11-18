import Cocoa
import WebKit

let consoleURL = URL(string: "http://127.0.0.1:8765/")!

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var retryTimer: Timer?
    var failures = 0

    func applicationDidFinishLaunching(_ notification: Notification) {
        let rect = NSRect(x: 0, y: 0, width: 1080, height: 760)
        window = NSWindow(contentRect: rect,
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered,
                          defer: false)
        window.title = "Autonode"
        window.minSize = NSSize(width: 720, height: 520)
        window.center()
        window.setFrameAutosaveName("AutonodeMainWindow")

        let config = WKWebViewConfiguration()
        webView = WKWebView(frame: rect, configuration: config)
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        window.contentView = webView

        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        load()
    }

    func load() {
        var request = URLRequest(url: consoleURL)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        webView.load(request)
    }

    func retryLater() {
        guard retryTimer == nil else { return }
        retryTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: false) { _ in
            self.retryTimer = nil
            self.load()
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        failures = 0
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        failures += 1
        retryLater()
    }

    func webView(_ webView: WKWebView,
                 didFailProvisionalNavigation navigation: WKNavigation!,
                 withError error: Error) {
        failures += 1
        if failures == 3 {
            let html = """
            <html><head><meta http-equiv="refresh" content="3;url=http://127.0.0.1:8765/"></head>
            <body style="background:#0f1115;color:#8b93a7;font:14px -apple-system;padding:60px;text-align:center">
            <h2 style="color:#e6e9ef">连不上 Autonode 服务</h2>
            <p>后台服务可能没有运行，每 3 秒会自动重试。</p>
            <p><button onclick="location.href='http://127.0.0.1:8765/'" style="padding:8px 18px;border-radius:8px;border:1px solid #2a2f3a;background:#1a1e26;color:#e6e9ef;font-size:13px">立即重试</button></p>
            <p>仍无法连接时，在终端执行：<br><code style="color:#4c8dff">launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.autonode.plist</code></p>
            <p>或重新运行安装包。</p>
            </body></html>
            """
            webView.loadHTMLString(html, baseURL: nil)
        }
        retryLater()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
