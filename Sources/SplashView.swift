import SwiftUI

struct SplashView: View {
    let onFinish: () -> Void
    /// RootView 探测到网络就设为 true，进度条立刻冲到 100% 然后结束
    @Binding var networkReady: Bool

    @State private var progress: CGFloat = 0
    @State private var pct: Int = 0
    @State private var finished = false

    private var appName: String {
        Bundle.main.infoDictionary?["CFBundleDisplayName"] as? String
            ?? Bundle.main.infoDictionary?["CFBundleName"] as? String
            ?? "App"
    }

    private var bgColor: Color {
        let info = Bundle.main.infoDictionary ?? [:]
        let r = info["SplashBgR"] as? Int ?? 26
        let g = info["SplashBgG"] as? Int ?? 30
        let b = info["SplashBgB"] as? Int ?? 46
        return Color(red: Double(r)/255, green: Double(g)/255, blue: Double(b)/255)
    }

    var body: some View {
        ZStack {
            bgColor.ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                // Logo
                Group {
                    if let img = UIImage(named: "AppLogo") {
                        Image(uiImage: img)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                    } else {
                        Image(systemName: "bolt.circle.fill")
                            .resizable()
                            .foregroundColor(.cyan)
                    }
                }
                .frame(width: 110, height: 110)
                .clipShape(Circle())
                .overlay(Circle().stroke(Color.cyan.opacity(0.4), lineWidth: 2))
                .shadow(color: .cyan.opacity(0.3), radius: 20)

                Spacer().frame(height: 28)

                Text(appName)
                    .font(.system(size: 26, weight: .bold))
                    .foregroundColor(.white)

                Spacer()

                // 进度条
                VStack(spacing: 10) {
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 3)
                                .fill(Color.white.opacity(0.15))
                                .frame(height: 4)
                            RoundedRectangle(cornerRadius: 3)
                                .fill(LinearGradient(
                                    colors: [Color(red:0.2,green:0.9,blue:0.8),
                                             Color(red:0.5,green:0.3,blue:0.9)],
                                    startPoint: .leading, endPoint: .trailing))
                                .frame(width: geo.size.width * progress, height: 4)
                        }
                    }
                    .frame(height: 4)
                    .padding(.horizontal, 48)

                    HStack {
                        Text(pct < 100 ? "Loading resources..." : "Done")
                            .font(.system(size: 12))
                            .foregroundColor(.white.opacity(0.5))
                        Spacer()
                        Text("\(pct)%")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.white.opacity(0.5))
                    }
                    .padding(.horizontal, 48)
                }
                .padding(.bottom, 60)
            }
        }
        .onAppear {
            startSlowProgress()
        }
        .onChange(of: networkReady) { ready in
            if ready { finishProgress() }
        }
    }

    /// 慢进度：从 0% 爬到 90%（等网络期间保持 < 90%）
    private func startSlowProgress() {
        let slowSteps  = 90         // 爬到 90%
        let slowTotal  = 8.0        // 8 秒爬完（可调）
        let interval   = slowTotal / Double(slowSteps)
        var step       = 0

        Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { t in
            guard !finished else { t.invalidate(); return }
            step += 1
            let raw = Double(step) / Double(slowSteps)
            // ease-out，接近 90% 时越来越慢
            let eased = 1 - pow(1 - raw, 3)
            progress = CGFloat(eased) * 0.90
            pct      = min(Int(progress * 100), 90)
            if step >= slowSteps { t.invalidate() }   // 卡在 90% 等网络
        }
    }

    /// 网络通了：快速从当前进度冲到 100%，然后回调
    private func finishProgress() {
        guard !finished else { return }
        finished = true

        let steps    = 20
        let interval = 0.04   // 0.8 秒冲完
        var step     = 0
        let start    = progress

        Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { t in
            step += 1
            let frac = Double(step) / Double(steps)
            progress = start + CGFloat(frac) * (1.0 - start)
            pct      = min(Int(progress * 100), 100)
            if step >= steps {
                t.invalidate()
                progress = 1.0
                pct      = 100
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                    onFinish()
                }
            }
        }
    }
}
