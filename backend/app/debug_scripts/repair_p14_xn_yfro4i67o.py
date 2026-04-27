"""Reparo P14 (TODO 010) — domain_xn__yfro4i67o.

Situação: tabela está em pg_inherits (ATTACHED ao parent `domain`) mas
pg_attribute tem 0 linhas com attnum > 0 — corrupção por SIGKILL durante
CREATE TABLE + ATTACH PARTITION.

Impacto:
  - REFRESH MATERIALIZED VIEW tld_domain_count_mv falha
  - SELECT * FROM domain falha
  - Próxima run de ingestão falha ao tentar usar a partição

Fix:
  1. Diagnosticar estado atual
  2. DETACH partition (normal ou via catálogo se necessário)
  3. DROP TABLE
  4. REINDEX SYSTEM obs (opcional — exige superuser)
  5. A próxima run de ingestão recria a partição automaticamente via FULL_RUN

Uso:
  # dentro do container backend ou ingestion:
  DATABASE_URL=postgresql://obs:...@postgres:5432/obs python repair_p14_xn_yfro4i67o.py

  # ou via docker exec:
  docker exec -it <container_id> python app/debug_scripts/repair_p14_xn_yfro4i67o.py
"""

from __future__ import annotations

import os
import sys
import textwrap

import psycopg2
import psycopg2.extras

TLD = "xn--yfro4i67o"
TABLE = f"domain_{TLD.replace('-', '_')}"      # domain_xn__yfro4i67o
PARENT = "domain"
EXPECTED_OID = 111607  # do diagnóstico original; confirmado no diagnóstico abaixo


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────────────

def banner(msg: str) -> None:
    line = "─" * 60
    print(f"\n{line}")
    print(f"  {msg}")
    print(line)


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def warn(msg: str) -> None:
    print(f"  ⚠️  {msg}")


def err(msg: str) -> None:
    print(f"  ❌ {msg}")


