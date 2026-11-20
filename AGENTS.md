# Project instructions

- Use `#testing` for every physical over-the-air transmission test. Never send
  test traffic to Public or another channel unless the user explicitly asks.
- Preserve the device identity, message history, and joined channels when
  deploying. Do not copy identity material or device credentials into Git.
- Update CHANGELOG.md for each revision and push the revision to the user's
  repository. Build/install and verify the packaged app through APPLaunch.
- Verify physical LCD refresh, not only framebuffer readback. This driver
  requires shared mapped writes for reliable panel updates.
- The test device's `/tmp` is RAM-backed. Put on-device build trees and package
  download/staging files on persistent storage (for example `~/.cache` and the
  installer's private `/var/cache/meshcore-zero`), rather than filling `/tmp`.
