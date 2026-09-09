import pymysql

class MysqlConection:
    def __init__(self):
        self.conexao = pymysql.connect(
            host='192.168.3.192',  # IP do servidor ou '127.0.0.1' se for local
            user='remoto',
            password='@Ede025978',
            database='pem_studio',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor  # Retorna os resultados como dicionários
            )
        self.cursor = self.conexao.cursor()


    def insert_mysql(self, lista: list):
        cont = 0
        for sql in lista:
            #try:
            self.cursor.execute(sql)
            #except:
            #        cont += 1
        self.conexao.commit()
        self.conexao.close()
        return cont