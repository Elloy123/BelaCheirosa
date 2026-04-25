from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("produto/<slug:slug>/", views.produto_detalhe, name="produto_detalhe"),

    path("carrinho/", views.carrinho_detalhe, name="carrinho"),
    path("carrinho/adicionar/<int:produto_id>/", views.carrinho_adicionar, name="carrinho_adicionar"),
    path("carrinho/atualizar/<int:produto_id>/", views.carrinho_atualizar, name="carrinho_atualizar"),
    path("carrinho/remover/<int:produto_id>/", views.carrinho_remover, name="carrinho_remover"),
    path("carrinho/limpar/", views.carrinho_limpar, name="carrinho_limpar"),
    path("checkout/", views.checkout, name="checkout"),

    path("painel/", views.dashboard, name="dashboard"),
    path("painel/completo/", views.dashboard_completo, name="dashboard_completo"),
    path("painel/vendas/", views.lista_vendas, name="lista_vendas"),
    path("painel/vendas/nova/", views.venda_nova, name="venda_nova"),
    path("painel/pedidos/", views.lista_pedidos, name="lista_pedidos"),
    path("painel/pedidos/<int:pk>/status/", views.pedido_atualizar_status, name="pedido_atualizar_status"),
    path("painel/vendas/<int:pk>/", views.venda_detalhe, name="venda_detalhe"),
    path("painel/vendas/<int:pk>/pdf/", views.venda_pdf, name="venda_pdf"),

    path("painel/produtos/", views.lista_produtos, name="lista_produtos"),
    path("painel/produtos/novo/", views.produto_form, name="produto_novo"),
    path("painel/produtos/<int:pk>/editar/", views.produto_form, name="produto_editar"),
    path("painel/produtos/categorias/<int:pk>/excluir/", views.categoria_excluir, name="categoria_excluir"),
    path("painel/produtos/categorias/novo/", views.categoria_rapida_form, name="categoria_rapida_form"),
    path("painel/produtos/subcategorias/novo/", views.subcategoria_rapida_form, name="subcategoria_rapida_form"),

    path("painel/estoque/", views.lista_estoque, name="lista_estoque"),
    path("painel/estoque/<int:pk>/movimentar/", views.movimentar_estoque, name="movimentar_estoque"),

    path("painel/clientes/", views.lista_clientes, name="lista_clientes"),
    path("painel/fiados/", views.lista_fiados, name="lista_fiados"),
    path("painel/fiados/novo/", views.fiado_form, name="fiado_novo"),
    path("painel/fiados/<int:pk>/pagamento/", views.fiado_atualizar_pagamento, name="fiado_atualizar_pagamento"),
    path("painel/fiados/<int:pk>/excluir/", views.fiado_excluir, name="fiado_excluir"),
    path("painel/boletos/", views.lista_contas_pagar, name="lista_contas_pagar"),
    path("painel/boletos/novo/", views.conta_pagar_form, name="conta_pagar_novo"),
    path("painel/boletos/<int:pk>/parcelas/", views.conta_pagar_adicionar_parcelas, name="conta_pagar_adicionar_parcelas"),
    path("painel/boletos/<int:pk>/pagamento/", views.conta_pagar_atualizar_pagamento, name="conta_pagar_atualizar_pagamento"),
    path("painel/boletos/<int:pk>/excluir/", views.conta_pagar_excluir, name="conta_pagar_excluir"),
    path("painel/clientes/novo/", views.cliente_form, name="cliente_novo"),
    path("painel/clientes/<int:pk>/editar/", views.cliente_form, name="cliente_editar"),
    path("painel/clientes/<int:pk>/", views.cliente_detalhe, name="cliente_detalhe"),

    path("painel/backup/", views.backup_banco, name="backup_banco"),
]