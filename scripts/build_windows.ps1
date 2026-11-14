# Requires Windows x64, .NET 8 SDK and PowerShell 7.
[CmdletBinding()]
param([string]$OutputDirectory = (Join-Path $PSScriptRoot '../dist/windows'))
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ("roundtable-build-" + [Guid]::NewGuid())
$bundle = Join-Path $stage 'AI-Roundtable'
$runtime = Join-Path $bundle 'runtime'
New-Item -ItemType Directory -Path $stage, $bundle, $runtime -Force | Out-Null
try {
    $pythonUrl = 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip'
    $pythonZip = Join-Path $stage 'python.zip'
    Invoke-WebRequest $pythonUrl -OutFile $pythonZip
    $pythonSha = (Get-FileHash $pythonZip -Algorithm SHA256).Hash
    if ($pythonSha -ne '9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38') { throw 'Python distribution hash mismatch' }
    Expand-Archive -LiteralPath $pythonZip -DestinationPath $runtime
    # The embedded runtime ignores PYTHONPATH and imports only its distribution and our app.
    Set-Content -LiteralPath (Join-Path $runtime 'python313._pth') -Value "python313.zip`n.`n..\app" -Encoding ascii
    $app = New-Item -ItemType Directory -Path (Join-Path $bundle 'app')
    foreach ($dir in @('backend','frontend')) { Copy-Item -Recurse -Path (Join-Path $root $dir) -Destination $app.FullName }
    Get-ChildItem $app -Directory -Filter '__pycache__' -Recurse | Remove-Item -Recurse -Force
    Get-ChildItem $app -File -Recurse | Where-Object { $_.Extension -eq '.pyc' -or $_.Name -eq '.DS_Store' } | Remove-Item -Force
    $project = Join-Path $root 'windows/AI-Roundtable.csproj'
    dotnet publish $project --configuration Release --runtime win-x64 --self-contained true --output $bundle
    if ($LASTEXITCODE -ne 0) { throw 'Windows desktop build failed' }
    $licenses = New-Item -ItemType Directory -Path (Join-Path $bundle 'licenses')
    $nuget = if ($env:NUGET_PACKAGES) { $env:NUGET_PACKAGES } else { Join-Path $env:USERPROFILE '.nuget/packages' }
    $wv = Join-Path $nuget 'microsoft.web.webview2/1.0.4314.35'
    foreach ($name in @('LICENSE.txt','NOTICE.txt')) {
        Copy-Item -LiteralPath (Join-Path $wv $name) -Destination (Join-Path $licenses.FullName "WebView2-$name")
    }
    Copy-Item -Path (Join-Path $root 'windows/README.txt') -Destination $bundle
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $zip = Join-Path $OutputDirectory 'AI-Roundtable-Windows-x64.zip'
    Compress-Archive -Path $bundle -DestinationPath $zip -Force -CompressionLevel Optimal
    Write-Host "Built $zip"
    Get-FileHash $zip -Algorithm SHA256
} finally {
    if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
