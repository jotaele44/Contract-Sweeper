#!/bin/bash
# One-time macOS fix for the PRII desktop app(s) in this folder.
#
# macOS quarantines anything downloaded from the internet and refuses to open
# apps that aren't signed with a paid Apple Developer ID / notarized by Apple
# ("cannot be opened because Apple cannot check it for malicious software" or
# "unidentified developer"). This clears that quarantine flag and ad-hoc-signs
# the bundle(s) so the app opens normally.
#
# It does NOT modify the app's behavior — it only tells THIS Mac that you trust
# this copy. Double-click this file once, then open the app as usual.
set -uo pipefail
cd "$(dirname "$0")"
shopt -s nullglob

echo "Clearing macOS quarantine in:"
echo "  $(pwd)"
echo

found=0
for app in *.app; do
  found=1
  echo "  • $app"
  xattr -dr com.apple.quarantine "$app" 2>/dev/null || true
  codesign --force --sign - "$app" >/dev/null 2>&1 || true
done
[ "$found" = 0 ] && echo "  (no .app bundle found next to this script)"

# Also clear the double-click launchers (and this helper itself).
xattr -dr com.apple.quarantine *.command *.sh 2>/dev/null || true

echo
echo "Done. Double-click the app (or its .command launcher) to start it."
[ -t 0 ] && read -r -p "Press Enter to close…" _ || true
