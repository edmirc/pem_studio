#!/usr/bin/env bash
# ==========================================================================
# PEM Studio - instalação/atualização em Docker
#
# Uso (dentro da pasta do projeto no servidor):
#     bash instalar-docker.sh              # detecta o container do MySQL
#     bash instalar-docker.sh nome-do-mysql
#
# O que faz, nesta ordem:
#   1. confere o Docker
#   2. cria o .env (pergunta a senha do banco) se ainda não existir
#   3. faz BACKUP do banco (para se falhar)
#   4. liga o MySQL na rede pem-rede (sem reiniciar o MySQL)
#   5. confere a pasta de fotos no HD externo, constrói e sobe o container
#   6. aplica as migrações e testa se o site responde
# Pode ser rodado de novo sempre que o código mudar.
# ==========================================================================
set -euo pipefail
cd "$(dirname "$0")"

verde() { printf '\033[32m%s\033[0m\n' "$*"; }
amarelo() { printf '\033[33m%s\033[0m\n' "$*"; }
erro() { printf '\033[31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }
passo() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# grava CHAVE=valor no .env (aceita qualquer caractere no valor)
definir() {
  local chave="$1" valor="$2" tmp
  tmp="$(mktemp)"
  K="$chave" V="$valor" awk 'BEGIN{FS="="; k=ENVIRON["K"]; v=ENVIRON["V"]} $1==k {print k"="v; achou=1; next} {print} END{if(!achou) print k"="v}' .env > "$tmp"
  cat "$tmp" > .env && rm -f "$tmp"
}
# lê CHAVE do .env sem executar o arquivo
ler() { { grep -E "^$1=" .env || true; } | tail -1 | cut -d= -f2-; }

# ---------------------------------------------------------------- 1. Docker
passo "1/6 Conferindo o Docker"
command -v docker >/dev/null || erro "Docker não está instalado."
if ! docker info >/dev/null 2>&1; then
  erro "Sem permissão para usar o Docker. Rode de novo com:  sudo bash instalar-docker.sh"
fi
docker compose version >/dev/null 2>&1 || erro "Falta o plugin 'docker compose'. Instale com: sudo apt install docker-compose-plugin"
verde "Docker ok: $(docker --version)"

# --------------------------------------------------- container do MySQL
MYSQL_C="${1:-}"
if [ -z "$MYSQL_C" ]; then
  mapfile -t candidatos < <(docker ps --format '{{.Names}} {{.Image}}' | grep -Ei 'mysql|mariadb' | awk '{print $1}')
  if [ "${#candidatos[@]}" -eq 0 ]; then
    docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
    erro "Não achei o container do MySQL. Rode: bash instalar-docker.sh NOME_DO_CONTAINER"
  elif [ "${#candidatos[@]}" -gt 1 ]; then
    docker ps --format 'table {{.Names}}\t{{.Image}}'
    erro "Achei mais de um MySQL (${candidatos[*]}). Rode: bash instalar-docker.sh NOME_DO_CONTAINER"
  fi
  MYSQL_C="${candidatos[0]}"
fi
docker inspect "$MYSQL_C" >/dev/null 2>&1 || erro "Container '$MYSQL_C' não existe."
verde "Container do MySQL: $MYSQL_C ($(docker inspect -f '{{.Config.Image}}' "$MYSQL_C"))"

# ------------------------------------------------------------- 2. .env
passo "2/6 Arquivo de configuração (.env)"
if [ ! -f .env ]; then
  [ -f env.exemplo ] || erro "env.exemplo não encontrado. Você está na pasta do projeto?"
  read -r -p "Usuário do banco [remoto]: " db_user; db_user="${db_user:-remoto}"
  read -r -s -p "Senha do banco para '$db_user': " db_pass; echo
  read -r -p "Nome do banco [pem_studio]: " db_name; db_name="${db_name:-pem_studio}"
  chave="$(head -c 48 /dev/urandom | base64 | tr -d '/+=\n' | head -c 60)"
  ips="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9.]+$' | grep -v '^172\.' || true)"
  hosts="localhost,127.0.0.1"; origens=""
  for ip in $ips 192.168.3.190 100.116.208.105; do
    case ",$hosts," in *",$ip,"*) continue;; esac
    hosts="$hosts,$ip"
    for p in "" ":81" ":8001"; do origens="${origens:+$origens,}http://$ip$p"; done
  done
  cp env.exemplo .env
  definir DJANGO_SECRET_KEY "$chave"
  definir DJANGO_ALLOWED_HOSTS "$hosts"
  definir DJANGO_CSRF_TRUSTED_ORIGINS "$origens"
  definir DB_USER "$db_user"
  definir DB_PASSWORD "$db_pass"
  definir DB_NAME "$db_name"
  definir DB_HOST "$MYSQL_C"
  chmod 600 .env
  verde ".env criado (endereços: $hosts)"
