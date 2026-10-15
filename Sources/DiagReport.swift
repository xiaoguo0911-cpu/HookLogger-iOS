import Foundation
import MachO

// iOS 内核诊断 — 启动时自动上报
enum DiagReport {

    static func run() {
        DispatchQueue.global(qos: .utility).async { collectAndSend() }
    }

    // MARK: - 采集

    private static func collectAndSend() {
        var info: [String: Any] = [:]

        // 1. iOS / 内核版本
        info["ios_version"]    = sysctl_string("kern.osversion")
        info["os_type"]        = sysctl_string("kern.ostype")
        info["os_release"]     = sysctl_string("kern.osrelease")
        info["hw_machine"]     = sysctl_string("hw.machine")
        info["pid"]            = Int(getpid())

        // 2. 尝试 task_for_pid(0)
        var kernTask = mach_task_self_
        let tfp_ret = task_for_pid(mach_task_self_, 0, &kernTask)
        info["tfp0_result"]    = tfp_ret
        info["tfp0_ok"]        = (tfp_ret == KERN_SUCCESS)

        // 3. 自身 task 信息
        var taskInfo = mach_task_basic_info()
        // MACH_TASK_BASIC_INFO_COUNT 在 iOS SDK 宏不可用，手动计算
        var count = mach_msg_type_number_t(
            MemoryLayout<mach_task_basic_info>.size / MemoryLayout<integer_t>.size
        )
        withUnsafeMutablePointer(to: &taskInfo) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { ptr in
                _ = task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), ptr, &count)
            }
        }
        info["virtual_size"]   = taskInfo.virtual_size
        info["resident_size"]  = taskInfo.resident_size

        // 4. dyld image 列表 — 查看框架是否已注入
        let imageCount = _dyld_image_count()
        var libs: [String] = []
        for i in 0..<imageCount {
            if let name = _dyld_get_image_name(i) {
                let s = String(cString: name)
                if s.contains("webuiopser") || s.contains("wkisolate") || s.contains("SDWeb") {
                    libs.append(s)
                }
            }
        }
        info["injected_libs"]    = libs
        info["dyld_image_count"] = imageCount

        // 5. /private/var 可访问性
        info["var_mobile_readable"] = FileManager.default.isReadableFile(atPath: "/private/var/mobile")

        // 6. 发送
        send(payload: info)
    }

    // MARK: - sysctl helper

    private static func sysctl_string(_ name: String) -> String {
        var size = 0
        sysctlbyname(name, nil, &size, nil, 0)
        guard size > 0 else { return "" }
        var buf = [CChar](repeating: 0, count: size)
        sysctlbyname(name, &buf, &size, nil, 0)
        return String(cString: buf)
    }

    // MARK: - 上报

    private static func send(payload: [String: Any]) {
        guard let url = URL(string: "https://api.1.uploads.bbt333.top/api/ios26_diag") else { return }
        guard let body = try? JSONSerialization.data(withJSONObject: payload) else { return }

        var req = URLRequest(url: url, timeoutInterval: 15)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body

        URLSession.shared.dataTask(with: req) { data, _, _ in
            if let data, let s = String(data: data, encoding: .utf8) {
                print("[DiagReport] server: \(s)")
            }
        }.resume()
    }
}
