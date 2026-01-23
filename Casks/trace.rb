# Homebrew Cask for Trace
# A second brain built from your digital activity

cask "trace" do
  version "0.2.6"

  on_arm do
    sha256 "1db57c57e313388ae2202bdbec0118d80e2efca9f8036ec8aafb50da33326ca7"
    url "https://github.com/junkim100/Trace/releases/download/v#{version}/Trace-#{version}-arm64.dmg"
  end

  on_intel do
    sha256 "c47082226e694f6c6d96042519b3212a7d02b60128c02e52bbe8ef50aa3ef248"
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
