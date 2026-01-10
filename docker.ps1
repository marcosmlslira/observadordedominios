# OBS Domínios - Docker Helper Script
# Facilita comandos Docker comuns

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("start", "stop", "logs", "rebuild", "clean", "status")]
    [string]$Command = "start",
    
    [Parameter(Mandatory=$false)]
    [ValidateSet("frontend", "backend", "all")]
    [string]$Service = "all"
)

$InfraPath = Join-Path $PSScriptRoot "infra"
$DevCompose = "stack.dev.yml"

function Write-Header {
    param([string]$Text)
    Write-Host "`n🦉 OBS Domínios - $Text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
}

function Start-DevEnvironment {
    Write-Header "Iniciando Ambiente de Desenvolvimento"
    
    if ($Service -eq "all") {
        Write-Host "📦 Buildando e iniciando todos os serviços..." -ForegroundColor Yellow
        docker-compose -f "$InfraPath\$DevCompose" up --build
    } else {
        Write-Host "📦 Buildando e iniciando $Service..." -ForegroundColor Yellow
        docker-compose -f "$InfraPath\$DevCompose" up --build $Service
    }
}

function Stop-DevEnvironment {
    Write-Header "Parando Ambiente de Desenvolvimento"
    docker-compose -f "$InfraPath\$DevCompose" down
    Write-Host "✅ Containers parados" -ForegroundColor Green
}

function Show-Logs {
    Write-Header "Logs em Tempo Real"
    
    if ($Service -eq "all") {
        Write-Host "📋 Exibindo logs de todos os serviços (Ctrl+C para sair)..." -ForegroundColor Yellow
        docker-compose -f "$InfraPath\$DevCompose" logs -f
    } else {
        Write-Host "📋 Exibindo logs de $Service (Ctrl+C para sair)..." -ForegroundColor Yellow
        docker-compose -f "$InfraPath\$DevCompose" logs -f $Service
    }
}

function Rebuild-Services {
    Write-Header "Rebuild de Serviços"
    
    if ($Service -eq "all") {
        Write-Host "🔨 Rebuilding todos os serviços..." -ForegroundColor Yellow
        docker-compose -f "$InfraPath\$DevCompose" up -d --build
    } else {
        Write-Host "🔨 Rebuilding $Service..." -ForegroundColor Yellow
        docker-compose -f "$InfraPath\$DevCompose" up -d --build $Service
    }
    Write-Host "✅ Rebuild concluído" -ForegroundColor Green
}

function Clean-Environment {
    Write-Header "Limpeza do Ambiente"
    
    Write-Host "⚠️  Esta ação irá remover:" -ForegroundColor Yellow
    Write-Host "   - Containers" -ForegroundColor Yellow
    Write-Host "   - Volumes" -ForegroundColor Yellow
    Write-Host "   - Networks" -ForegroundColor Yellow
    
    $confirm = Read-Host "Deseja continuar? (s/n)"
    
    if ($confirm -eq "s") {
        docker-compose -f "$InfraPath\$DevCompose" down -v
        Write-Host "✅ Ambiente limpo" -ForegroundColor Green
    } else {
        Write-Host "❌ Operação cancelada" -ForegroundColor Red
    }
}

function Show-Status {
    Write-Header "Status dos Containers"
    
    docker-compose -f "$InfraPath\$DevCompose" ps
    
    Write-Host "`n📊 Informações:" -ForegroundColor Cyan
    Write-Host "   Frontend: http://localhost:3005" -ForegroundColor White
    Write-Host "   Backend:  http://localhost:8005/docs" -ForegroundColor White
    Write-Host "   Design System: http://localhost:3005/design-system" -ForegroundColor White
}

# Main execution
switch ($Command) {
    "start" { Start-DevEnvironment }
    "stop" { Stop-DevEnvironment }
    "logs" { Show-Logs }
    "rebuild" { Rebuild-Services }
    "clean" { Clean-Environment }
    "status" { Show-Status }
}
