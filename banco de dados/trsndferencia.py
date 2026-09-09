from class_banco import Banco
from class_mysql import MysqlConection



dados = Banco().get_dados('vendas_precificacao')
sql = 'INSERT INTO vendas_precificacao (impressao, filament, embalagem, acessorios, custos, sugerido, vanda, product_id) values ('
sqls = []
for i in dados:
    for l in range(0, len(i)):
        dado = ''
        if l is None:
            dado = 'null'
        else:
            dado = l
            
    sqls.append(f"{sql}{dado}, {i[2]}, {i[3]}, {i[4]}, {i[5]}, {i[6]}, {i[7]}, {i[8]});")

for l in sqls:
    print(l)
#print(MysqlConection().insert_mysql(sqls))