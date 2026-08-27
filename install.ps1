param(
    [string]$ProjectPath = (Get-Location).Path,
    [string]$Version = "",
    [string]$PackageSource = "graphtyn",
    [switch]$SkipService,
    [switch]$SkipSetup,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) { return @("py", "-3") }
    if (Get-Command python -ErrorAction SilentlyContinue) { return @("python") }
    throw "Python 3.10 o superior no está instalado. Instálelo desde https://www.python.org/downloads/windows/ y repita el comando."
}

$script:Python = Find-Python
function Invoke-Python {
    $command = $script:Python[0]
    $prefix = @($script:Python | Select-Object -Skip 1)
    & $command @prefix @args
    if ($LASTEXITCODE -ne 0) { throw "Python terminó con código $LASTEXITCODE." }
}

$pythonVersion = (Invoke-Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
$parts = $pythonVersion.Split('.')
if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 10)) {
    throw "Graphtyn requiere Python 3.10 o superior; se encontró $pythonVersion."
}

try { Invoke-Python -m pipx --version | Out-Null }
catch {
    Write-Host "Instalando pipx para el usuario..." -ForegroundColor Cyan
    Invoke-Python -m pip install --user --upgrade pipx
}

Invoke-Python -m pipx ensurepath | Out-Null
$package = $PackageSource
if ($PackageSource -eq "graphtyn" -and -not $Version) {
    $bundledWheel = Get-ChildItem -Path $PSScriptRoot -Filter "graphtyn-*.whl" -File |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($bundledWheel) { $package = $bundledWheel.FullName }
}
if ($Version) {
    if ($Version -notmatch '^\d+\.\d+\.\d+([a-zA-Z0-9.-]+)?$') { throw "Versión inválida: $Version" }
    if ($PackageSource -ne "graphtyn") { throw "No combine -Version con -PackageSource personalizado." }
    $package = "graphtyn==$Version"
}

Write-Host "Instalando $package..." -ForegroundColor Cyan
Invoke-Python -m pipx install --force $package
$binDir = (Invoke-Python -m pipx environment --value PIPX_BIN_DIR | Select-Object -Last 1).Trim()
$graphtyn = Join-Path $binDir "graphtyn.exe"
if (-not (Test-Path $graphtyn)) { throw "pipx terminó, pero no se encontró $graphtyn" }

$project = [System.IO.Path]::GetFullPath($ProjectPath)
if (-not (Test-Path $project -PathType Container)) { throw "El proyecto no existe: $project" }
if (-not $SkipSetup) {
    Write-Host "Configurando el proyecto..." -ForegroundColor Cyan
    & $graphtyn setup --path $project --apply
    if ($LASTEXITCODE -ne 0) { throw "No se pudo configurar el proyecto." }
}
if (-not $SkipService) {
    Write-Host "Registrando el dashboard al iniciar sesión..." -ForegroundColor Cyan
    & $graphtyn service install --kind windows --path $project --enable
    if ($LASTEXITCODE -ne 0) { throw "No se pudo registrar el dashboard de Windows." }
}

Write-Host "Graphtyn quedó instalado correctamente." -ForegroundColor Green
Write-Host "Dashboard: http://127.0.0.1:9210" -ForegroundColor Green
Write-Host "Proyecto: $project"
if (-not $NoOpen -and -not $SkipService) { Start-Process "http://127.0.0.1:9210" }
