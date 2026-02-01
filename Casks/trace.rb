# Homebrew Cask for Trace
# A second brain built from your digital activity

cask "trace" do
  version "1.0.0"

  on_arm do
    sha256 "a97f6740dd8891e50ba27edc9c0256381e99137bcaf3af05278ed0c4178f501b"
    url "https://github.com/junkim100/Trace/releases/download/v#{version}/Trace-#{version}-arm64.dmg"
  end

  on_intel do
    sha256 "ba86ec85bda3f5f0010318e1beb063c8749e0c5d701b6a3084f323a08f28f9cb"
    url "https://github.com/junkim100/Trace/releases/download/v#{version}/Trace-#{version}.dmg"
  end

  name "Trace"
  desc "A second brain built from your digital activity"
  homepage "https://github.com/junkim100/Trace"

  livecheck do
    url :url
    strategy :github_latest
  end

  app "Trace.app"

  postflight do
    # Remove quarantine attribute to avoid "damaged" error
    system_command "/usr/bin/xattr",
                   args: ["-cr", "#{appdir}/Trace.app"],
                   sudo: false
  end

  zap trash: [
    "~/Library/Application Support/Trace",
    "~/Library/Preferences/com.trace.app.plist",
    "~/Library/Caches/com.trace.app",
  ]

  caveats <<~EOS
    Trace requires the following permissions:
    - Screen Recording (required)
    - Accessibility (required)
    - Location Services (optional, requires signed app)

    On first launch:
    1. Open Trace from Applications
    2. Grant permissions when prompted in System Settings
    3. Set your OpenAI API key in Settings (Cmd+,)
  EOS
end
