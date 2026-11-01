param(
    [string]$Sdk,
    [string]$Jdk,
    [string]$BuildDir,
    [string]$OutputDir,
    [string]$KeyStore
)
$ErrorActionPreference = 'Stop'
$buildArguments = @((Join-Path $PSScriptRoot 'scripts/build.py'))
foreach ($entry in @(
    @('--sdk', $Sdk), @('--jdk', $Jdk), @('--build-dir', $BuildDir),
    @('--output-dir', $OutputDir), @('--keystore', $KeyStore)
)) {
    if ($entry[1]) { $buildArguments += $entry }
}
& python @buildArguments
if ($LASTEXITCODE -ne 0) { throw "Build failed with exit code $LASTEXITCODE" }
