$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$sourceRoot = Join-Path $repoRoot '.cache/slam-source'
$versions = Get-Content (Join-Path $PSScriptRoot 'source_versions.json') -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Force $sourceRoot | Out-Null
foreach ($project in @('stella_vslam', 'g2o')) {
    $target = Join-Path $sourceRoot $project
    $remote = if ($project -eq 'g2o') { 'RainerKuemmerle/g2o' } else { 'stella-cv/stella_vslam' }
    if (-not (Test-Path $target)) {
        git clone --no-checkout "https://github.com/$remote.git" $target
        if ($LASTEXITCODE -ne 0) { throw "Clone failed: $project" }
        git -C $target checkout $versions.$project
        if ($LASTEXITCODE -ne 0) { throw "Checkout failed: $project" }
    }
    $actual = git -C $target rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $actual -ne $versions.$project) {
        throw "Existing $project checkout differs from source_versions.json; inspect it manually"
    }
    git -C $target submodule update --init --recursive
    if ($LASTEXITCODE -ne 0) { throw "Submodule fetch failed: $project" }
}
$vocabulary = Join-Path $sourceRoot 'orb_vocab.fbow'
if (-not (Test-Path $vocabulary)) {
    curl.exe --fail --location --output $vocabulary 'https://raw.githubusercontent.com/stella-cv/FBoW_orb_vocab/main/orb_vocab.fbow'
    if ($LASTEXITCODE -ne 0) { throw 'Vocabulary download failed' }
}
if ((Get-FileHash $vocabulary -Algorithm SHA256).Hash.ToLowerInvariant() -ne $versions.orb_vocab_sha256) {
    throw 'Vocabulary hash does not match source_versions.json'
}
Write-Output 'Pinned sources and vocabulary are ready.'
