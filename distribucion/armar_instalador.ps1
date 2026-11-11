<#
Arma el instalador de Windows del Iterador CEV (Inno Setup).

  powershell -ExecutionPolicy Bypass -File distribucion\armar_instalador.ps1          # arma el .exe (sin consola) y el instalador
  powershell -ExecutionPolicy Bypass -File distribucion\armar_instalador.ps1 -SinExe  # solo el instalador, con el .exe ya armado
  ... -Compresion "lzma2/normal"   otra compresion (por defecto lzma2/max; ver iterador_cev.iss)

Necesita Inno Setup 6.3 o mas nuevo:  winget install --id JRSoftware.InnoSetup -e
Resultado: distribucion\instalador\IteradorCEV-<version>-instalador.exe
#>
param([switch]$SinExe, [string]$Compresion = "lzma2/max")
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$env:PYTHONPATH = $raiz

if (-not $SinExe) {
    & (Join-Path $PSScriptRoot "armar_exe.ps1")
}
$origen = Join-Path $raiz "distribucion\dist\IteradorCEV"
if (-not (Test-Path (Join-Path $origen "IteradorCEV.exe"))) { throw "Falta $origen\IteradorCEV.exe: arma primero el ejecutable" }

$info = python distribucion\preparar.py | ConvertFrom-Json
if ($LASTEXITCODE) { throw "preparar.py fallo" }

$candidatos = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path $_) }
if (-not $candidatos) { throw "No encuentro Inno Setup. Instalalo con: winget install --id JRSoftware.InnoSetup -e" }
$iscc = @($candidatos)[0]
Write-Host "Inno Setup: $iscc (compresion $Compresion)"

$salida = Join-Path $raiz "distribucion\instalador"
$inicio = Get-Date
& $iscc /Q `
    "/DNombre=$($info.nombre)" "/DVersion=$($info.version)" "/DVersionNum=$($info.version_numero)" `
    "/DEditor=$($info.editor)" "/DUrl=$($info.url)" "/DOrigen=$origen" "/DSalida=$salida" `
    "/DArchivo=$($info.archivo)" "/DIcono=$($info.icono)" "/DAviso=$($info.aviso)" `
    "/DCompresion=$Compresion" `
    distribucion\iterador_cev.iss
if ($LASTEXITCODE) { throw "Inno Setup fallo" }

$f = Get-Item (Join-Path $salida "$($info.archivo).exe")
$min = [math]::Round(((Get-Date) - $inicio).TotalMinutes, 1)
Write-Host ""
Write-Host ("Instalador: {0} ({1} MB, {2} min)" -f $f.FullName, [math]::Round($f.Length / 1MB, 0), $min)
