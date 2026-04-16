# 006 - Acesso contínuo ao PostgreSQL via DBeaver + SSH (sem container auxiliar)

## Contexto

Hoje o acesso ao PostgreSQL de produção exige criar um container proxy temporário (`socat`) para
encaminhar `postgres:5432` para uma porta local no host.

Objetivo deste refinamento: permitir acesso recorrente e estável pelo DBeaver sem subir container
extra em cada sessão, usando:
- porta fixa publicada no serviço `postgres` do stack;
- túnel SSH nativo do DBeaver;
- regras de firewall para reduzir exposição.

## Objetivo

Implementar um caminho oficial de conexão para desenvolvedores autorizados:
1. manter `postgres` acessível em porta fixa no host de produção;
2. usar DBeaver com SSH tunnel para conexão diária;
3. manter superfície de ataque controlada com firewall e credenciais adequadas.

## Escopo

### Em escopo
- Alteração do `stack.yml` de produção (repo `docker-stack-infra`) para publicar porta do Postgres.
- Configuração de firewall para porta publicada.
- Runbook de conexão no DBeaver (aba Main + aba SSH).
- Checklist de validação e rollback.

### Fora de escopo
- Troca de engine de banco.
- Mudança de schema/modelo de dados.
- Criação de bastion host dedicado.

## Implementação proposta

### 1. Publicar porta fixa no serviço `postgres`

No `stack.yml` de produção (repositório `docker-stack-infra`), adicionar no serviço `postgres`:

```yaml
services:
  postgres:
    # ...
    ports:
      - target: 5432
        published: 15432
        protocol: tcp
        mode: host
```

Notas:
- usar `15432` para evitar conflito com instalações locais;
- manter `mode: host` para previsibilidade operacional no nó do banco;
- não alterar variáveis `POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB` neste passo.

### 2. Aplicar hardening de rede

Aplicar regra de firewall no host de produção para minimizar exposição de `15432/tcp`.

Estratégia recomendada:
- bloquear `15432/tcp` publicamente;
- permitir somente fontes explícitas (VPN, IP corporativo, ou administração aprovada).

Exemplo com UFW (ajustar à política real do servidor):

```bash
sudo ufw deny 15432/tcp
# opcional: liberar somente rede/IP autorizado
sudo ufw allow from <IP_OU_CIDR_AUTORIZADO> to any port 15432 proto tcp
sudo ufw status numbered
```

Se o ambiente usar outra camada (iptables/security group/cloud firewall), documentar regra equivalente.

### 3. Deploy

Executar deploy do stack de produção:

```bash
docker stack deploy -c stack.yml observador
```

Validar serviço:

```bash
docker service ls | grep observador_postgres
docker service ps observador_postgres --no-trunc
```

### 4. Configuração padrão do DBeaver

Configurar conexão PostgreSQL no DBeaver:

Main:
- Host: `127.0.0.1`
- Port: `15432`
- Database: `obs`
- Username: `obs`
- Password: `<segredo_real>`

SSH:
- Use SSH Tunnel: habilitado
- Host/IP: `158.69.211.109`
- Port: `22`
- User name: `ubuntu`
- Authentication: chave privada (recomendado) ou senha
- Keep Alive: habilitado

Observação:
- com SSH Tunnel ativo, o acesso ocorre pelo canal SSH autenticado;
- sem SSH (ou sem IP liberado), a conexão deve falhar.

### 5. Segurança de credenciais

Após estabilizar acesso:
- remover senhas padrão (`obs/obs`) em produção, se ainda estiverem em uso;
- criar usuário de leitura para uso de análise (ex: `obs_readonly`);
- registrar origem de segredos em cofre/secret manager do time.

## Critérios de aceite

- [ ] Serviço `postgres` no stack de produção publica `15432/tcp`.
- [ ] Firewall documentado e aplicado para limitar acesso à porta publicada.
- [ ] Conexão no DBeaver funciona com SSH tunnel sem uso de container auxiliar.
- [ ] Health da API continua estável após alteração de stack.
- [ ] Runbook salvo e compartilhado com o time.
- [ ] Rollback testado (remover publicação da porta e redeploy).

## Plano de validação

1. Validar conectividade no servidor:
```bash
ss -lntp | grep 15432
```

2. Validar fluxo com SSH + DBeaver:
- abrir conexão;
- executar `SELECT now();`
- executar `SELECT current_database(), current_user;`

3. Validar que sem SSH/IP autorizado a conexão não abre.

## Rollback

1. Remover bloco `ports` do serviço `postgres` no `stack.yml`.
2. `docker stack deploy` novamente.
3. Remover exceções de firewall criadas para `15432/tcp`.
4. Revalidar que acesso externo à porta não existe.

## Riscos e mitigação

- Exposição indevida da porta do banco:
  mitigar com firewall + revisão de regras após deploy.
- Uso de credenciais amplas no DBeaver:
  mitigar com usuário read-only e rotação de senha.
- Mudança operacional fora do repo principal:
  mitigar com PR no `docker-stack-infra` e checklist de validação.
