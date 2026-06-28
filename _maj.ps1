$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
try {
    Write-Host '============================================'
    Write-Host '   Mise a jour de RetroBuddy'
    Write-Host '============================================'
    Write-Host ''
    Write-Host '[..] Telechargement de la derniere version...'
    $url = 'https://github.com/jeydead81/RetroBuddy/archive/refs/heads/main.zip'
    $tmp = Join-Path $env:TEMP ('rb_' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force $tmp | Out-Null
    $zip = Join-Path $tmp 'rb.zip'
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Write-Host '[..] Extraction...'
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $src = Join-Path $tmp 'RetroBuddy-main'
    if (-not (Test-Path $src)) { throw 'archive inattendue' }
    Write-Host '[..] Application de la mise a jour (vos donnees et votre cle sont preservees)...'
    robocopy $src $repo /E /XD (Join-Path $repo '.venv') (Join-Path $repo 'data') /XF 'config.local.yaml' /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw 'copie des fichiers impossible' }
    Write-Host '[..] Mise a jour des composants...'
    & (Join-Path $repo '.venv\Scripts\python.exe') -m pip install -r (Join-Path $repo 'requirements.txt') --quiet --disable-pip-version-check
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host ''
    Write-Host '============================================'
    Write-Host '   A jour ! Vos donnees (base + cle) sont intactes.'
    Write-Host '============================================'
} catch {
    Write-Host ''
    Write-Host ('[ERREUR] ' + $_.Exception.Message)
    Write-Host 'Aucune donnee n''a ete touchee. Verifiez votre connexion et reessayez.'
}
Read-Host 'Appuyez sur Entree pour fermer'
