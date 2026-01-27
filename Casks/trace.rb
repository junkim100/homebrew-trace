# Homebrew Cask for Trace
# A second brain built from your digital activity

cask "trace" do
  version "0.6.0"

  on_arm do
    sha256 "b1055472e880d0e7a38cd5302f061055da8901b947d23d7b127439a05e156cc8"
    url "https://github.com/junkim100/Trace/releases/download/v#{version}/Trace-#{version}-arm64.dmg"
  end

  on_intel do
    sha256 "c6485d4e7f9929e98ef09d02cbe3b455ffdf1519a24ee002d0f9278fd8d5535e"
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
