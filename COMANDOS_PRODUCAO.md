# Comandos de Producao

## Preparacao
```powershell
ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new ubuntu@158.69.211.109 "hostname"
```

Opcional para usar o helper local `scripts/prod_server.py`:
```powershell
$env:PROD_HOST="158.69.211.109"
$env:PROD_USER="ubuntu"
$env:PROD_PASSWORD="<senha>"
py -m pip install paramiko
```

## Status do stack
```powershell
py scripts/prod_server.py status
```

## Ver envs efetivas do backend
```powershell
py scripts/prod_server.py auth-env
```

O bloco critico para login e:
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD_HASH`
- `JWT_SECRET_KEY`

Se qualquer um vier vazio, o login admin nao funciona.

## Ver logs do backend
```powershell
py scripts/prod_server.py logs --service observador_backend --tail 200
```

## Testar health publico
```powershell
py scripts/prod_server.py health
```

## Testar login real
```powershell
py scripts/prod_server.py test-login --email admin@observador.com --password mls1509ti
```

## Forcar rolling update do backend
```powershell
py scripts/prod_server.py restart --service observador_backend
```

Observacao:
- `observador_ct_ingestor` e `observador_certstream_server` sao legados e nao devem ser recriados.
- A stack produtiva real fica em `C:\PROJETOS\docker-stack-infra\stacks\observador.yml`.
- O worker diario valido da ingestao atual e `observador-ingestion_ingestion_worker`.

## Regra operacional
- Corrija primeiro a origem em `docker-stack-infra`.
- So use restart manual depois de confirmar que o stack ja contem as envs corretas.

## Monitorar progresso da ingestao
Local com PowerShell:
```powershell
$env:OBS_ADMIN_EMAIL="admin@observador.com"
$env:OBS_ADMIN_PASSWORD="SUA_SENHA"
.\scripts\watch_ingestion.ps1
```

Leitura unica com PowerShell:
```powershell
.\scripts\watch_ingestion.ps1 -Email "admin@observador.com" -Password "SUA_SENHA" -Once
```

Servidor/Linux:
```bash
export OBS_ADMIN_EMAIL="admin@observador.com"
export OBS_ADMIN_PASSWORD="SUA_SENHA"
bash scripts/watch_ingestion.sh
```

Leitura unica no servidor/Linux:
```bash
OBS_ADMIN_EMAIL="admin@observador.com" OBS_ADMIN_PASSWORD="SUA_SENHA" ONCE=1 bash scripts/watch_ingestion.sh
```
