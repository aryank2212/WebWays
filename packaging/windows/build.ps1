# Build the portable folder + zip (and the installer if Inno Setup's iscc is on PATH). Run from the repo root.
#   py -3.12 -m venv .venv; .\.venv\Scripts\pip install libtorrent aiohttp cryptography pyinstaller
#   cd ui; npm ci; npm run build; cd ..
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
$ErrorActionPreference = "Stop"
$py = if (Test-Path .\.venv\Scripts\python.exe) { ".\.venv\Scripts\python.exe" } else { "python" }
$version = & $py -c "import sys; sys.path[:0]=['core','protocol']; import webways_core; print(webways_core.__version__)"
if (-not (Test-Path ui\dist\index.html)) { throw "ui\dist is missing: run 'npm run build' in ui first" }

$commit = (git rev-parse --short HEAD 2>$null)
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $py -m PyInstaller --noconfirm --clean --name WebWays --icon packaging\windows\webways.ico `
  --paths protocol --paths indexer --paths core `
  --add-data "ui\dist;ui\dist" --collect-all libtorrent `
  --hidden-import webways_core.cli --hidden-import webways_indexer.cli `
  packaging\windows\entry.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# licenses, notices and the source offer travel with every binary
$out = "dist\WebWays"
New-Item -ItemType Directory -Force "$out\licenses" | Out-Null
Copy-Item LICENSE.md, THIRD_PARTY_NOTICES.md "$out\licenses\"
Copy-Item core\LICENSE "$out\licenses\LICENSE-GPL-3.0.txt"
Copy-Item indexer\LICENSE "$out\licenses\LICENSE-AGPL-3.0.txt"
Copy-Item protocol\LICENSE "$out\licenses\LICENSE-Apache-2.0.txt"
Copy-Item packaging\windows\README.txt "$out\README.txt"
"WebWays $version`ncommit $commit`nbuilt $(Get-Date -Format s)" | Set-Content "$out\BUILD-INFO.txt"

$zip = "dist\WebWays-$version-windows-x64.zip"
Compress-Archive -Path "$out\*" -DestinationPath $zip -Force
Write-Host "portable: $zip"

if (Get-Command iscc -ErrorAction SilentlyContinue) {
  iscc "/DAppVersion=$version" packaging\windows\webways.iss
  if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
  Write-Host "installer: dist-installer\WebWays-Setup-$version.exe"
} else { Write-Host "iscc not found: skipped installer (install Inno Setup 6 to build it)" }
