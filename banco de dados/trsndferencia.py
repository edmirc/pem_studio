from class_banco import Banco
from class_mysql import MysqlConection



dados = Banco().get_dados('vendas_feiras')
sql = 'INSERT INTO vendas_feiras (qnt, value, pagment, nomeFeira_id, product_id) values ('
sqls = []
for i in dados:
    sqls.append(f"""{sql}{i[1]}, {i[2]}, '{i[3]}', {i[4]}, {i[5]});""")

#for sql in sqls:
#     print(sql)
print(MysqlConection().insert_mysql(sqls))