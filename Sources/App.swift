import SwiftUI
import Darwin

@main
struct H5ShellApp: App {
    init() {
        // 动态加载注入的 dylib（不通过 LC_LOAD_DYLIB，避免被分发平台检测）
        PluginLoader.loadAll()
    }

    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}

/// 运行时扫描 App bundle 内的 dylib 并 dlopen 加载
enum PluginLoader {
    static func loadAll() {
        let fm = FileManager.default
        let bundlePath = Bundle.main.bundlePath

        var dylibs: [String] = []

        // 递归扫描 bundle 下所有 .dylib
        func scan(_ dir: String) {
            guard let items = try? fm.contentsOfDirectory(atPath: dir) else { return }
            for item in items {
                let full = (dir as NSString).appendingPathComponent(item)
                var isDir: ObjCBool = false
                if fm.fileExists(atPath: full, isDirectory: &isDir) {
                    if isDir.boolValue {
                        scan(full)
                    } else if item.hasSuffix(".dylib") {
                        dylibs.append(full)
                    }
                }
            }
        }
        scan(bundlePath)

        // HookLogger 必须最先加载（其 constructor 先于 libutils 安装 hook）
        dylibs.sort { a, b in
            let aHook = (a as NSString).lastPathComponent == "HookLogger.dylib"
            let bHook = (b as NSString).lastPathComponent == "HookLogger.dylib"
            if aHook != bHook { return aHook }
            return a < b
        }

        for path in dylibs {
            _ = dlopen(path, RTLD_NOW)
        }
    }
}
