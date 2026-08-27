param([switch]$KeepData)

$ErrorActionPreference = "Stop"
$python = if (Get-Command py -ErrorAction SilentlyContinue) { @("py", "-3") }
          elseif (Get-Command python -ErrorAction SilentlyContinue) { @("python") }
          else { throw "No se encontró Python." }
$script:Python = $python
function Invoke-Python {
    $command = $script:Python[0]
    $prefix = @($script:Python | Select-Object -Skip 1)
    & $command @prefix @args
    if ($LASTEXITCODE -ne 0) { throw "Python terminó con código $LASTEXITCODE." }
}

try {
    $binDir = (Invoke-Python -m pipx environment --value PIPX_BIN_DIR | Select-Object -Last 1).Trim()
    $graphtyn = Join-Path $binDir "graphtyn.exe"
    if (Test-Path $graphtyn) { & $graphtyn service uninstall --kind windows }
    Invoke-Python -m pipx uninstall graphtyn
} catch { Write-Warning $_ }

if (-not $KeepData) {
    $state = Join-Path $HOME ".graphtyn"
    if (Test-Path $state) {
        $answer = Read-Host "¿Eliminar también la memoria e índices de $state? Escriba ELIMINAR"
        if ($answer -eq "ELIMINAR") { Remove-Item -LiteralPath $state -Recurse -Force }
    }
}
Write-Host "Graphtyn fue desinstalado." -ForegroundColor Green
