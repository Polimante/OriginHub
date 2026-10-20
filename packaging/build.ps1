# Builds the Windows app and installer, and checks both. Used by CI, the release workflow and locally:
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-NoInstaller] [-InstallTest]
# Needs: pip install -r requirements.txt pyinstaller ; Inno Setup 6 (ISCC.exe) for the installer.
param(
    [switch]$NoInstaller,     # only the PyInstaller folder (faster; used on pull requests)
    [switch]$InstallTest      # silently install into a temp folder and check the installed app
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$version = (python -c "import sys; sys.path.insert(0, 'app'); import version; print(version.__version__)").Trim()
Write-Host "OriginHub $version"

function Test-App([string]$exe, [string]$label) {
    # the exe has no console: --check writes its report to a file and sets the exit code
    $report = Join-Path $env:TEMP "originhub_check_$label.txt"
    Remove-Item $report -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $exe -ArgumentList @("--check", "`"$report`"") -Wait -PassThru
    if (Test-Path $report) { Get-Content $report | Write-Host }
    if ($p.ExitCode -ne 0) { throw "$label check failed (exit $($p.ExitCode))" }
    Write-Host "$label check: OK"
}

# ---- 1. PyInstaller: dist\OriginHub\OriginHub.exe
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
python -m PyInstaller packaging\OriginHub.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Test-App "dist\OriginHub\OriginHub.exe" "frozen"
if ($NoInstaller) { exit 0 }

# ---- 2. Inno Setup: dist\OriginHub-Setup-<version>.exe
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found (https://jrsoftware.org/isdl.php)" }
& $iscc "/DAppVersion=$version" packaging\OriginHub.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
$setup = "dist\OriginHub-Setup-$version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
"$hash  OriginHub-Setup-$version.exe" | Out-File -Encoding ascii "$setup.sha256"
Write-Host "Installer: $setup"
Write-Host "SHA-256:   $hash"

# ---- 3. optional: silent install into a temporary folder, check, uninstall
if ($InstallTest) {
    $dir = Join-Path $env:TEMP "OriginHub_install_test"
    Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $setup -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
        "/CURRENTUSER", "/NOICONS", "/DIR=`"$dir`"") -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "installer failed (exit $($p.ExitCode))" }
    Test-App "$dir\OriginHub.exe" "installed"
    Start-Process -FilePath "$dir\unins000.exe" -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES") -Wait
}
