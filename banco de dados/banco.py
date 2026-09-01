

import csv
import sqlite3
from class_banco import Banco







# 2. Abre e lê o arquivo CSV
print("Digite o número referente a tabela: \n1 -> Categoria \n2 -> Produtos \n3 -> Filamentos \n4 -> Precificação")
res = int(input("Digite o número da ação: "))
dict = {1: "Categorias", 2: "Produtos", 3: "filamento", 4: "precificar"}
arquivo = dict[res]
csv_file_path = f"C:\\projetos\\pem studio\\banco de dados\\{arquivo}.CSV"
with open(csv_file_path, mode="r", encoding="utf-8") as file:
  reader = csv.DictReader(file, delimiter=";")
  headers = reader.fieldnames

  if not headers:
    print("Erro: O arquivo CSV está vazio ou não possui cabeçalho.")



  # 5. Coleta os dados das linhas
  rows = []
  db_file_path = 'C:\\projetos\\pem studio\\db.sqlite3'
  #conn = sqlite3.connect(db_file_path)S
  cont = 1
  for row in reader:
    rows.append(tuple(row[header] for header in headers))
  if res == 1:
    Banco().category(rows)
  elif res == 2:
    Banco().product(rows)
  elif res == 3:
    Banco().filament(rows)
  elif res == 4:
    Banco().precificar(rows)
  else:
    print("Número inválido!!!")
   