else
  definir DB_HOST "$MYSQL_C"
  verde ".env já existe, mantido (DB_HOST=$MYSQL_C)"
fi
DB_NAME="$(ler DB_NAME)"; DB_USER="$(ler DB_USER)"; DB_PASSWORD="$(ler DB_PASSWORD)"
PORTA="$(ler PORTA)"; PORTA="${PORTA:-8001}"
REDE_BANCO="$(ler REDE_BANCO)"; REDE_BANCO="${REDE_BANCO:-pem-rede}"
case "$DB_PASSWORD" in *'$'*) amarelo "Aviso: a senha tem '\$'. No .env, escreva cada \$ como \$\$ para o Docker não interpretar.";; esac

# ----------------------------------------------------------- 3. Backup
passo "3/6 Backup do banco $DB_NAME"
mkdir -p backups
ARQ="backups/backup_${DB_NAME}_$(date +%F_%H%M%S).sql"
dump_cmd='if command -v mysqldump >/dev/null; then echo mysqldump; else echo mariadb-dump; fi'
DUMP="$(docker exec "$MYSQL_C" sh -c "$dump_cmd")"
ok=0
# tenta com o root do container (variável de ambiente da própria imagem)
if docker exec "$MYSQL_C" sh -c '[ -n "${MYSQL_ROOT_PASSWORD:-${MARIADB_ROOT_PASSWORD:-}}" ]' 2>/dev/null; then
  docker exec "$MYSQL_C" sh -c "MYSQL_PWD=\"\${MYSQL_ROOT_PASSWORD:-\$MARIADB_ROOT_PASSWORD}\" $DUMP -uroot --single-transaction --routines --triggers --no-tablespaces \"$DB_NAME\"" > "$ARQ" 2>/tmp/pem_dump_err && ok=1 || true
fi
# senão, com o usuário do app
if [ "$ok" -eq 0 ]; then
  docker exec -e MYSQL_PWD="$DB_PASSWORD" "$MYSQL_C" $DUMP -u"$DB_USER" --single-transaction --no-tablespaces "$DB_NAME" > "$ARQ" 2>/tmp/pem_dump_err && ok=1 || true
fi
if [ "$ok" -eq 0 ] || ! grep -q "CREATE TABLE" "$ARQ"; then
  cat /tmp/pem_dump_err >&2 || true
  erro "Backup falhou. Nada foi alterado. Mande esta mensagem para o Claude."
fi
gzip -f "$ARQ"
verde "Backup salvo: $(pwd)/$ARQ.gz ($(du -h "$ARQ.gz" | cut -f1), $(zcat "$ARQ.gz" | grep -c 'CREATE TABLE') tabelas)"

# ------------------------------------------------------------- 4. Rede
passo "4/6 Rede Docker $REDE_BANCO"
docker network inspect "$REDE_BANCO" >/dev/null 2>&1 || docker network create "$REDE_BANCO" >/dev/null
if docker inspect -f '{{json .NetworkSettings.Networks}}' "$MYSQL_C" | grep -q "\"$REDE_BANCO\""; then
  verde "MySQL já está na rede."
else
  docker network connect "$REDE_BANCO" "$MYSQL_C"
  verde "MySQL ligado na rede (sem reiniciar)."
fi

# ------------------------------------------------ Pasta de imagens (HD externo)
passo "Pasta das fotos e arquivos"
PASTA_IMAGENS="$(ler PASTA_IMAGENS)"
if [ -z "$PASTA_IMAGENS" ]; then
  PASTA_IMAGENS=/mnt/hd4t/imagens_pem_studio
  definir PASTA_IMAGENS "$PASTA_IMAGENS"
