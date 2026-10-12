from class_banco import Banco
from class_mysql import MysqlConection



<<<<<<< HEAD
dados = Banco().get_dados('vendas_feiras')
sql = 'INSERT INTO vendas_feiras (qnt, value, pagment, nomeFeira_id, product_id) values ('
sqls = []
for i in dados:
    sqls.append(f"""{sql}{i[1]}, {i[2]}, '{i[3]}', {i[4]}, {i[5]});""")

#for sql in sqls:
#     print(sql)
=======
dados = Banco().get_dados('vendas_precificacao')
sql = 'INSERT INTO vendas_precificacao (impressao, filament, embalagem, acessorios, custo, sugerido, vanda, product_id) values ('
sqls = []
for i in dados:
    dado = []
    for l in range(0, len(i)):   
        if i[l] is None:
            dado.append('null')
        else:
            dado.append(i[l])
    dado.pop(0)
    sqls.append(f"{sql}{dado[0]}, {dado[1]}, {dado[2]}, {dado[3]}, {dado[4]}, {dado[5]}, {dado[6]}, {dado[7]});")

#for l in sqls:
#    print(l)
>>>>>>> bccd26ece09e93b0d645b3bfd134b9963b8e6ba4
print(MysqlConection().insert_mysql(sqls))