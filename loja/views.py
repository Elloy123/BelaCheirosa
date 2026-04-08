from decimal import Decimal, InvalidOperation
from datetime import date, timedelta
from uuid import uuid4
from urllib.parse import quote_plus

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.utils import timezone

from .cart import Carrinho
from .forms import ClienteForm, ProdutoForm
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
from .pdf_utils import gerar_pdf_venda


def _gerar_slug_produto(nome, produto_id=None):
	base = slugify(nome) or "produto"
	slug = base
	contador = 1
	while True:
		query = Produto.objects.filter(slug=slug)
		if produto_id:
			query = query.exclude(pk=produto_id)
		if not query.exists():
			return slug
		contador += 1
		slug = f"{base}-{contador}"


def _gerar_slug_categoria(nome):
	base = slugify(nome) or "categoria"
	slug = base
	contador = 1
	while Categoria.objects.filter(slug=slug).exists():
		contador += 1
		slug = f"{base}-{contador}"
	return slug


def _add_months(base_date, months):
	month_index = (base_date.month - 1) + months
	year = base_date.year + (month_index // 12)
	month = (month_index % 12) + 1
	last_day = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
	day = min(base_date.day, last_day)
	return date(year, month, day)


def _status_por_pagamento(valor_total, valor_pago):
	if valor_pago <= 0:
		return "pendente"
	if valor_pago < valor_total:
		return "parcial"
	return "pago"


def home(request):
	slug = request.GET.get("cat")
	filtro = request.GET.get("filtro", "padrao")
	busca = request.GET.get("q", "").strip()

	base_produtos = Produto.objects.filter(ativo=True).select_related("categoria")
	produtos = base_produtos
	categoria_ativa = None
	categoria_pai_ativa = None
	subcategorias_ativas = []

	if slug:
		categoria_ativa = get_object_or_404(Categoria, slug=slug)
		if categoria_ativa.parent_id:
			categoria_pai_ativa = categoria_ativa.parent
			produtos = produtos.filter(categoria=categoria_ativa)
			subcategorias_ativas = list(
				categoria_pai_ativa.subcategorias.all().order_by("nome")
			)
		else:
			categoria_pai_ativa = categoria_ativa
			produtos = produtos.filter(
				Q(categoria=categoria_ativa) | Q(categoria__parent=categoria_ativa)
			)
			subcategorias_ativas = list(categoria_ativa.subcategorias.all().order_by("nome"))

	if busca:
		produtos = produtos.filter(
			Q(nome__icontains=busca)
			| Q(codigo__icontains=busca)
			| Q(descricao__icontains=busca)
		)

	if filtro == "mais_vendidos":
		produtos = produtos.order_by("-vendas", "nome")
	elif filtro == "mais_baratos":
		produtos = produtos.order_by("preco", "nome")
	elif filtro == "mais_caros":
		produtos = produtos.order_by("-preco", "nome")

	carrinho = Carrinho(request)
	return render(
		request,
		"loja/home.html",
		{
			"produtos": produtos,
			"categoria_ativa": categoria_ativa,
			"categoria_pai_ativa": categoria_pai_ativa,
			"subcategorias_ativas": subcategorias_ativas,
			"filtro_ativo": filtro,
			"busca": busca,
			"carrinho_qtd": carrinho.count(),
		},
	)


def produto_detalhe(request, slug):
	produto = get_object_or_404(Produto, slug=slug, ativo=True)
	relacionados = Produto.objects.filter(
		ativo=True, categoria=produto.categoria
	).exclude(id=produto.id)[:6]
	carrinho = Carrinho(request)
	return render(
		request,
		"loja/produto_detalhe.html",
		{
			"produto": produto,
			"relacionados": relacionados,
			"carrinho_qtd": carrinho.count(),
		},
	)


def carrinho_detalhe(request):
	carrinho = Carrinho(request)
	clientes = Cliente.objects.all().order_by("nome")
	return render(
		request,
		"loja/carrinho.html",
		{
			"itens": list(carrinho),
			"total": carrinho.total(),
			"clientes": clientes,
			"carrinho_qtd": carrinho.count(),
			"formas": Venda.FORMA_PAGAMENTO,
		},
	)


def carrinho_adicionar(request, produto_id):
	if request.method != "POST":
		return redirect("home")

	produto = get_object_or_404(Produto, id=produto_id, ativo=True)
	carrinho = Carrinho(request)

	try:
		qtd = int(request.POST.get("qtd", "1"))
	except ValueError:
		qtd = 1

	if qtd <= 0:
		messages.error(request, "Quantidade inválida.")
		return redirect(request.POST.get("next", "home"))

	if qtd > produto.estoque:
		messages.error(request, f"Estoque insuficiente. Disponível: {produto.estoque}.")
		return redirect(request.POST.get("next", "home"))

	carrinho.add(produto, qtd=qtd)
	messages.success(request, f"Adicionado ao carrinho: {produto.nome}")
	return redirect(request.POST.get("next", "home"))


def carrinho_atualizar(request, produto_id):
	if request.method != "POST":
		return redirect("carrinho")

	produto = get_object_or_404(Produto, id=produto_id, ativo=True)
	carrinho = Carrinho(request)

	try:
		qtd = int(request.POST.get("qtd", "1"))
	except ValueError:
		qtd = 1

	if qtd < 0:
		messages.error(request, "Quantidade inválida.")
		return redirect("carrinho")

	if qtd > produto.estoque:
		messages.error(request, f"Estoque insuficiente. Disponível: {produto.estoque}.")
		return redirect("carrinho")

	carrinho.add(produto, qtd=qtd, override=True)
	messages.success(request, "Carrinho atualizado.")
	return redirect("carrinho")


def carrinho_remover(request, produto_id):
	carrinho = Carrinho(request)
	carrinho.remove(produto_id)
	messages.success(request, "Item removido.")
	return redirect("carrinho")


def carrinho_limpar(request):
	carrinho = Carrinho(request)
	carrinho.clear()
	messages.success(request, "Carrinho limpo.")
	return redirect("carrinho")


def checkout(request):
	if request.method != "POST":
		return redirect("carrinho")

	carrinho = Carrinho(request)
	itens = list(carrinho)
	if not itens:
		messages.error(request, "Carrinho vazio.")
		return redirect("carrinho")

	nome_cliente = request.POST.get("nome_cliente", "").strip()
	endereco_cliente = request.POST.get("endereco_cliente", "").strip()
	forma = request.POST.get("forma_pagamento", "dinheiro")
	desconto = Decimal(request.POST.get("desconto", "0") or "0")
	observacao = request.POST.get("observacao", "").strip()

	total_bruto = sum(item["subtotal"] for item in itens)
	total_final = total_bruto - desconto

	pedido = Pedido.objects.create(
		cliente_nome=nome_cliente,
		cliente_endereco=endereco_cliente,
		forma_pagamento=forma,
		desconto=desconto,
		observacao=observacao,
		status="pendente",
	)
	for item in itens:
		produto = get_object_or_404(Produto, id=item["produto_id"], ativo=True)
		ItemPedido.objects.create(
			pedido=pedido,
			produto=produto,
			quantidade=item["qtd"],
			preco_unitario=item["preco"],
		)

	linhas = [
		f"Olá! Gostaria de finalizar este pedido #{pedido.id}:",
		"",
		"*Itens do carrinho:*",
	]
	for item in itens:
		linhas.append(
			f"- {item['nome']} | Qtd: {item['qtd']} | Subtotal: R$ {item['subtotal']:.2f}"
		)

	linhas.extend([
		"",
		f"Subtotal: R$ {total_bruto:.2f}",
		f"Desconto: R$ {desconto:.2f}",
		f"*Total: R$ {total_final:.2f}*",
		"",
		"*Dados do cliente:*",
		f"Nome: {nome_cliente or 'Não informado'}",
		f"Endereço: {endereco_cliente or 'Não informado'}",
		f"Pagamento: {dict(Venda.FORMA_PAGAMENTO).get(forma, forma)}",
	])

	if observacao:
		linhas.append(f"Observação: {observacao}")

	mensagem = quote_plus("\n".join(linhas))
	numero = settings.LOJA_WHATSAPP
	url = f"https://wa.me/{numero}?text={mensagem}"
	carrinho.clear()
	return redirect(url)


@staff_member_required(login_url="/admin/login/")
def dashboard(request):
	hoje = timezone.now().date()
	inicio_mes = hoje.replace(day=1)

	vendas_hoje = Venda.objects.filter(data__date=hoje, status="concluida")
	vendas_mes = Venda.objects.filter(data__date__gte=inicio_mes, status="concluida")

	faturamento_hoje = sum(v.total for v in vendas_hoje)
	faturamento_mes = sum(v.total for v in vendas_mes)
	lucro_mes = sum(
		(item.preco_unitario - item.produto.custo) * item.quantidade
		for venda in vendas_mes
		for item in venda.itens.select_related("produto").all()
	)

	baixo_estoque = Produto.objects.filter(ativo=True, estoque__lte=F("estoque_minimo"))
	ultimas_vendas = Venda.objects.select_related("cliente")[:10]

	vendas_por_forma = (
		vendas_mes.values("forma_pagamento")
		.annotate(qtd=Count("id"), total=Sum("itens__preco_unitario"))
		.order_by("-qtd")
	)

	fiados_alerta = FiadoConta.objects.filter(
		status__in=["pendente", "parcial"],
		vencimento__lte=hoje + timedelta(days=3),
	)
	boletos_alerta = ContaPagar.objects.filter(
		status__in=["pendente", "parcial"],
		vencimento__lte=hoje + timedelta(days=3),
	)
	pedidos_pendentes = Pedido.objects.filter(status="pendente").count()

	return render(
		request,
		"admin_panel/dashboard.html",
		{
			"faturamento_hoje": faturamento_hoje,
			"faturamento_mes": faturamento_mes,
			"lucro_mes": lucro_mes,
			"qtd_vendas_hoje": vendas_hoje.count(),
			"qtd_produtos": Produto.objects.filter(ativo=True).count(),
			"qtd_clientes": Cliente.objects.count(),
			"baixo_estoque": baixo_estoque[:8],
			"qtd_baixo_estoque": baixo_estoque.count(),
			"ultimas_vendas": ultimas_vendas,
			"vendas_por_forma": vendas_por_forma,
			"pedidos_pendentes": pedidos_pendentes,
			"fiados_alerta": fiados_alerta.count(),
			"boletos_alerta": boletos_alerta.count(),
		},
	)


@staff_member_required(login_url="/admin/login/")
def lista_pedidos(request):
	status = request.GET.get("status", "pendente")
	pedidos = Pedido.objects.prefetch_related("itens__produto")
	if status:
		pedidos = pedidos.filter(status=status)
	return render(
		request,
		"admin_panel/lista_pedidos.html",
		{"pedidos": pedidos[:200], "status": status, "status_choices": Pedido.STATUS},
	)


@staff_member_required(login_url="/admin/login/")
def pedido_atualizar_status(request, pk):
	pedido = get_object_or_404(Pedido.objects.prefetch_related("itens__produto"), pk=pk)
	novo_status = request.POST.get("status", "")
	if novo_status not in {"pendente", "concluido", "cancelado"}:
		return redirect("lista_pedidos")

	if pedido.status != "concluido" and novo_status == "concluido":
		venda = Venda.objects.create(
			cliente=Cliente.objects.filter(nome=pedido.cliente_nome).first(),
			forma_pagamento=pedido.forma_pagamento,
			desconto=pedido.desconto,
			observacao=f"Origem pedido #{pedido.id}. {pedido.observacao}".strip(),
			status="pendente" if pedido.forma_pagamento == "fiado" else "concluida",
		)
		for item in pedido.itens.all():
			if item.quantidade > item.produto.estoque:
				messages.error(request, f"Estoque insuficiente para {item.produto.nome}.")
				venda.delete()
				return redirect("lista_pedidos")
			ItemVenda.objects.create(
				venda=venda,
				produto=item.produto,
				quantidade=item.quantidade,
				preco_unitario=item.preco_unitario,
			)
			item.produto.vendas += item.quantidade
			item.produto.save(update_fields=["vendas"])
			MovimentacaoEstoque.objects.create(
				produto=item.produto,
				tipo="saida",
				quantidade=item.quantidade,
				observacao=f"Baixa pedido #{pedido.id}",
				responsavel=request.user.username,
			)

	pedido.status = novo_status
	pedido.save(update_fields=["status"])
	messages.success(request, f"Pedido #{pedido.id} atualizado para {pedido.get_status_display()}.")
	return redirect("lista_pedidos")


@staff_member_required(login_url="/admin/login/")
def lista_vendas(request):
	q = request.GET.get("q", "").strip()
	status = request.GET.get("status", "").strip()
	forma = request.GET.get("forma", "").strip()

	vendas = Venda.objects.select_related("cliente").prefetch_related("itens")
	if q:
		vendas = vendas.filter(Q(cliente__nome__icontains=q) | Q(id__icontains=q))
	if status:
		vendas = vendas.filter(status=status)
	if forma:
		vendas = vendas.filter(forma_pagamento=forma)

	total_filtrado = sum(v.total for v in vendas)
	return render(
		request,
		"admin_panel/lista_vendas.html",
		{
			"vendas": vendas[:150],
			"total_filtrado": total_filtrado,
			"status_choices": Venda.STATUS,
			"forma_choices": Venda.FORMA_PAGAMENTO,
			"q": q,
			"status": status,
			"forma": forma,
		},
	)


@staff_member_required(login_url="/admin/login/")
def venda_detalhe(request, pk):
	venda = get_object_or_404(
		Venda.objects.select_related("cliente").prefetch_related("itens__produto"),
		pk=pk,
	)
	return render(request, "admin_panel/venda_detalhe.html", {"venda": venda})


@staff_member_required(login_url="/admin/login/")
def venda_pdf(request, pk):
	venda = get_object_or_404(
		Venda.objects.select_related("cliente").prefetch_related("itens__produto"),
		pk=pk,
	)
	buffer = gerar_pdf_venda(venda)
	response = HttpResponse(buffer, content_type="application/pdf")
	response["Content-Disposition"] = f'inline; filename="venda_{pk:05d}.pdf"'
	return response


@staff_member_required(login_url="/admin/login/")
def lista_estoque(request):
	q = request.GET.get("q", "").strip()
	situacao = request.GET.get("situacao", "")

	produtos = Produto.objects.filter(ativo=True).select_related("categoria")
	if q:
		produtos = produtos.filter(Q(nome__icontains=q) | Q(codigo__icontains=q))

	resultado = []
	for p in produtos:
		if p.estoque == 0:
			sit = "Zerado"
		elif p.estoque <= p.estoque_minimo:
			sit = "Baixo"
		else:
			sit = "OK"
		if situacao and sit != situacao:
			continue
		resultado.append(
			{"produto": p, "situacao": sit, "valor_estoque": p.custo * p.estoque}
		)

	return render(
		request,
		"admin_panel/lista_estoque.html",
		{
			"resultado": resultado,
			"q": q,
			"situacao": situacao,
			"qtd_baixo": sum(1 for r in resultado if r["situacao"] == "Baixo"),
			"qtd_zerado": sum(1 for r in resultado if r["situacao"] == "Zerado"),
			"total_valor": sum(r["valor_estoque"] for r in resultado),
		},
	)


@staff_member_required(login_url="/admin/login/")
def lista_produtos(request):
	q = request.GET.get("q", "").strip()
	cat = request.GET.get("cat", "").strip()

	produtos = Produto.objects.select_related("categoria", "categoria__parent").all()
	if q:
		produtos = produtos.filter(Q(nome__icontains=q) | Q(codigo__icontains=q))
	if cat:
		produtos = produtos.filter(
			Q(categoria__slug=cat) | Q(categoria__parent__slug=cat)
		)

	return render(
		request,
		"admin_panel/lista_produtos.html",
		{
			"produtos": produtos[:300],
			"q": q,
			"cat": cat,
			"categorias_pai": Categoria.objects.filter(parent__isnull=True).order_by("nome"),
		},
	)


@staff_member_required(login_url="/admin/login/")
def produto_form(request, pk=None):
	produto = get_object_or_404(Produto, pk=pk) if pk else None
	nome_antigo = produto.nome if produto else ""

	if request.method == "POST":
		form = ProdutoForm(request.POST, request.FILES, instance=produto)
		if form.is_valid():
			obj = form.save(commit=False)
			if not obj.slug or (nome_antigo and nome_antigo != obj.nome):
				obj.slug = _gerar_slug_produto(obj.nome, produto_id=obj.pk)
			obj.save()
			messages.success(request, "Produto salvo com sucesso.")
			return redirect("lista_produtos")
	else:
		form = ProdutoForm(instance=produto)

	categorias_sub = list(
		Categoria.objects.filter(parent__isnull=False)
		.values("id", "nome", "parent_id")
		.order_by("nome")
	)
	return render(
		request,
		"admin_panel/produto_form.html",
		{
			"form": form,
			"produto": produto,
			"categorias_sub": categorias_sub,
			"categorias_pai": Categoria.objects.filter(parent__isnull=True).order_by("nome"),
		},
	)


@staff_member_required(login_url="/admin/login/")
def categoria_rapida_form(request):
	if request.method != "POST":
		return redirect("produto_novo")

	next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/painel/produtos/novo/"
	nome = request.POST.get("nome", "").strip()
	if not nome:
		messages.error(request, "Informe o nome da categoria principal.")
		return redirect(next_url)

	existente = Categoria.objects.filter(parent__isnull=True, nome__iexact=nome).first()
	if existente:
		messages.info(request, f"Categoria ja existente: {existente.nome}.")
		return redirect(next_url)

	Categoria.objects.create(nome=nome, slug=_gerar_slug_categoria(nome))
	messages.success(request, "Categoria principal criada com sucesso.")
	return redirect(next_url)


@staff_member_required(login_url="/admin/login/")
def subcategoria_rapida_form(request):
	if request.method != "POST":
		return redirect("produto_novo")

	next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/painel/produtos/novo/"
	nome = request.POST.get("nome", "").strip()
	parent_id = request.POST.get("categoria_pai_id", "").strip()

	if not nome or not parent_id:
		messages.error(request, "Informe a categoria principal e o nome da subcategoria.")
		return redirect(next_url)

	pai = get_object_or_404(Categoria, pk=parent_id, parent__isnull=True)
	existente = Categoria.objects.filter(parent=pai, nome__iexact=nome).first()
	if existente:
		messages.info(request, f"Subcategoria ja existente em {pai.nome}: {existente.nome}.")
		return redirect(next_url)

	Categoria.objects.create(nome=nome, slug=_gerar_slug_categoria(nome), parent=pai)
	messages.success(request, "Subcategoria criada com sucesso.")
	return redirect(next_url)


@staff_member_required(login_url="/admin/login/")
def movimentar_estoque(request, pk):
	produto = get_object_or_404(Produto, pk=pk)
	historico = produto.movimentacoes.all()[:20]

	if request.method == "POST":
		tipo = request.POST.get("tipo")
		quantidade = int(request.POST.get("quantidade", "0") or "0")
		observacao = request.POST.get("observacao", "").strip()
		if quantidade > 0 and tipo in {"entrada", "saida", "ajuste"}:
			MovimentacaoEstoque.objects.create(
				produto=produto,
				tipo=tipo,
				quantidade=quantidade,
				observacao=observacao,
				responsavel=request.user.username,
			)
			messages.success(request, "Movimentação registrada.")
		return redirect("lista_estoque")

	return render(
		request,
		"admin_panel/movimentar_estoque.html",
		{"produto": produto, "historico": historico},
	)


@staff_member_required(login_url="/admin/login/")
def lista_clientes(request):
	q = request.GET.get("q", "").strip()
	situacao = request.GET.get("situacao", "").strip()

	clientes = Cliente.objects.all()
	if q:
		clientes = clientes.filter(
			Q(nome__icontains=q) | Q(cpf__icontains=q) | Q(telefone__icontains=q)
		)
	if situacao:
		clientes = clientes.filter(situacao=situacao)

	return render(
		request,
		"admin_panel/lista_clientes.html",
		{
			"clientes": clientes,
			"situacoes": Cliente.SITUACAO_CHOICES,
			"q": q,
			"sit": situacao,
		},
	)


@staff_member_required(login_url="/admin/login/")
def cliente_form(request, pk=None):
	cliente = get_object_or_404(Cliente, pk=pk) if pk else None

	if request.method == "POST":
		form = ClienteForm(request.POST, instance=cliente)
		if form.is_valid():
			form.save()
			messages.success(request, "Cliente salvo com sucesso.")
			return redirect("lista_clientes")
	else:
		form = ClienteForm(instance=cliente)

	return render(request, "admin_panel/cliente_form.html", {"form": form, "cliente": cliente})


@staff_member_required(login_url="/admin/login/")
def cliente_detalhe(request, pk):
	cliente = get_object_or_404(Cliente, pk=pk)
	vendas = cliente.vendas.all().prefetch_related("itens")
	total_gasto = sum(v.total for v in vendas.filter(status="concluida"))
	total_pendente = sum(v.total for v in vendas.filter(status="pendente"))
	return render(
		request,
		"admin_panel/cliente_detalhe.html",
		{
			"cliente": cliente,
			"vendas": vendas,
			"total_gasto": total_gasto,
			"total_pendente": total_pendente,
		},
	)


@staff_member_required(login_url="/admin/login/")
def lista_fiados(request):
	hoje = date.today()
	fiados = FiadoConta.objects.select_related("cliente").all()
	return render(
		request,
		"admin_panel/lista_fiados.html",
		{
			"fiados": fiados,
			"qtd_alerta": sum(1 for f in fiados if f.status in {"pendente", "parcial"} and 0 <= f.dias_para_vencer <= 3),
			"qtd_vencidos": sum(1 for f in fiados if f.status in {"pendente", "parcial"} and f.dias_para_vencer < 0),
			"hoje": hoje,
		},
	)


@staff_member_required(login_url="/admin/login/")
def fiado_form(request):
	if request.method == "POST":
		cliente = get_object_or_404(Cliente, pk=request.POST.get("cliente_id"))
		FiadoConta.objects.create(
			cliente=cliente,
			referencia=request.POST.get("referencia", "").strip(),
			valor_total=Decimal(request.POST.get("valor_total", "0") or "0"),
			valor_pago=Decimal(request.POST.get("valor_pago", "0") or "0"),
			vencimento=request.POST.get("vencimento"),
			status=request.POST.get("status", "pendente"),
			observacao=request.POST.get("observacao", "").strip(),
		)
		messages.success(request, "Conta fiado registrada.")
		return redirect("lista_fiados")
	return render(
		request,
		"admin_panel/fiado_form.html",
		{"clientes": Cliente.objects.all().order_by("nome"), "status_choices": FiadoConta.STATUS},
	)


@staff_member_required(login_url="/admin/login/")
def lista_contas_pagar(request):
	hoje = date.today()
	contas = ContaPagar.objects.all()

	status = request.GET.get("status", "").strip()
	pagamento_inicio = request.GET.get("pagamento_inicio", "").strip()
	pagamento_fim = request.GET.get("pagamento_fim", "").strip()

	if status:
		contas = contas.filter(status=status)

	if pagamento_inicio:
		try:
			data_inicio = date.fromisoformat(pagamento_inicio)
			contas = contas.filter(data_pagamento__gte=data_inicio)
		except ValueError:
			messages.error(request, "Data inicial de pagamento invalida.")

	if pagamento_fim:
		try:
			data_fim = date.fromisoformat(pagamento_fim)
			contas = contas.filter(data_pagamento__lte=data_fim)
		except ValueError:
			messages.error(request, "Data final de pagamento invalida.")

	total_pago_periodo = contas.aggregate(total=Sum("valor_pago"))["total"] or Decimal("0")
	qtd_pagamentos_periodo = contas.filter(data_pagamento__isnull=False).count()

	return render(
		request,
		"admin_panel/lista_contas_pagar.html",
		{
			"contas": contas,
			"qtd_alerta": sum(1 for c in contas if c.status in {"pendente", "parcial"} and 0 <= c.dias_para_vencer <= 3),
			"qtd_vencidos": sum(1 for c in contas if c.status in {"pendente", "parcial"} and c.dias_para_vencer < 0),
			"status_choices": ContaPagar.STATUS,
			"status": status,
			"pagamento_inicio": pagamento_inicio,
			"pagamento_fim": pagamento_fim,
			"total_pago_periodo": total_pago_periodo,
			"qtd_pagamentos_periodo": qtd_pagamentos_periodo,
			"hoje": hoje,
		},
	)


@staff_member_required(login_url="/admin/login/")
def conta_pagar_form(request):
	if request.method == "POST":
		fornecedor = request.POST.get("fornecedor", "").strip()
		referencia = request.POST.get("referencia", "").strip()
		try:
			valor_total = Decimal(request.POST.get("valor_total", "0") or "0")
			valor_pago = Decimal(request.POST.get("valor_pago", "0") or "0")
		except InvalidOperation:
			messages.error(request, "Valores invalidos para o boleto.")
			return redirect("conta_pagar_novo")
		vencimento = date.fromisoformat(request.POST.get("vencimento"))
		data_pagamento = request.POST.get("data_pagamento") or None
		observacao = request.POST.get("observacao", "").strip()

		try:
			parcelas = int(request.POST.get("parcelas", "1") or "1")
		except ValueError:
			parcelas = 1
		parcelas = max(1, parcelas)

		grupo = uuid4().hex[:12]
		for i in range(parcelas):
			vencimento_parcela = _add_months(vencimento, i)
			valor_pago_parcela = valor_pago if i == 0 else Decimal("0")
			status_parcela = _status_por_pagamento(valor_total, valor_pago_parcela)
			ContaPagar.objects.create(
				fornecedor=fornecedor,
				referencia=referencia,
				grupo_referencia=grupo,
				parcela_numero=i + 1,
				parcelas_total=parcelas,
				valor_total=valor_total,
				valor_pago=valor_pago_parcela,
				vencimento=vencimento_parcela,
				data_pagamento=data_pagamento if i == 0 else None,
				status=status_parcela,
				observacao=observacao,
			)

		messages.success(request, f"Conta a pagar registrada com {parcelas} parcela(s).")
		return redirect("lista_contas_pagar")
	return render(
		request,
		"admin_panel/conta_pagar_form.html",
		{"status_choices": ContaPagar.STATUS},
	)


@staff_member_required(login_url="/admin/login/")
def conta_pagar_adicionar_parcelas(request, pk):
	conta_base = get_object_or_404(ContaPagar, pk=pk)

	if request.method == "POST":
		try:
			quantidade = int(request.POST.get("quantidade", "1") or "1")
		except ValueError:
			quantidade = 1
		quantidade = max(1, quantidade)

		try:
			valor_parcela = Decimal(request.POST.get("valor_parcela", str(conta_base.valor_total)) or str(conta_base.valor_total))
		except InvalidOperation:
			messages.error(request, "Valor da parcela invalido.")
			return redirect("conta_pagar_adicionar_parcelas", pk=conta_base.pk)
		primeiro_vencimento = date.fromisoformat(request.POST.get("primeiro_vencimento"))
		observacao = request.POST.get("observacao", "").strip()

		grupo = conta_base.grupo_referencia or f"conta-{conta_base.id}"
		contas_grupo = ContaPagar.objects.filter(grupo_referencia=grupo).order_by("parcela_numero")
		if not contas_grupo.exists():
			conta_base.grupo_referencia = grupo
			conta_base.save(update_fields=["grupo_referencia"])
			contas_grupo = ContaPagar.objects.filter(pk=conta_base.pk)

		ultima = contas_grupo.order_by("-parcela_numero").first()
		max_parcela = ultima.parcela_numero if ultima else 0
		novo_total = contas_grupo.count() + quantidade

		for idx in range(quantidade):
			ContaPagar.objects.create(
				fornecedor=conta_base.fornecedor,
				referencia=conta_base.referencia,
				grupo_referencia=grupo,
				parcela_numero=max_parcela + idx + 1,
				parcelas_total=novo_total,
				valor_total=valor_parcela,
				valor_pago=Decimal("0"),
				vencimento=_add_months(primeiro_vencimento, idx),
				status="pendente",
				observacao=observacao,
			)

		ContaPagar.objects.filter(grupo_referencia=grupo).update(parcelas_total=novo_total)
		messages.success(request, f"Foram adicionadas {quantidade} parcela(s).")
		return redirect("lista_contas_pagar")

	return render(
		request,
		"admin_panel/conta_pagar_parcelas_form.html",
		{"conta": conta_base},
	)


@staff_member_required(login_url="/admin/login/")
def conta_pagar_atualizar_pagamento(request, pk):
	if request.method != "POST":
		return redirect("lista_contas_pagar")

	conta = get_object_or_404(ContaPagar, pk=pk)
	try:
		valor_pago = Decimal(request.POST.get("valor_pago", str(conta.valor_pago)) or str(conta.valor_pago))
	except InvalidOperation:
		messages.error(request, "Valor pago invalido.")
		return redirect("lista_contas_pagar")
	if valor_pago < 0:
		valor_pago = Decimal("0")

	conta.valor_pago = valor_pago
	conta.data_pagamento = request.POST.get("data_pagamento") or None
	conta.status = _status_por_pagamento(conta.valor_total, conta.valor_pago)
	conta.save(update_fields=["valor_pago", "data_pagamento", "status"])

	messages.success(request, f"Pagamento da parcela {conta.parcela_label} atualizado.")
	return redirect("lista_contas_pagar")
