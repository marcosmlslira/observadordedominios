# Comandos de Producao

## Preparacao
```powershell
$env:PROD_HOST="158.69.211.109"
$env:PROD_USER="ubuntu"
$env:PROD_PASSWORD="<senha>"
```

Se faltar a biblioteca SSH:
```powershell
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

## Regra operacional
- Corrija primeiro a origem em `docker-stack-infra`.
- So use restart manual depois de confirmar que o stack ja contem as envs corretas.
