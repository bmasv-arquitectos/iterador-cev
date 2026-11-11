<#
Arma el Iterador CEV para Windows (una carpeta) con PyInstaller.

  powershell -ExecutionPolicy Bypass -File distribucion\armar_exe.ps1            # sin consola (version final)
  powershell -ExecutionPolicy Bypass -File distribucion\armar_exe.ps1 -Consola   # con consola (ver errores)
  ... -SinInstalar   no reinstala los requisitos

Resultado: distribucion\dist\IteradorCEV\IteradorCEV.exe (y su carpeta _internal).
Hay que correrlo con un entorno virtual activado (.venv-exe, ver distribucion\LEEME.md):
PyInstaller mete en el ejecutable lo que encuentra en el entorno, y el Python global suele
tener librerias pesadas (torch, scipy...). Fuera de un entorno virtual, no arma.
#>
param([switch]$Consola, [switch]$SinInstalar)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$env:PYTHONPATH = $raiz
$maximoMB = 600

python --version
Write-Host ("Python: " + (python -c "import sys; print(sys.executable)"))
$venv = python -c "import sys; print(sys.prefix != sys.base_prefix)"
if ($venv -ne "True") {
    throw "No hay un entorno virtual activado: activa .venv-exe (ver distribucion\LEEME.md). Con el Python global el ejecutable sale con librerias que no usa."
}
if (-not $SinInstalar) {
    python -m pip install -r distribucion\requirements-exe.txt
    if ($LASTEXITCODE) { throw "pip fallo" }
}
$pw = python -c "import importlib.util as u; print(bool(u.find_spec('win32api') or u.find_spec('pywintypes')))"
if ($pw -eq "True") { Write-Warning "Este entorno tiene pywin32: se sacara del ejecutable igual, pero conviene un .venv-exe limpio" }
$pesadas = python -c "import importlib.util as u; print(' '.join(p for p in ('torch','scipy','pandas','matplotlib','cv2','sklearn','onnxruntime','kaleido','plotly') if u.find_spec(p)))"
if ($pesadas) { Write-Warning "Este entorno tiene librerias pesadas que la app no usa ($pesadas): se excluyen, pero conviene un .venv-exe limpio" }

python distribucion\preparar.py | Out-Null          # icono y aviso en distribucion\generado
if ($LASTEXITCODE) { throw "preparar.py fallo" }
if ($Consola) { $env:ITERADOR_CONSOLA = "1" } else { Remove-Item Env:ITERADOR_CONSOLA -ErrorAction SilentlyContinue }

python -m PyInstaller --noconfirm --clean --distpath distribucion\dist --workpath distribucion\build distribucion\iterador_cev.spec
if ($LASTEXITCODE) { throw "PyInstaller fallo" }

$carpeta = Join-Path $raiz "distribucion\dist\IteradorCEV"
$mb = [math]::Round(((Get-ChildItem $carpeta -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 0)
$tipo = if ($Consola) { "con consola" } else { "sin consola" }
Write-Host ""
Write-Host "Listo: $carpeta\IteradorCEV.exe ($mb MB, $tipo)"
$w = Get-ChildItem $carpeta -Recurse | Where-Object { $_.Name -match '^(win32com|win32comext|pythonwin|pywin32_system32|pythoncom\d*\.dll|pywintypes\d*\.dll|win32\w*\.pyd)$' }
if ($w) {
    Write-Warning "Quedo algo de pywin32:"
    $w | ForEach-Object { Write-Host ("  " + $_.FullName.Substring($carpeta.Length + 1)) }
} else { Write-Host "Sin pywin32: OK" }
if ($mb -gt $maximoMB) {
    Write-Warning "Pesa mas de $maximoMB MB: revisa las carpetas mas grandes de _internal:"
    Get-ChildItem (Join-Path $carpeta "_internal") | ForEach-Object {
        [pscustomobject]@{ Nombre = $_.Name; MB = [math]::Round(((Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB), 0) }
    } | Sort-Object MB -Descending | Select-Object -First 10 | Format-Table -AutoSize
}
