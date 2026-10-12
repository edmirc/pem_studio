from django.contrib import admin
from vendas.models import Precificacao, Feiras, VendasFeiras, VendasInternas
from django.db.models import Sum
from datetime import datetime
from django.db.models import Q

def convert_date(text: str):
    data_obj = datetime.strptime(text.strip(), '%d/%m/%Y')
    data_formatada = data_obj.strftime('%Y-%m-%d')
    return data_formatada


@admin.register(Precificacao)
class PrecificacaoAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'custo', 'sugerido', 'vanda',)
    search_fields = ('product__product',) # Permite buscar pelo produto se houver suporte
    list_filter = ('product', 'product__category')
    readonly_fields = ('custo', 'sugerido',)

@admin.register(Feiras)
class FeirasAdmin(admin.ModelAdmin):
    list_display = ('id', 'nomeFeira', 'product', 'qnt', 'value', 'pagment')
    list_filter = ('nomeFeira__name','nomeFeira__date','product__product' ,'pagment')
    search_fields = ('product__product', 'nomeFeira__name', 'nomeFeira__name') # Ajuste os campos de texto conforme os models externos se necessário
    def get_search_results(self, request, queryset, search_term):
                queryset, use_distinct = super().get_search_results(request, queryset, search_term)
                if search_term:
                    try:
                        data_formatada = convert_date(search_term)
                        filtro_data = Q(nomeFeira__date=data_formatada) # Use Q(date__date=data_formatada) se 'date' for DateTimeField
                        
                        # Une os resultados da busca padrão com os resultados filtrados pela data
                        queryset = queryset | self.model.objects.filter(filtro_data)
                    except ValueError:
                        # Se o que foi digitado não for uma data válida (ex: nome de um produto), ignora e segue o fluxo normal
                        pass
                        
                return queryset, use_distinct

@admin.register(VendasFeiras)
class VendasFeirasAdmin(admin.ModelAdmin):
    list_display = ('feira', 'total_debito', 'total_credito', 'total_pix', 'total_dinheiro', 'total_total')
    list_filter = ('feira__date', )
    search_fields = ('feira__date',)
    readonly_fields = ('total_debito', 'total_credito', 'total_pix', 'total_dinheiro', 'total_total',)

    def get_search_results(self, request, queryset, search_term):
            queryset, use_distinct = super().get_search_results(request, queryset, search_term)
            if search_term:
                try:
                    data_formatada = convert_date(search_term)
                    filtro_data = Q(feira__date=data_formatada) # Use Q(date__date=data_formatada) se 'date' for DateTimeField
                    
                    # Une os resultados da busca padrão com os resultados filtrados pela data
                    queryset = queryset | self.model.objects.filter(filtro_data)
                except ValueError:
                    # Se o que foi digitado não for uma data válida (ex: nome de um produto), ignora e segue o fluxo normal
                    pass
                    
            return queryset, use_distinct
 
@admin.register(VendasInternas)
class VendasInternasAdmin(admin.ModelAdmin):
    list_display = ('id', 'date', 'qnt', 'product', 'valor', 'client', 'pagment')
    list_filter = ('date', 'product__product' )
    search_fields = ('date', 'product__product')

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term:
            try:
                data_formatada = convert_date(search_term)
                filtro_data = Q(date=data_formatada) # Use Q(date__date=data_formatada) se 'date' for DateTimeField
                
                # Une os resultados da busca padrão com os resultados filtrados pela data
                queryset = queryset | self.model.objects.filter(filtro_data)
            except ValueError:
                # Se o que foi digitado não for uma data válida (ex: nome de um produto), ignora e segue o fluxo normal
                pass
                
        return queryset, use_distinct
    
