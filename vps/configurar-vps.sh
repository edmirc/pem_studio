#!/usr/bin/env bash
# ==========================================================================
# PEM Studio — configura a VPS (Debian) como porta de entrada pela internet
#
#   pemstudio.com.br          -> site da empresa (arquivos desta VPS)
#   sistema.pemstudio.com.br  -> sistema no servidor de casa, pelo Tailscale
#
# Uso, como root, na pasta onde estão "vps/" e "site/":
#     bash vps/configurar-vps.sh
# Pode rodar de novo para atualizar o site ou a configuração.
# ==========================================================================
set -euo pipefail

DOMINIO="${DOMINIO:-pemstudio.com.br}"
SISTEMA="${SISTEMA:-sistema.$DOMINIO}"
CASA="${CASA:-100.116.208.105:8001}"       # IP do Tailscale do servidor de casa : porta do sistema
EMAIL="${EMAIL:-pem.studio3d@gmail.com}"   # avisos do certificado HTTPS
PASTA_SITE_DESTINO=/var/www/pemstudio

AQUI="$(cd "$(dirname "$0")" && pwd)"
PASTA_SITE="$AQUI/../site"

verde() { printf '\033[32m%s\033[0m\n' "$*"; }
amarelo() { printf '\033[33m%s\033[0m\n' "$*"; }
erro() { printf '\033[31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }
passo() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

[ "$(id -u)" = "0" ] || erro "Rode como root:  sudo bash vps/configurar-vps.sh"
[ -f "$PASTA_SITE/index.html" ] || erro "Não achei $PASTA_SITE/index.html. Envie as pastas 'vps' e 'site' juntas."
[ -f "$AQUI/Caddyfile.modelo" ] || erro "Não achei $AQUI/Caddyfile.modelo."
grep -q "whatsapp: ''" "$PASTA_SITE/js/site.js" && amarelo "Aviso: o WhatsApp ainda não foi preenchido em site/js/site.js."

# ---------------------------------------------------------------- 1. portas
passo "1/7 Conferindo as portas 80 e 443"
ocupadas="$(ss -ltnpH '( sport = :80 or sport = :443 )' 2>/dev/null | grep -v caddy || true)"
if [ -n "$ocupadas" ]; then
  echo "$ocupadas"
  erro "Outro programa está usando a porta 80/443 (veja acima). Pare-o (ex.: systemctl disable --now apache2 nginx) e rode de novo."
fi
verde "Portas livres."

# --------------------------------------------------------------- 2. pacotes
passo "2/7 Instalando o Caddy (servidor web com HTTPS automático)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates gnupg debian-archive-keyring bind9-dnsutils iproute2 >/dev/null
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
fi
verde "$(caddy version | head -1)"

# ------------------------------------------------------------- 3. Tailscale
passo "3/7 Tailscale (túnel até o servidor de casa)"
if ! command -v tailscale >/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
if ! tailscale status >/dev/null 2>&1; then
  amarelo "Vai aparecer um link: abra no navegador e entre com a MESMA conta do Tailscale do servidor de casa."
  tailscale up --hostname=vps-pemstudio
fi
verde "VPS no Tailscale: $(tailscale ip -4 | head -1)"

# ------------------------------------------------- 4. túnel até o sistema
passo "4/7 Testando o acesso ao sistema em casa ($CASA)"
codigo="$(curl -s -o /dev/null -m 10 -w '%{http_code}' "http://$CASA/entrar/" || true)"
case "$codigo" in
  200) verde "Sistema respondeu pelo túnel." ;;
  400) amarelo "O sistema respondeu, mas recusou o endereço (HTTP 400). No servidor de casa, rode o instalar-docker.sh de novo para liberar $SISTEMA." ;;
  *)   amarelo "O sistema não respondeu (código '$codigo'). Confira se o container pem-studio está rodando em casa e se os dois aparecem em 'tailscale status'. Sigo com o resto." ;;
esac

# ------------------------------------------------------------------ 5. site
passo "5/7 Publicando o site em $PASTA_SITE_DESTINO"
mkdir -p "$PASTA_SITE_DESTINO"
tmp="$(mktemp -d)"
cp -r "$PASTA_SITE"/. "$tmp"/
rm -f "$tmp/LEIA-ME.md"
rm -rf "$PASTA_SITE_DESTINO.antigo"
[ -n "$(ls -A "$PASTA_SITE_DESTINO" 2>/dev/null)" ] && mv "$PASTA_SITE_DESTINO" "$PASTA_SITE_DESTINO.antigo" && mkdir -p "$PASTA_SITE_DESTINO"
cp -r "$tmp"/. "$PASTA_SITE_DESTINO"/ && rm -rf "$tmp"
find "$PASTA_SITE_DESTINO" -type d -exec chmod 755 {} + ; find "$PASTA_SITE_DESTINO" -type f -exec chmod 644 {} +
verde "Site copiado ($(find "$PASTA_SITE_DESTINO" -type f | wc -l) arquivos). A versão anterior ficou em $PASTA_SITE_DESTINO.antigo"

# ------------------------------------------------------------- 6. Caddyfile
passo "6/7 Configurando endereços e HTTPS"
[ -f /etc/caddy/Caddyfile ] && cp /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak.$(date +%F_%H%M%S)"
email_linha="# sem e-mail (opcional: EMAIL=voce@exemplo.com bash vps/configurar-vps.sh)"
[ -n "$EMAIL" ] && email_linha="email $EMAIL"
sed -e "s|{{EMAIL_LINHA}}|$email_linha|g" -e "s|{{SITE}}|$DOMINIO|g" -e "s|{{WWW}}|www.$DOMINIO|g" \
    -e "s|{{SITE_URL}}|https://$DOMINIO|g" -e "s|{{SISTEMA}}|$SISTEMA|g" -e "s|{{CASA}}|$CASA|g" \
    "$AQUI/Caddyfile.modelo" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || { caddy validate --config /etc/caddy/Caddyfile; erro "Configuração do Caddy inválida."; }
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; verde "Firewall (ufw): portas 80 e 443 liberadas."
fi
systemctl enable caddy >/dev/null 2>&1
systemctl reload caddy 2>/dev/null || systemctl restart caddy
verde "Caddy configurado."

# ------------------------------------------------------------------ 7. DNS
passo "7/7 Conferindo o DNS"
ip_vps="$(curl -s -4 -m 8 https://api.ipify.org || true)"
falta=0
for nome in "$DOMINIO" "www.$DOMINIO" "$SISTEMA"; do
  aponta="$(dig +short A "$nome" @1.1.1.1 | tail -1)"
  if [ "$aponta" = "$ip_vps" ]; then verde "  $nome -> $aponta  ok"
  else amarelo "  $nome -> ${aponta:-(nada)}   precisa apontar para $ip_vps"; falta=1; fi
done

echo
if [ "$falta" = "1" ]; then
  amarelo "================================================================"
  amarelo " Falta o DNS: no Registro.br, crie registros do tipo A apontando"
  amarelo " para $ip_vps (veja acima). O HTTPS é emitido sozinho alguns"
  amarelo " minutos depois que o DNS estiver certo. Não precisa rodar de novo."
  amarelo "================================================================"
else
  verde "================================================================"
  verde " Pronto!  https://$DOMINIO   e   https://$SISTEMA"
  verde " (o certificado HTTPS pode levar 1 a 2 minutos na primeira vez)"
  verde "================================================================"
fi
