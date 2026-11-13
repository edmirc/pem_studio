# PEM Studio — rodando em Docker

O app roda num container (`pem-studio`) na mesma máquina do container do MySQL.
Os dois ficam numa rede Docker compartilhada (`pem-rede`), e o app acessa o
banco pelo nome do container.

## Jeito rápido (script)

```bash
cd ~/pem-studio
bash instalar-docker.sh          # ou: sudo bash instalar-docker.sh
```

O script faz tudo abaixo sozinho (backup, rede, build, migrações, teste) e pode
ser rodado de novo para atualizar. Os backups ficam em `backups/`.

## Primeira instalação (passo a passo manual)

```bash
# 1. Descobrir o nome do container do MySQL
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}'

# 2. Backup do banco ANTES de qualquer coisa
docker exec <container-mysql> sh -c 'mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines pem_studio' > ~/backup_pem_$(date +%F_%H%M).sql
ls -lh ~/backup_pem_*.sql   # confira que não está vazio

# 3. Criar a rede compartilhada e ligar o MySQL nela (não reinicia o MySQL)
docker network create pem-rede
docker network connect pem-rede <container-mysql>

# 4. Colocar o projeto numa pasta própria (sem mexer na instalação antiga)
mkdir -p ~/pem-studio
#   (copie os arquivos do projeto para ~/pem-studio)
cd ~/pem-studio

# 5. Criar o .env a partir do exemplo e preencher
cp env.exemplo .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # cole em DJANGO_SECRET_KEY
nano .env      # DB_HOST = nome do container do MySQL, DB_PASSWORD = senha
chmod 600 .env

# 6. Construir e subir (porta de teste 8001)
docker compose up -d --build
docker compose logs -f          # Ctrl+C para sair

# 7. Criar as tabelas novas (compras, insumos)
docker compose exec web python manage.py migrate
```

Teste em `http://192.168.3.190:8001/`.

## Trocar para a porta definitiva

Quando estiver tudo certo:

```bash
# parar o serviço antigo (não apaga nada)
sudo systemctl stop <servico-antigo> && sudo systemctl disable <servico-antigo>
# se era o nginx que atendia a porta 81, pare o site antigo ou o nginx

# no .env: PORTA=81  (e confira DJANGO_CSRF_TRUSTED_ORIGINS)
docker compose up -d
```

Para voltar ao antigo: `docker compose down` e `sudo systemctl enable --now <servico-antigo>`.

## Dia a dia

| O que | Comando (dentro de ~/pem-studio) |
|---|---|
| Atualizar depois de mudar o código | `docker compose up -d --build` e depois `docker compose exec web python manage.py migrate` |
| Ver logs | `docker compose logs -f --tail 100` |
| Reiniciar | `docker compose restart` |
| Criar usuário | `docker compose exec web python manage.py createsuperuser` |
| Shell do Django | `docker compose exec web python manage.py shell` |
| Status | `docker compose ps` |

O container reinicia sozinho se o servidor reiniciar (`restart: unless-stopped`).

## Fotos e arquivos das solicitações

Ficam no HD externo, em `PASTA_IMAGENS` do `.env` (padrão `/mnt/hd4t/imagens_pem_studio`),
dentro de `solicitacoes/<número>/`. O script confere se o HD está montado antes de subir
(para as fotos não irem parar no disco do sistema) e testa se o container consegue gravar lá.
Esses arquivos **não** entram no backup do banco; copie a pasta junto se for fazer cópia de segurança.

## Restaurar um backup

```bash
docker exec -i <container-mysql> sh -c 'mysql -u root -p"$MYSQL_ROOT_PASSWORD" pem_studio' < ~/backup_pem_AAAA-MM-DD_HHMM.sql
```
