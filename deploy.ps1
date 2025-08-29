# deploy.ps1
param(
  [switch]$NoCache,
  [switch]$RunNow,
  [switch]$ShowLogs
)

$ErrorActionPreference = "Stop"

# 1) Ir para a pasta do repositório (onde está este script)
$REPO = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $REPO
Write-Host "==> Diretório: $(Get-Location)"

# 2) Atualizar repositório
if (Test-Path ".git") {
  Write-Host "==> git pull --rebase --autostash"
  git pull --rebase --autostash
} else {
  Write-Warning "(.git não encontrado) Pulando git pull."
}

# 3) Build da imagem
$buildCmd = "docker compose build"
if ($NoCache) { $buildCmd += " --no-cache" }
Write-Host "==> $buildCmd"
iex $buildCmd

# 4) Subir/atualizar serviço
Write-Host "==> docker compose up -d"
docker compose up -d

# 5) Status rápido
Write-Host "==> docker compose ps"
docker compose ps

# 6) Execução imediata opcional
if ($RunNow) {
  Write-Host "==> Executando agora: main.py --all"
  docker exec -it automatest-runner /usr/local/bin/python /app/main.py --all
}

# 7) Logs opcionais
if ($ShowLogs) {
  Write-Host "==> Logs (Ctrl+C para sair)"
  docker logs -f automatest-runner
}

Write-Host "`nOK. Deploy concluído."
