# Homebrew Cask for Trace
# A second brain built from your digital activity

cask "trace" do
  version "0.3.0"

  on_arm do
    sha256 "825e848d6afa730f24c4a9fac99c30922f33533e2609a9cbd80f7efc129ebf2f"
    url "https://github.com/junkim100/Trace/releases/download/v#{version}/Trace-#{version}-arm64.dmg"
  end

  on_intel do
    sha256 "918f00000f70c106229c4ea7e1fe7538247c855cf6dc0137b84261b3ffd5bdde"
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
