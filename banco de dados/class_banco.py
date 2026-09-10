import sqlite3
from decimal import Decimal

class Banco:
    def __init__(self):
        self.conn = self.get_connection()
        self.cursor = self.conn.cursor()

    def get_connection(self):
        con = None
        try:
            con = sqlite3.connect('C:\\projetos\\pem studio\\db.sqlite3')
        except:
            con = sqlite3.connect('C:\\Projetos\\pem_studio\\db.sqlite3')
        return con

    def insert(self, sql: list):
            cont = 0
            for query in sql:
                try:
                    self.cursor.execute(query)
                    self.conn.commit()
                except:
                    cont += 1
            return cont


    def get_id(self, talbe: str, campo: str, dado: str):
        sql = f"select id from {talbe} where {campo} = '{dado}';"
        self.cursor.execute(sql)
        id = self.cursor.fetchone()
        try:
            id = id[0]
        except:
            id = None
        return id

    def category(self, rows: list):
        sql: list = []
        for row in rows:
            sql.append(f"INSERT INTO cadastro_category (category) values ('{row[0]}');")
        cont = self.insert(sql)
        print(cont)
        self.conn.close()

    def product(self, rows: list):
        insets: str = "insert into cadastro_product (product, category_id) values ("
        sql_p: list = []
        for row in rows:
            id = self.get_id("cadastro_category", 'category', row[1])
            sql_p.append(f"{insets} '{row[0]}', {id});")
        cont = self.insert(sql_p)
        print(cont)
        self.conn.close()

    def filament(self, rows: list):
        text = "INSERT INTO cadastro_filment (name, color, filamentBrand_id, filamentType_id) values ("
        sql_l = []
        for row in rows:
            nome = row[0].split()
            cor = nome[0]
            brand = self.get_id("cadastro_filamentbrand", "name", row[1])
            type = self.get_id("cadastro_filamettype", "type", row[2])
            sql_l.append(f"{text}'{row[0]}', '{cor}', {brand}, {type});")
        cont = self.insert(sql_l)
        print(cont)
        self.conn.close()

    def dadosPrecificacao(self, rows: list) -> list:
        dados = []
        for row in rows:
            dado = {}
            cont = 0
            for r in row:
                if cont > 0:
                    r = r.replace(",", ".")
                v = r.isdigit()
                if v:
                    r =  Decimal(r)
                if r == '':
                    r = None
                dado[cont] = r
                cont += 1
            dados.append(dado)
        return dados

    def precificar(self, rows: list):
    
        text = "INSERT INTO vendas_precificacao (product_id, impressao, filament, embalagem, acessorios, custo, sugerido, vanda) values ("
        sql_l = []
        lista = self.dadosPrecificacao(rows)
        for i in lista:
            cont = 0
            for r in i:
                if i[cont] is None:
                    i[cont] = "Null"
                cont += 1
            try:
                idProduct = self.get_id('cadastro_product', 'product', i[0])
                if idProduct is not None or i[1] is not None or i[2] is not None:
                    sql = f"{text}{idProduct}, {i[1]}, {i[2]}, {i[3]}, {i[4]}, {i[5]}, {i[6]}, {i[7]});"
                    sql_l.append(sql)
            except:
                pass
        cont = self.insert(sql_l)
        print(cont)
        self.conn.close

    def get_dados(self, table: str) -> list :
        sql = F"SELECT * FROM {table};"
        self.cursor.execute(sql)
        dados = []
        for i in self.cursor.fetchall():
            dados.append(i)
        self.conn.close()
        return dados
        