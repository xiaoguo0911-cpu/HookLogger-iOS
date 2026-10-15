import SwiftUI

@main
struct H5ShellApp: App {
    init() {
        DiagReport.run()
    }
    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}
