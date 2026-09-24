# Smart compose up: rebuild images only when build inputs change, and
# recreate bind-mounted API containers when ./cognee Python source changes
# (uvicorn does not auto-reload with DEBUG=false).
#
# Usage (from repo root):
#   .\scripts\compose-up.ps1
#   .\scripts\compose-up.ps1 -ForceBuild
#   .\scripts\compose-up.ps1 -ForceBuild frontend,cognee-mcp
#   .\scripts\compose-up.ps1 -NoBuild          # never build, just up -d
#
# Before building frontend, if package.json and package-lock.json drifted,
# the script runs npm install in cognee-frontend so Docker npm ci can succeed.
#
# Why this exists: `docker compose up -d --build` always enters the build path
# (context transfer / frontend Next build). Backend Python is bind-mounted, so
# day-to-day source edits usually need NO image rebuild â€?only Dockerfile /
# lockfiles (and frontend source for the production UI image). The process
# still must be recreated so new routes/modules load.

[CmdletBinding()]
param(
    [switch]$ForceBuild,
    [switch]$NoBuild,
    [string]$ForceBuildServices = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ComposeArgs = @()
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

$StampDir = Join-Path $RepoRoot ".compose-build-stamps"
New-Item -ItemType Directory -Force -Path $StampDir | Out-Null

function Get-FileFingerprint {
    param([string[]]$Paths)
    $rootPath = $RepoRoot.Path
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    $ms = New-Object System.IO.MemoryStream
    foreach ($path in ($Paths | Sort-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $path)) { continue }
        $item = Get-Item -LiteralPath $path
        if ($item.PSIsContainer) {
            Get-ChildItem -LiteralPath $path -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.FullName -notmatch '[\\/]node_modules[\\/]|[\\/]\.next[\\/]|[\\/]\.git[\\/]' -and
                    $_.Extension -notin @(".map", ".log")
                } |
                Sort-Object FullName |
                ForEach-Object {
                    $rel = $_.FullName.Substring($rootPath.Length).TrimStart("\", "/").Replace("\", "/").ToLowerInvariant()
                    $fileHash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
                    $bytes = [Text.Encoding]::UTF8.GetBytes("$rel|$fileHash|")
                    $ms.Write($bytes, 0, $bytes.Length)
                }
        } else {
            $rel = $item.FullName.Substring($rootPath.Length).TrimStart("\", "/").Replace("\", "/").ToLowerInvariant()
            $hash = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash
            $bytes = [Text.Encoding]::UTF8.GetBytes("$rel|$hash|")
            $ms.Write($bytes, 0, $bytes.Length)
        }
    }
    $ms.Position = 0
    $digest = [BitConverter]::ToString($hasher.ComputeHash($ms)).Replace("-", "").ToLowerInvariant()
    $hasher.Dispose()
    $ms.Dispose()
    return $digest
}

function Test-ImageExists {
    param([string]$ImageRef)
    if (-not $ImageRef) { return $false }
    docker image inspect $ImageRef 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Repair-FrontendLockfileIfNeeded {
    <#
    Docker frontend image runs `npm ci`, which requires package.json and
    package-lock.json to match. If they drifted, refresh the lockfile on the
    host before build. Returns $true when npm install updated the lockfile.
    #>
    $fe = Join-Path $RepoRoot "cognee-frontend"
    $pkg = Join-Path $fe "package.json"
    $lock = Join-Path $fe "package-lock.json"
    if (-not (Test-Path -LiteralPath $pkg) -or -not (Test-Path -LiteralPath $lock)) {
        return $false
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Host "[compose-up] npm not on PATH; cannot repair frontend lockfile"
        return $false
    }

    Push-Location -LiteralPath $fe
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & npm ci --dry-run 1>$null 2>$null
        $syncOk = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $prevEap
        if ($syncOk) {
            return $false
        }

        Write-Host "[compose-up] frontend package.json / package-lock.json out of sync; running npm install..."
        $ErrorActionPreference = "Continue"
        & npm install
        $installExit = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        if ($installExit -ne 0) {
            throw "npm install failed in cognee-frontend (exit $installExit)"
        }
        Write-Host "[compose-up] frontend lockfile updated; commit package-lock.json when convenient"
        return $true
    } finally {
        Pop-Location
    }
}

# Build inputs that actually change the image layers we care about.
# cognee / cognee-mcp mount ./cognee at runtime, so app Python edits are NOT
# listed here â€?change those without rebuild.
$ServiceSpecs = @{
    cognee = @{
        ImageHint = "cognee-cognee"
        Watch = @(
            (Join-Path $RepoRoot "Dockerfile")
            (Join-Path $RepoRoot "pyproject.toml")
            (Join-Path $RepoRoot "uv.lock")
            (Join-Path $RepoRoot "entrypoint.sh")
            (Join-Path $RepoRoot "README.md")
        )
    }
    "cognee-mcp" = @{
        ImageHint = "cognee-cognee-mcp"
        Watch = @(
            (Join-Path $RepoRoot "cognee-mcp\Dockerfile")
            (Join-Path $RepoRoot "cognee-mcp\pyproject.toml")
            (Join-Path $RepoRoot "cognee-mcp\uv.lock")
            (Join-Path $RepoRoot "cognee-mcp\entrypoint.sh")
            (Join-Path $RepoRoot "cognee-mcp\src")
        )
    }
    frontend = @{
        ImageHint = "cognee-ui-local"
        Watch = @(
            (Join-Path $RepoRoot "cognee-frontend\Dockerfile")
            (Join-Path $RepoRoot "cognee-frontend\package.json")
            (Join-Path $RepoRoot "cognee-frontend\package-lock.json")
            (Join-Path $RepoRoot "cognee-frontend\next.config.ts")
            (Join-Path $RepoRoot "cognee-frontend\tsconfig.json")
            (Join-Path $RepoRoot "cognee-frontend\src")
            (Join-Path $RepoRoot "cognee-frontend\public")
        )
    }
}

$profilesRaw = ""
if (Test-Path (Join-Path $RepoRoot ".env")) {
    $line = Select-String -Path (Join-Path $RepoRoot ".env") -Pattern '^\s*COMPOSE_PROFILES\s*=' |
        Select-Object -First 1
    if ($line) {
        $profilesRaw = ($line.Line -split "=", 2)[1].Trim().Trim('"').Trim("'")
    }
}
$activeProfiles = @()
if ($profilesRaw) {
    $activeProfiles = $profilesRaw.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}

# Only consider building services that are in the default project or active profiles.
$profileOf = @{
    cognee = $null
    "cognee-mcp" = "mcp"
    frontend = "ui"
}

$candidates = @()
foreach ($name in $ServiceSpecs.Keys) {
    $needProfile = $profileOf[$name]
    if ($null -eq $needProfile -or $activeProfiles -contains $needProfile) {
        $candidates += $name
    }
}

$forced = @()
if ($ForceBuildServices) {
    $forced = $ForceBuildServices.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}
if ($ForceBuild -and -not $forced.Count) {
    $forced = $candidates
}

$toBuild = @()
foreach ($name in $candidates) {
    $spec = $ServiceSpecs[$name]
    $stampPath = Join-Path $StampDir "$name.sha256"
    $fp = Get-FileFingerprint -Paths $spec.Watch
    $imageOk = Test-ImageExists -ImageRef $spec.ImageHint
    # Also accept tagged variants compose may use
    if (-not $imageOk) {
        $imageOk = Test-ImageExists -ImageRef "$($spec.ImageHint):latest"
    }

    $prev = $null
    if (Test-Path -LiteralPath $stampPath) {
        $prev = (Get-Content -LiteralPath $stampPath -Raw).Trim()
    }

    $reason = $null
    if ($NoBuild) {
        # skip
    } elseif ($forced -contains $name) {
        $reason = "forced"
    } elseif (-not $imageOk) {
        $reason = "image missing"
    } elseif ($prev -ne $fp) {
        $reason = "inputs changed"
    }

    if ($reason) {
        Write-Host "[compose-up] build $name ($reason)"
        $toBuild += [pscustomobject]@{ Name = $name; Fingerprint = $fp; StampPath = $stampPath }
    } else {
        Write-Host "[compose-up] skip build $name"
    }
}

if ($toBuild.Count -gt 0 -and -not $NoBuild) {
    # Force array: single [string] @splat expands to chars ("frontend" -> "f")
    $names = @($toBuild | ForEach-Object { $_.Name })
    if ($names -contains "frontend") {
        if (Repair-FrontendLockfileIfNeeded) {
            $feSpec = $ServiceSpecs["frontend"]
            foreach ($item in $toBuild) {
                if ($item.Name -eq "frontend") {
                    $item.Fingerprint = Get-FileFingerprint -Paths $feSpec.Watch
                }
            }
        }
    }
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & docker compose build @names
    $buildExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($buildExit -ne 0) { exit $buildExit }
    foreach ($item in $toBuild) {
        Set-Content -LiteralPath $item.StampPath -Value $item.Fingerprint -NoNewline
    }
} else {
    Write-Host "[compose-up] no image rebuild needed"
}

# ./cognee is bind-mounted into cognee / cognee-mcp. Recreate those containers
# when the source tree changes so the running process picks up new modules.
$sourceStampPath = Join-Path $StampDir "cognee-source.sha256"
$sourceFp = Get-FileFingerprint -Paths @((Join-Path $RepoRoot "cognee"))
$sourcePrev = $null
if (Test-Path -LiteralPath $sourceStampPath) {
    $sourcePrev = (Get-Content -LiteralPath $sourceStampPath -Raw).Trim()
}

$toRecreate = [System.Collections.Generic.List[string]]::new()
if ($ForceBuild -or ($sourcePrev -ne $sourceFp)) {
    $toRecreate.Add("cognee") | Out-Null
    if ($activeProfiles -contains "mcp") {
        $toRecreate.Add("cognee-mcp") | Out-Null
    }
}
foreach ($item in $toBuild) {
    if ($item.Name -in @("cognee", "cognee-mcp") -and -not ($toRecreate -contains $item.Name)) {
        $toRecreate.Add($item.Name) | Out-Null
    }
}

$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& docker compose up -d @ComposeArgs
$upExit = $LASTEXITCODE
if ($upExit -eq 0 -and $toRecreate.Count -gt 0) {
    if ($ForceBuild) {
        Write-Host "[compose-up] recreate $($toRecreate -join ', ') (forced)"
    } elseif ($sourcePrev -ne $sourceFp) {
        Write-Host "[compose-up] recreate $($toRecreate -join ', ') (./cognee source changed)"
    } else {
        Write-Host "[compose-up] recreate $($toRecreate -join ', ') (image rebuilt)"
    }
    & docker compose up -d --force-recreate @($toRecreate.ToArray())
    $upExit = $LASTEXITCODE
    if ($upExit -eq 0) {
        Set-Content -LiteralPath $sourceStampPath -Value $sourceFp -NoNewline
    }
} elseif ($upExit -eq 0) {
    Write-Host "[compose-up] skip recreate (./cognee unchanged)"
}
$ErrorActionPreference = $prevEap
exit $upExit
