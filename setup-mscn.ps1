$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv-mscn/Scripts/python.exe'
$bootstrapMarker = Join-Path $PSScriptRoot '.venv-mscn/.bootstrap-pinned-wheels'
$checkCode = @'
import importlib.metadata as m
import sys
assert sys.version_info[:3] == (3, 8, 20), sys.version
expected = {'numpy':'1.24.4', 'torch':'1.13.1+cpu', 'pytest':'8.3.5',
            'typing_extensions':'4.13.2', 'iniconfig':'2.1.0', 'packaging':'24.2',
            'pluggy':'1.5.0', 'exceptiongroup':'1.2.2', 'tomli':'2.2.1', 'colorama':'0.4.6'}
actual = {name:m.version(name) for name in expected}
assert actual == expected, actual
import numpy as np
import torch
torch.set_num_threads(1)
sample = torch.from_numpy(np.array([1., 2.], dtype=np.float32))
assert torch.equal(sample * 2, torch.tensor([2., 4.]))
print('Pinned MSCN versions and CPU NumPy/Torch smoke verified; no package changes.')
'@
if ((Test-Path -LiteralPath $python) -and -not (Test-Path -LiteralPath $bootstrapMarker)) {
    & $python -c $checkCode
    if ($LASTEXITCODE -ne 0) {
        throw 'Existing MSCN environment differs. It was preserved; use another project checkout for a different environment.'
    }
    return
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'Install uv first, or run the main setup.ps1.'
}
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '.runtime'
$env:UV_PYTHON_BIN_DIR = Join-Path $PSScriptRoot '.runtime/bin'
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot 'output/tmp/uv-cache'
if (-not (Test-Path -LiteralPath $python)) {
    uv python install 3.8.20 --no-bin --no-registry
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed' }
    uv venv --python 3.8.20 .venv-mscn
    if ($LASTEXITCODE -ne 0) { throw 'MSCN environment creation failed' }
    Set-Content -LiteralPath $bootstrapMarker -Value 'Pinned-wheel bootstrap in progress; safe to resume this installer.'
}
$manifestPath = Join-Path $PSScriptRoot 'docs/manifests/mscn-windows-py38-wheels.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$wheelDirectory = Join-Path $PSScriptRoot 'data/downloads/mscn-wheels'
New-Item -ItemType Directory -Path $wheelDirectory -Force | Out-Null
$wheelFiles = @()
foreach ($entry in $manifest) {
    $target = Join-Path $wheelDirectory $entry.filename
    if (-not (Test-Path -LiteralPath $target)) {
        $partial = $target + '.download.tmp'
        curl.exe --fail --location --retry 3 --output $partial -- $entry.url
        if ($LASTEXITCODE -ne 0) { throw ('Wheel download failed: ' + $entry.filename) }
        $checksum = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
        if ((Get-Item -LiteralPath $partial).Length -ne $entry.bytes -or $checksum -ne $entry.sha256) {
            throw ('Downloaded wheel differs from the pinned bytes: ' + $entry.filename)
        }
        Move-Item -LiteralPath $partial -Destination $target
    }
    $checksum = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ((Get-Item -LiteralPath $target).Length -ne $entry.bytes -or $checksum -ne $entry.sha256) {
        throw ('Existing wheel differs; preserved without installation: ' + $entry.filename)
    }
    $wheelFiles += $target
}
uv pip install --python $python --no-index --no-deps @wheelFiles
if ($LASTEXITCODE -ne 0) { throw 'Pinned wheel installation failed' }
& $python -c $checkCode
if ($LASTEXITCODE -ne 0) { throw 'Pinned MSCN runtime verification failed' }
if (Test-Path -LiteralPath $bootstrapMarker) { Remove-Item -LiteralPath $bootstrapMarker }
