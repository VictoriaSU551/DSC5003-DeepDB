$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'Please install uv first: python -m pip install uv'
}
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '.runtime'
$cachePath = Join-Path $PSScriptRoot 'output/tmp/uv-cache'
$env:UV_CACHE_DIR = $cachePath
uv python install 3.8.20
if ($LASTEXITCODE -ne 0) { throw 'Python installation failed' }
uv venv --python 3.8.20 .venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
$temporaryDrive = $null
try {
    # Shorten only build-cache paths; all physical files remain inside this project.
    foreach ($letter in @('R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z')) {
        if (-not (Test-Path ($letter + ':\'))) {
            subst ($letter + ':') $PSScriptRoot
            if ($LASTEXITCODE -eq 0) {
                $temporaryDrive = $letter + ':'
                $env:UV_CACHE_DIR = $temporaryDrive + '/output/tmp/uv-cache'
                break
            }
        }
    }
    uv pip install --python .venv/Scripts/python.exe -r requirements.txt -c requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    uv pip install --python .venv/Scripts/python.exe --no-deps spflow==0.0.40
    if ($LASTEXITCODE -ne 0) { throw 'SPFlow installation failed' }
} finally {
    if ($temporaryDrive) { subst $temporaryDrive /d }
    $env:UV_CACHE_DIR = $cachePath
}
Write-Output 'Environment ready. Run .venv/Scripts/python.exe code/download_data.py'
