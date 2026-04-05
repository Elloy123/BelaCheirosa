from django.contrib import admin

from .models import (
	Categoria,
	Cliente,
	ContaPagar,
	FiadoConta,
	ItemPedido,
	ItemVenda,
	MovimentacaoEstoque,
	Pedido,
	Produto,
	Venda,
)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
	list_display = ("nome", "parent", "slug")
	list_filter = ("parent",)
	search_fields = ("nome", "slug", "parent__nome")


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
	list_display = ("nome", "codigo", "categoria", "preco", "estoque", "ativo")
	list_filter = ("ativo", "categoria")
	search_fields = ("nome", "codigo", "slug")


class ItemVendaInline(admin.TabularInline):
	model = ItemVenda
	extra = 0


class ItemPedidoInline(admin.TabularInline):
	model = ItemPedido
	extra = 0


@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):
	list_display = ("id", "cliente", "forma_pagamento", "status", "data")
	list_filter = ("status", "forma_pagamento", "data")
	search_fields = ("id", "cliente__nome")
	inlines = [ItemVendaInline]


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
	list_display = ("nome", "telefone", "situacao", "limite_credito")
	list_filter = ("situacao",)
	search_fields = ("nome", "cpf", "telefone")


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
	list_display = ("produto", "tipo", "quantidade", "responsavel", "data")
	list_filter = ("tipo", "data")
	search_fields = ("produto__nome", "observacao", "responsavel")


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
	list_display = ("id", "cliente_nome", "forma_pagamento", "status", "criado_em")
	list_filter = ("status", "forma_pagamento", "criado_em")
	search_fields = ("id", "cliente_nome", "cliente_endereco")
	inlines = [ItemPedidoInline]


@admin.register(FiadoConta)
class FiadoContaAdmin(admin.ModelAdmin):
	list_display = ("cliente", "referencia", "valor_total", "valor_pago", "vencimento", "status")
	list_filter = ("status", "vencimento")
	search_fields = ("cliente__nome", "referencia")


@admin.register(ContaPagar)
class ContaPagarAdmin(admin.ModelAdmin):
	list_display = (
		"fornecedor",
		"referencia",
		"parcela_numero",
		"parcelas_total",
		"valor_total",
		"valor_pago",
		"vencimento",
		"data_pagamento",
		"status",
	)
	list_filter = ("status", "vencimento", "data_pagamento")
	search_fields = ("fornecedor", "referencia")

# Register your models here.
