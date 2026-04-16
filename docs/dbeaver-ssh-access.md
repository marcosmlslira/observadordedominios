# DBeaver — Acesso ao PostgreSQL de Produção via SSH Tunnel

## Pré-requisitos

- DBeaver CE/EE instalado localmente
- Chave privada SSH com acesso ao servidor de produção (`ubuntu@158.69.211.109`)
- Porta `15432` publicada no serviço `postgres` do Docker Swarm (já configurado)

---

## Por que SSH Tunnel?

O PostgreSQL de produção **não tem porta exposta publicamente** por padrão.
A porta `15432` está acessível apenas via SSH pelo servidor de produção.
Sem o túnel SSH ativo no DBeaver, a conexão falhará.

---

## Configuração no DBeaver

### Aba "Main"

| Campo    | Valor             |
|----------|-------------------|
| Host     | `127.0.0.1`       |
| Port     | `15432`           |
| Database | `obs`             |
| Username | `obs`             |
| Password | `<senha_do_banco>` |

### Aba "SSH"

| Campo                  | Valor                  |
|------------------------|------------------------|
| Use SSH Tunnel         | ✅ Habilitado           |
| Host/IP                | `158.69.211.109`       |
| Port                   | `22`                   |
| User name              | `ubuntu`               |
| Authentication Method  | Public Key             |
| Private Key (arquivo)  | `~/.ssh/id_rsa` (ou caminho da sua chave) |
| Keep Alive             | ✅ Habilitado           |

> **Nota:** Com SSH Tunnel ativo, o DBeaver cria um túnel local na porta `15432` → servidor → container postgres. O campo "Host" na aba Main sempre será `127.0.0.1`.

---

## Validação da conexão

Após conectar, execute:

```sql
SELECT now();
SELECT current_database(), current_user;
```

Resultado esperado: banco `obs`, usuário `obs`.

---

## Aplicar na produção (deploy do stack)

O arquivo `infra/stack.yml` deste repositório define a configuração de ports do postgres.
Para aplicar em produção:

```bash
# Via CI/CD (recomendado):
# Faça merge na main e o pipeline deploya automaticamente

# Ou manualmente no servidor:
ssh ubuntu@158.69.211.109
cd /home/ubuntu/stacks
docker stack deploy -c stack.yml observador

# Validar que a porta está escutando:
ss -lntp | grep 15432
```

---

## Firewall (UFW)

A porta `15432` deve ser bloqueada publicamente e acessível apenas via SSH tunnel:

```bash
# No servidor de produção:
sudo ufw deny 15432/tcp
# Se precisar liberar IP específico (ex: VPN):
# sudo ufw allow from <IP_AUTORIZADO> to any port 15432 proto tcp
sudo ufw status numbered
```

---

## Rollback

Para remover o acesso:

1. Remover o bloco `ports` do serviço `postgres` em `infra/stack.yml`
2. Fazer deploy:
   ```bash
   docker stack deploy -c stack.yml observador
   ```
3. Revogar exceções de firewall para `15432/tcp`
4. Validar que a porta não está mais escutando: `ss -lntp | grep 15432`

---

## Segurança

- A senha padrão `obs/obs` deve ser trocada em produção o quanto antes
- Prefira criar um usuário de leitura (`obs_readonly`) para análise ad-hoc
- Registrar credenciais em gerenciador de segredos do time (Vault, 1Password, etc.)
