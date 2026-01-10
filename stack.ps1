# OBS Domínios - Docker Stack Helper Script
# Facilita comandos Docker Stack comuns

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("build", "deploy", "remove", "logs", "status", "clean")]
    [string]$Command = "deploy",
    
    [Parameter(Mandatory=$false)]
    [ValidateSet("frontend", "backend", "all")]
    [string]$Service = "all"
)

$ProjectRoot = $PSScriptRoot
$StackName = "obs"

function Write-Header {
    param([string]$Text)
    Write-Host "`n🦉 OBS Domínios - $Text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
}

function Build-Images {
    Write-Header "Building Imagens"
    
    Set-Location $ProjectRoot
    
    if ($Service -eq "all" -or $Service -eq "frontend") {
        Write-Host "📦 Building frontend:dev..." -ForegroundColor Yellow
        docker build -t observadordedominios-frontend:dev -f frontend/Dockerfile.dev frontend/
    }
    
    if ($Service -eq "all" -or $Service -eq "backend") {
        Write-Host "📦 Building backend:dev..." -ForegroundColor Yellow
        docker build -t observadordedominios-backend:dev -f backend/Dockerfile.dev backend/
    }
    
    Write-Host "✅ Build concluído" -ForegroundColor Green
}

function Deploy-Stack {
    Write-Header "Deploy da Stack"
    
    # Inicializar Swarm se necessário
    $swarmStatus = docker info --format '{{.Swarm.LocalNodeState}}'
    if ($swarmStatus -ne "active") {
        Write-Host "🔄 Inicializando Docker Swarm..." -ForegroundColor Yellow
        docker swarm init
    }
    
    Set-Location "$ProjectRoot\infra"
    
    Write-Host "🚀 Fazendo deploy da stack '$StackName'..." -ForegroundColor Yellow
    docker stack deploy -c stack.dev.yml $StackName
    
    Write-Host "✅ Stack deployada com sucesso!" -ForegroundColor Green
    Write-Host "`n⏳ Aguarde alguns segundos para os serviços iniciarem..." -ForegroundColor Yellow
}

function Remove-Stack {
    Write-Header "Removendo Stack"
    
    docker stack rm $StackName
    Write-Host "✅ Stack removida" -ForegroundColor Green
}

function Show-Logs {
    Write-Header "Logs dos Serviços"
    
    if ($Service -eq "all") {
        Write-Host "📋 Exibindo logs de todos os serviços..." -ForegroundColor Yellow
        docker service logs -f ${StackName}_frontend ${StackName}_backend
    } else {
        Write-Host "📋 Exibindo logs de $Service..." -ForegroundColor Yellow
        docker service logs -f ${StackName}_${Service}
    }
}

function Show-Status {
    Write-Header "Status da Stack"
    
    Write-Host "`n📊 Stack Services:" -ForegroundColor Cyan
    docker stack services $StackName
    
    Write-Host "`n📦 Tasks:" -ForegroundColor Cyan
    docker stack ps $StackName --no-trunc
    
    Write-Host "`n📍 URLs:" -ForegroundColor Cyan
    Write-Host "   Frontend: http://localhost:3005" -ForegroundColor White
    Write-Host "   Backend:  http://localhost:8005/docs" -ForegroundColor White
    Write-Host "   Design System: http://localhost:3005/design-system" -ForegroundColor White
}

function Clean-Environment {
    Write-Header "Limpeza do Ambiente"
    
    Write-Host "⚠️  Esta ação irá:" -ForegroundColor Yellow
    Write-Host "   - Remover a stack" -ForegroundColor Yellow
    Write-Host "   - Remover volumes órfãos" -ForegroundColor Yellow
    
    $confirm = Read-Host "Deseja continuar? (s/n)"
    
    if ($confirm -eq "s") {
        docker stack rm $StackName
        Start-Sleep -Seconds 5
        docker volume prune -f
        Write-Host "✅ Ambiente limpo" -ForegroundColor Green
    } else {
        Write-Host "❌ Operação cancelada" -ForegroundColor Red
    }
}

# Main execution
switch ($Command) {
    "build" { Build-Images }
    "deploy" { 
        Build-Images
        Deploy-Stack 
    }
    "remove" { Remove-Stack }
    "logs" { Show-Logs }
    "status" { Show-Status }
    "clean" { Clean-Environment }
}
