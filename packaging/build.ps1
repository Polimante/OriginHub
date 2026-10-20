# Builds the Windows app and installer, and checks both. Used by CI, the release workflow and locally:
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-NoInstaller] [-InstallTest [-UpdateTest]]
# Needs: pip install -r requirements.txt pyinstaller ; Inno Setup 6 (ISCC.exe) for the installer.
param(
    [switch]$NoInstaller,     # only the PyInstaller folder (faster; used on pull requests)
    [switch]$InstallTest,     # silently install into a temp folder and check the installed app (CI only)
    [switch]$UpdateTest       # with -InstallTest: the installed app updates itself from a local fake release
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

function Test-Update([string]$dir, [string]$setup) {
    # Serves a fake "99.0.0" release (this same installer) from a local web server, runs the installed
    # app with --self-update, and expects: download + SHA-256 check, silent reinstall, app restarted.
    $port = 8765
    $srv = Join-Path $env:TEMP "OriginHub_update_server"
    Remove-Item -Recurse -Force $srv -ErrorAction SilentlyContinue
    New-Item -ItemType Directory $srv | Out-Null
    $fake = "OriginHub-Setup-99.0.0.exe"
    Copy-Item $setup (Join-Path $srv $fake)
    $h = (Get-FileHash (Join-Path $srv $fake) -Algorithm SHA256).Hash.ToLower()
    "$h  $fake" | Out-File -Encoding ascii (Join-Path $srv "$fake.sha256")
    $base = "http://127.0.0.1:$port"
    @{ tag_name = "v99.0.0"; body = "update test"; html_url = $base;
       assets = @(@{ name = $fake; size = (Get-Item $setup).Length; browser_download_url = "$base/$fake" },
                  @{ name = "$fake.sha256"; size = 100; browser_download_url = "$base/$fake.sha256" }) } |
        ConvertTo-Json -Depth 4 | Out-File -Encoding ascii (Join-Path $srv "latest.json")
    $server = Start-Process python -ArgumentList @("-m", "http.server", "$port", "--bind", "127.0.0.1",
        "--directory", "`"$srv`"") -PassThru -WindowStyle Hidden
    # the installer deletes _internal before copying: the marker disappears only if it really ran
    $marker = Join-Path $dir "_internal\update_test_marker.txt"
    "before update" | Out-File $marker
    $exe = Join-Path $dir "OriginHub.exe"
    try {
        Start-Sleep -Seconds 2
        $env:ORIGINHUB_UPDATE_API = "$base/latest.json"
        $p = Start-Process -FilePath $exe -ArgumentList "--self-update" -Wait -PassThru
        if ($p.ExitCode -ne 0) { throw "--self-update failed (exit $($p.ExitCode))" }
        $relaunched = $null
        for ($i = 0; $i -lt 90 -and -not $relaunched; $i++) {
            Start-Sleep -Seconds 2
            if (-not (Test-Path $marker)) {
                $relaunched = Get-Process OriginHub -ErrorAction SilentlyContinue |
                    Where-Object { $_.Path -eq $exe } | Select-Object -First 1
            }
        }
        if (Test-Path $marker) { throw "the update installer did not run" }
        if (-not $relaunched) { throw "OriginHub was not restarted after the update" }
        Write-Host "update check: downloaded, verified, installed and restarted (pid $($relaunched.Id))"
        Stop-Process -Id $relaunched.Id -Force
    } finally {
        Remove-Item Env:ORIGINHUB_UPDATE_API -ErrorAction SilentlyContinue
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    }
    Test-App $exe "updated"
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

# ---- 3. optional: silent install into a temporary folder, check, (update,) uninstall
if ($InstallTest) {
    # Installing registers OriginHub for this Windows user; where it is really installed, the test would
    # take over (and then remove) that registration. So it runs only on a clean machine (CI).
    $id = "Microsoft\Windows\CurrentVersion\Uninstall\{632EE1B2-7DB5-42A9-8E71-B8E198C9175E}_is1"
    $installed = @("HKCU:\Software\$id", "HKLM:\Software\$id") | Where-Object { Test-Path $_ }
    if ($installed -and -not $env:CI) {
        throw "OriginHub is installed on this computer: -InstallTest would replace its registration. It runs in CI."
    }
    $dir = Join-Path $env:TEMP "OriginHub_install_test"
    Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $setup -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
        "/CURRENTUSER", "/NOICONS", "/DIR=`"$dir`"") -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "installer failed (exit $($p.ExitCode))" }
    Test-App (Join-Path $dir "OriginHub.exe") "installed"
    if ($UpdateTest) { Test-Update $dir (Resolve-Path $setup).Path }
    Start-Process -FilePath (Join-Path $dir "unins000.exe") -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES") -Wait
}