def info(msg: str) -> None:
    print(f"  ℹ️  {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# Diagnóstico
# ─────────────────────────────────────────────────────────────────────────────

def diagnose(cur: psycopg2.extensions.cursor) -> dict:
    """Retorna o estado atual da partição corrompida."""
    result: dict = {}

    # OID e relispartition
    cur.execute(
        "SELECT oid, relispartition, relkind FROM pg_class WHERE relname = %s",
        (TABLE,),
    )
    row = cur.fetchone()
    if row is None:
        result["exists"] = False
        return result

    result["exists"] = True
    result["oid"] = row["oid"]
    result["relispartition"] = row["relispartition"]
    result["relkind"] = row["relkind"]

    # pg_attribute (número de colunas)
    cur.execute(
        "SELECT count(*) AS n FROM pg_attribute WHERE attrelid = %s AND attnum > 0",
        (result["oid"],),
    )
    result["attr_count"] = cur.fetchone()["n"]

    # pg_inherits
    cur.execute(
        "SELECT inhparent::regclass::text AS parent FROM pg_inherits WHERE inhrelid = %s",
        (result["oid"],),
    )
    inh = cur.fetchone()
    result["in_inherits"] = inh is not None
    result["parent"] = inh["parent"] if inh else None

    # Constraints
    cur.execute(
        "SELECT conname, contype, coninhcount, conislocal, conparentid "
        "FROM pg_constraint WHERE conrelid = %s",
        (result["oid"],),
    )
    result["constraints"] = cur.fetchall()

    # pg_depend orphans (OIDs em pg_depend sem pg_class)
    cur.execute(
        """
        SELECT pd.objid
        FROM pg_depend pd
        WHERE pd.classid = 'pg_class'::regclass
          AND pd.refobjid = %s
          AND NOT EXISTS (SELECT 1 FROM pg_class pc WHERE pc.oid = pd.objid)
        """,
        (result["oid"],),
    )
    result["phantom_deps"] = [r["objid"] for r in cur.fetchall()]

    return result


def print_diagnosis(d: dict) -> None:
    banner(f"Diagnóstico: {TABLE}")
    if not d["exists"]:
        warn("Tabela não encontrada em pg_class — já foi dropada ou nunca existiu.")
        return

    info(f"OID:             {d['oid']}")
    info(f"relispartition:  {d['relispartition']}")
    info(f"relkind:         {d['relkind']}")
    info(f"pg_attribute:    {d['attr_count']} coluna(s) com attnum > 0")
    info(f"em pg_inherits:  {d['in_inherits']} (parent={d['parent']})")
    info(f"constraints:     {len(d['constraints'])} entradas")
    for c in d["constraints"]:
        info(f"  → {c['conname']} type={c['contype']} inhcount={c['coninhcount']} "
             f"islocal={c['conislocal']} parentid={c['conparentid']}")
    if d["phantom_deps"]:
        warn(f"phantom pg_depend OIDs: {d['phantom_deps']}")
    else:
        info("phantom pg_depend:  nenhum")

    if d["attr_count"] == 0:
        err("Confirmado: tabela corrompida — 0 colunas em pg_attribute.")
    else:
        warn(f"Tabela tem {d['attr_count']} coluna(s) — verifique se o reparo ainda é necessário.")


# ─────────────────────────────────────────────────────────────────────────────
# Reparo
# ─────────────────────────────────────────────────────────────────────────────

def repair(conn: psycopg2.extensions.connection, d: dict, dry_run: bool = False) -> bool:
    """Executa o reparo. Retorna True se a tabela foi removida com sucesso."""
    if not d["exists"]:
        ok("Nada a fazer — tabela já não existe.")
        return True

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def execute(sql: str, params: tuple = ()) -> None:
        if dry_run:
            info(f"[DRY-RUN] {sql.strip()[:120]}")
        else:
            cur.execute(sql, params)

    # ── Passo 1: limpar phantom pg_depend ────────────────────────────────────
    if d["phantom_deps"]:
        banner("Passo 1: remover phantom OIDs em pg_depend")
        if not dry_run:
            cur.execute("SET allow_system_table_mods = on")
        for oid in d["phantom_deps"]:
            execute(
                "DELETE FROM pg_depend WHERE classid = 'pg_class'::regclass AND objid = %s",
                (oid,),
            )
            info(f"Removido phantom OID {oid} de pg_depend")
        if not dry_run:
            cur.execute("SET allow_system_table_mods = off")
            conn.commit()
        ok("Phantom OIDs removidos.")
    else:
        info("Passo 1: sem phantom OIDs — pulando.")

    # ── Passo 2: DETACH partition ─────────────────────────────────────────────
    banner(f"Passo 2: DETACH PARTITION {TABLE}")
    if d["in_inherits"]:
        if not dry_run:
            try:
                cur.execute(
                    f"ALTER TABLE {PARENT} DETACH PARTITION {TABLE}",
                )
                conn.commit()
                ok(f"DETACH normal bem-sucedido.")
            except Exception as exc:
                conn.rollback()
                warn(f"DETACH normal falhou ({exc}) — usando remoção direta do catálogo.")
                cur.execute("SET allow_system_table_mods = on")
                cur.execute(
                    "DELETE FROM pg_inherits WHERE inhrelid = %s",
                    (d["oid"],),
                )
                # Remover constraint herdada do parent (conparentid != 0)
                cur.execute(
                    "UPDATE pg_constraint SET coninhcount = 0, conislocal = true, conparentid = 0 "
                    "WHERE conrelid = %s",
                    (d["oid"],),
                )
                # Remover relispartition
                cur.execute(
                    "UPDATE pg_class SET relispartition = false WHERE oid = %s",
                    (d["oid"],),
                )
                cur.execute("SET allow_system_table_mods = off")
                conn.commit()
                ok("Removido de pg_inherits via catálogo direto.")
        else:
            info(f"[DRY-RUN] ALTER TABLE {PARENT} DETACH PARTITION {TABLE}")
    else:
        info("Partição já não está em pg_inherits — pulando DETACH.")

    # ── Passo 3: DROP TABLE ───────────────────────────────────────────────────
    banner(f"Passo 3: DROP TABLE {TABLE}")
    if not dry_run:
        try:
            cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
            conn.commit()
            ok(f"DROP TABLE {TABLE} executado.")
        except Exception as exc:
            conn.rollback()
            err(f"DROP TABLE falhou: {exc}")
            err("Tente manualmente: psql -c 'DROP TABLE domain_xn__yfro4i67o CASCADE'")
            return False
    else:
        info(f"[DRY-RUN] DROP TABLE {TABLE}")

    return True


def reindex_system(conn: psycopg2.extensions.connection, dry_run: bool = False) -> None:
    """REINDEX SYSTEM obs — requer superuser."""
    banner("Passo 4: REINDEX SYSTEM obs")
    if dry_run:
        info("[DRY-RUN] REINDEX SYSTEM obs")
        return
    try:
        old_iso = conn.isolation_level
        conn.set_isolation_level(0)  # autocommit — REINDEX não roda em transação
        cur = conn.cursor()
        cur.execute("REINDEX SYSTEM obs")
        conn.set_isolation_level(old_iso)
        ok("REINDEX SYSTEM obs concluído.")
    except Exception as exc:
        warn(f"REINDEX SYSTEM falhou: {exc}")
        warn("Execute manualmente como superuser: psql -U postgres -d obs -c 'REINDEX SYSTEM obs'")


def verify(conn: psycopg2.extensions.connection) -> None:
    """Verifica o estado pós-reparo e testa o materialized view."""
    banner("Verificação pós-reparo")
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT oid FROM pg_class WHERE relname = %s", (TABLE,))
    if cur.fetchone() is None:
        ok(f"Tabela {TABLE} não existe mais em pg_class ✓")
    else:
        err(f"Tabela {TABLE} ainda existe — DROP não foi aplicado?")

    cur.execute(
        "SELECT inhrelid FROM pg_inherits WHERE inhrelid IN "
        "(SELECT oid FROM pg_class WHERE relname = %s)",
        (TABLE,),
    )
    if cur.fetchone() is None:
        ok(f"Nenhuma entrada em pg_inherits para {TABLE} ✓")
    else:
        err(f"Ainda há entrada em pg_inherits para {TABLE}")

    # Testar REFRESH do materialized view (se existir)
    cur.execute(
        "SELECT relname FROM pg_class WHERE relname = 'tld_domain_count_mv' AND relkind = 'm'"
    )
    if cur.fetchone():
        try:
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY tld_domain_count_mv")
            conn.commit()
            ok("REFRESH MATERIALIZED VIEW tld_domain_count_mv ✓")
        except Exception as exc:
            warn(f"REFRESH tld_domain_count_mv falhou: {exc}")
            warn("Pode haver outras partições corrompidas ou a MV precisa de CONCURRENTLY.")
    else:
        info("tld_domain_count_mv não encontrado — pulando teste de refresh.")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    dry_run = "--dry-run" in sys.argv
    skip_reindex = "--skip-reindex" in sys.argv

    if dry_run:
        warn("Modo DRY-RUN ativo — nenhuma alteração será feita.")

    db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_DIRECT")
    if not db_url:
        # Fallback: tenta ler do .env
        env_file = os.path.join(os.path.dirname(__file__), "../../../.env")
        if os.path.exists(env_file):
            for line in open(env_file):
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    db_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not db_url:
        err("DATABASE_URL não encontrado. Defina a variável de ambiente antes de rodar.")
        sys.exit(1)

    info(f"Conectando a: {db_url[:40]}...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Diagnóstico
    d = diagnose(cur)
    print_diagnosis(d)

    if not d["exists"]:
        banner("Resultado")
        ok("Tabela já não existe — nenhum reparo necessário.")
        ok("A próxima run de ingestão criará a partição automaticamente.")
        conn.close()
        return

    if d["attr_count"] > 0:
        banner("Resultado")
        warn(f"Tabela tem {d['attr_count']} coluna(s) — pode estar saudável.")
        warn("Execute com --force para forçar o DROP mesmo assim.")
        if "--force" not in sys.argv:
            conn.close()
            return

    # Reparo
    success = repair(conn, d, dry_run=dry_run)

    # REINDEX SYSTEM
    if success and not skip_reindex and not dry_run:
        reindex_system(conn, dry_run=dry_run)
    elif skip_reindex:
        info("Passo 4 pulado (--skip-reindex). Execute manualmente se necessário:")
        info("  psql -U postgres -d obs -c 'REINDEX SYSTEM obs'")

    # Verificação final
    if success and not dry_run:
        verify(conn)

    banner("Resultado final")
    if success and not dry_run:
        ok(f"Partição {TABLE} removida com sucesso.")
        ok("A próxima run de ingestão recriará a partição automaticamente (FULL_RUN).")
        ok("Dispare um ciclo manual via /admin/ingestion ou POST /v1/ingestion/trigger/daily-cycle")
    elif dry_run:
        info("Dry-run completo. Remova --dry-run para aplicar as alterações.")

    conn.close()


if __name__ == "__main__":
    main()
