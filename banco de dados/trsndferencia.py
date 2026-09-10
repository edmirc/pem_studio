from class_banco import Banco
from class_mysql import MysqlConection



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
print(MysqlConection().insert_mysql(sqls))