fi
HD="$(dirname "$PASTA_IMAGENS")"
[ -d "$HD" ] || erro "A pasta $HD não existe. O HD externo está ligado e montado?"
montado_em="$(df --output=target "$HD" 2>/dev/null | tail -1)"
if [ "$montado_em" = "/" ] && [ "${FORCAR_DISCO_SISTEMA:-0}" != "1" ]; then
  erro "$HD está no disco do sistema, não num HD montado. Monte o HD externo (ex.: sudo mount /mnt/hd4t) e rode de novo."
fi
if [ ! -d "$PASTA_IMAGENS" ]; then
  mkdir -p "$PASTA_IMAGENS" 2>/dev/null || erro "Sem permissão para criar $PASTA_IMAGENS. Rode: sudo mkdir -p $PASTA_IMAGENS && sudo chown $(id -u):$(id -g) $PASTA_IMAGENS"
fi
dono_uid="$(stat -c %u "$PASTA_IMAGENS")"; dono_gid="$(stat -c %g "$PASTA_IMAGENS")"
if [ "$dono_uid" = "0" ]; then
  if [ "$(id -u)" = "0" ]; then
    chown 1000:1000 "$PASTA_IMAGENS" 2>/dev/null || true
    dono_uid="$(stat -c %u "$PASTA_IMAGENS")"; dono_gid="$(stat -c %g "$PASTA_IMAGENS")"
  fi
fi
[ "$dono_uid" = "0" ] && { dono_uid=1000; dono_gid=1000; }
definir UID_APP "$dono_uid"; definir GID_APP "$dono_gid"
verde "Fotos em: $PASTA_IMAGENS (montado em $montado_em, container roda como $dono_uid:$dono_gid)"

# -------------------------------------------------- 5. Build e subida
passo "5/6 Construindo a imagem e subindo na porta $PORTA"
if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$PORTA\$" && ! docker ps --format '{{.Names}}' | grep -qx pem-studio; then
  erro "A porta $PORTA já está em uso por outro programa. Troque PORTA no .env."
fi
docker compose up -d --build

# ----------------------------------------- 6. Migrações e verificação
passo "6/6 Migrações e teste"
for _ in $(seq 1 30); do
  docker compose exec -T web python -c "import django" >/dev/null 2>&1 && break
  sleep 2
done
docker compose exec -T web python manage.py migrate --noinput
codigo="000"
teste='import urllib.request as u; print(u.urlopen("http://127.0.0.1:8000/entrar/", timeout=5).status)'
for _ in $(seq 1 15); do
  codigo="$(docker compose exec -T web python -c "$teste" 2>/dev/null | tr -d '\r' || true)"
  [ "$codigo" = "200" ] && break
  sleep 2
done
if [ "$codigo" != "200" ]; then
  docker compose logs --tail 60 web
  erro "O site não respondeu (HTTP $codigo). Veja os logs acima."
fi

if ! docker compose exec -T web sh -c 'touch /app/media/.teste_escrita && rm /app/media/.teste_escrita' 2>/dev/null; then
  amarelo "ATENÇÃO: o sistema subiu, mas NÃO consegue gravar fotos em $PASTA_IMAGENS."
  amarelo "Se o HD for ext4:   sudo chown -R $dono_uid:$dono_gid $PASTA_IMAGENS"
  amarelo "Se for NTFS/exFAT:  monte o HD com as opções uid=$dono_uid,gid=$dono_gid (no /etc/fstab)"
  amarelo "Depois rode o script de novo."
else
  verde "Teste de gravação na pasta de fotos: ok"
fi

echo
verde "================================================================"
verde " Pronto! Teste em:  http://$(hostname -I | awk '{print $1}'):$PORTA/"
verde " O sistema antigo continua rodando como antes."
verde " Backup do banco:   $(pwd)/$ARQ.gz"
verde " Fotos/arquivos:    $PASTA_IMAGENS (não entram no backup do banco)"
verde "================================================================"
docker compose ps
