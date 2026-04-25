import io
import sqlite3
from decimal import Decimal, InvalidOperation
from datetime import date, timedelta
from uuid import uuid4
from urllib.parse import quote_plus

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models import (
	Case,
	CharField,
	Count,
	DecimalField,
	ExpressionWrapper,
	F,
	Q,
	Sum,
	Value,
	When,
)
from django.db.models.functions import Coalesce
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


PER_PAGE_OPTIONS = (12, 24, 50, 100)


def _paginas_visiveis(paginator, page_obj, vizinhos=2):
	"""Retorna lista de números de página e None para reticências."""
	current = page_obj.number
	num_pages = paginator.num_pages
	delta = vizinhos
	pages = set()
	pages.add(1)
	pages.add(num_pages)
	for i in range(max(1, current - delta), min(num_pages, current + delta) + 1):
		pages.add(i)
	result = []
	prev = None
	for p in sorted(pages):
		if prev is not None and p - prev > 1:
			result.append(None)
		result.append(p)
		prev = p
	return result

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


def _parse_decimal_input(value, fallback="0"):
	"""Converte string decimal aceitando virgula ou ponto."""
	text = str(value if value not in (None, "") else fallback).strip()
	return Decimal(text.replace(",", "."))


def _dividir_em_parcelas(valor_total, parcelas):
	parcelas = max(1, int(parcelas or 1))
	valor_base = (valor_total / Decimal(parcelas)).quantize(Decimal("0.01"))
	valores = [valor_base for _ in range(parcelas)]
	diferenca = valor_total - sum(valores)
	valores[-1] = (valores[-1] + diferenca).quantize(Decimal("0.01"))
	return valores


def _querystring_without_page(request):
	params = request.GET.copy()
	params.pop("page", None)
	return params.urlencode()


def _paginate(request, queryset, per_page):
	paginator = Paginator(queryset, per_page)
	return paginator.get_page(request.GET.get("page"))


def _parse_per_page(value, default=24):
	try:
		selected = int(value)
	except (ValueError, TypeError):
		selected = default
	if selected not in PER_PAGE_OPTIONS:
		selected = default
	return selected


def _sum_subtotal_itens(item_queryset):
	subtotal_expr = ExpressionWrapper(
		F("preco_unitario") * F("quantidade"),
		output_field=DecimalField(max_digits=14, decimal_places=2),
	)
	return item_queryset.aggregate(
		total=Coalesce(
			Sum(subtotal_expr),
			Value(Decimal("0.00")),
			output_field=DecimalField(max_digits=14, decimal_places=2),
		)
	)["total"]


def home(request):
	slug = request.GET.get("cat")
	filtro = request.GET.get("filtro", "padrao")
	busca = request.GET.get("q", "").strip()
	per_page = _parse_per_page(request.GET.get("por_pagina"), default=24)

	base_produtos = Produto.objects.filter(ativo=True).select_related("categoria", "categoria__parent")
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
	else:
		produtos = produtos.order_by("-criado_em", "nome")

	paginator = Paginator(produtos, per_page)
	page_number = request.GET.get("page", 1)
	page_obj = paginator.get_page(page_number)

	carrinho = Carrinho(request)
	return render(
		request,
		"loja/home.html",
		{
			"produtos": page_obj,
			"page_obj": page_obj,
			"paginator": paginator,
			"paginas_visiveis": _paginas_visiveis(paginator, page_obj),
			"per_page_options": PER_PAGE_OPTIONS,
			"per_page": per_page,
			"categoria_ativa": categoria_ativa,
			"categoria_pai_ativa": categoria_pai_ativa,
			"subcategorias_ativas": subcategorias_ativas,
			"filtro_ativo": filtro,
			"busca": busca,
			"querystring": _querystring_without_page(request),
			"carrinho_qtd": carrinho.count(),
		},
	)


def produto_detalhe(request, slug):
	produto = get_object_or_404(Produto, slug=slug, ativo=True)
	Produto.objects.filter(pk=produto.pk).update(visualizacoes=F("visualizacoes") + 1)
	produto.refresh_from_db(fields=["visualizacoes"])
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
			"formas": [(v, l) for v, l in Venda.FORMA_PAGAMENTO if v != "fiado"],
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
	if not nome_cliente:
		messages.error(request, "Por favor, informe seu nome para continuar.")
		return redirect("carrinho")

	tipo_entrega = request.POST.get("tipo_entrega", "retirada")
	endereco_cliente = request.POST.get("endereco_cliente", "").strip()
	if tipo_entrega == "entrega" and not endereco_cliente:
		messages.error(request, "Informe o endereço de entrega.")
		return redirect("carrinho")

	forma = request.POST.get("forma_pagamento", "dinheiro")
	observacao = request.POST.get("observacao", "").strip()

	total_final = sum(item["subtotal"] for item in itens)

	pedido = Pedido.objects.create(
		cliente_nome=nome_cliente,
		cliente_endereco=endereco_cliente,
		forma_pagamento=forma,
		desconto=Decimal("0.00"),
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

	tipo_label = "Entrega no endereço" if tipo_entrega == "entrega" else "Retirada na loja"

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
		f"*Total: R$ {total_final:.2f}*",
		"",
		"*Dados do cliente:*",
		f"Nome: {nome_cliente}",
		f"Tipo: {tipo_label}",
	])

	if tipo_entrega == "entrega":
		linhas.append(f"Endereço: {endereco_cliente}")

	linhas.append(f"Pagamento: {dict(Venda.FORMA_PAGAMENTO).get(forma, forma)}")

	if observacao:
		linhas.append(f"Observação: {observacao}")

	mensagem = quote_plus("\n".join(linhas))
	numero = settings.LOJA_WHATSAPP
	url = f"https://wa.me/{numero}?text={mensagem}"
	carrinho.clear()
	return redirect(url)


def _calcular_dashboard_completo(periodo, hoje):
	"""Retorna dict com dados do dashboard completo para um período."""
	periodos = {
		"7d": {"label": "Últimos 7 dias", "inicio": hoje - timedelta(days=6)},
		"30d": {"label": "Últimos 30 dias", "inicio": hoje - timedelta(days=29)},
		"mes": {"label": "Mês atual", "inicio": hoje.replace(day=1)},
	}
	if periodo not in periodos:
		periodo = "mes"
	periodo_info = periodos[periodo]
	data_inicio = periodo_info["inicio"]

	produtos_ativos = Produto.objects.filter(ativo=True)
	valor_venda_expr = ExpressionWrapper(
		F("preco") * F("estoque"), output_field=DecimalField(max_digits=14, decimal_places=2)
	)
	valor_custo_expr = ExpressionWrapper(
		F("custo") * F("estoque"), output_field=DecimalField(max_digits=14, decimal_places=2)
	)
	resumo_estoque = produtos_ativos.aggregate(
		total_venda=Coalesce(Sum(valor_venda_expr), Value(Decimal("0.00")), output_field=DecimalField(max_digits=14, decimal_places=2)),
		total_custo=Coalesce(Sum(valor_custo_expr), Value(Decimal("0.00")), output_field=DecimalField(max_digits=14, decimal_places=2)),
	)
	total_venda_estoque = resumo_estoque["total_venda"]
	total_custo_estoque = resumo_estoque["total_custo"]
	lucro_potencial_estoque = total_venda_estoque - total_custo_estoque
	margem_potencial_pct = (
		(lucro_potencial_estoque / total_custo_estoque) * Decimal("100")
		if total_custo_estoque > 0 else Decimal("0")
	)

	vendas_periodo = Venda.objects.filter(status="concluida", data__date__gte=data_inicio, data__date__lte=hoje)
	itens_periodo = ItemVenda.objects.filter(venda__in=vendas_periodo).select_related("produto")
	receita_expr = ExpressionWrapper(F("preco_unitario") * F("quantidade"), output_field=DecimalField(max_digits=14, decimal_places=2))
	custo_expr = ExpressionWrapper(F("produto__custo") * F("quantidade"), output_field=DecimalField(max_digits=14, decimal_places=2))

	resumo_vendas = itens_periodo.aggregate(
		receita=Coalesce(Sum(receita_expr), Value(Decimal("0.00")), output_field=DecimalField(max_digits=14, decimal_places=2)),
		custo=Coalesce(Sum(custo_expr), Value(Decimal("0.00")), output_field=DecimalField(max_digits=14, decimal_places=2)),
	)
	receita_vendas = resumo_vendas["receita"]
	custo_vendas = resumo_vendas["custo"]
	lucro_real = receita_vendas - custo_vendas
	taxa_lucro_real_pct = (
		(lucro_real / custo_vendas) * Decimal("100") if custo_vendas > 0 else Decimal("0")
	)

	mais_acessados = produtos_ativos.order_by("-visualizacoes", "-vendas", "nome")[:10]
	mais_comprados = (
		itens_periodo
		.values("produto__id", "produto__nome")
		.annotate(
			qtd_total=Coalesce(Sum("quantidade"), 0),
			receita=Coalesce(Sum(receita_expr), Value(Decimal("0.00")), output_field=DecimalField(max_digits=14, decimal_places=2)),
		)
		.order_by("-qtd_total", "produto__nome")[:10]
	)

	insights = []
	if total_custo_estoque > 0:
		insights.append(f"Margem potencial do estoque atual: {margem_potencial_pct:.2f}% sobre o custo.")
	if custo_vendas > 0:
		insights.append(f"Taxa de lucro real em {periodo_info['label'].lower()}: {taxa_lucro_real_pct:.2f}%.")
	else:
		insights.append(f"Não há vendas concluídas em {periodo_info['label'].lower()} para calcular lucro real.")
	if mais_acessados and mais_acessados[0].visualizacoes > 0:
		insights.append(f"Produto mais acessado: {mais_acessados[0].nome} com {mais_acessados[0].visualizacoes} visualizações.")
	if mais_comprados:
		insights.append(f"Produto mais comprado em {periodo_info['label'].lower()}: {mais_comprados[0]['produto__nome']} com {mais_comprados[0]['qtd_total']} unidades.")

	return {
		"total_venda_estoque": total_venda_estoque,
		"total_custo_estoque": total_custo_estoque,
		"lucro_potencial_estoque": lucro_potencial_estoque,
		"margem_potencial_pct": margem_potencial_pct,
		"receita_vendas": receita_vendas,
		"custo_vendas": custo_vendas,
		"lucro_real": lucro_real,
		"taxa_lucro_real_pct": taxa_lucro_real_pct,
		"mais_acessados": mais_acessados,
		"mais_comprados": mais_comprados,
		"insights": insights,
		"periodo": periodo,
		"periodo_label": periodo_info["label"],
	}


@staff_member_required(login_url="/admin/login/")
def dashboard(request):
	hoje = timezone.now().date()
	inicio_mes = hoje.replace(day=1)
	periodo = request.GET.get("periodo", "mes")

	vendas_hoje = Venda.objects.filter(data__date=hoje, status="concluida")
	vendas_mes = Venda.objects.filter(data__date__gte=inicio_mes, status="concluida")
	itens_hoje = ItemVenda.objects.filter(venda__in=vendas_hoje)
	itens_mes = ItemVenda.objects.filter(venda__in=vendas_mes).select_related("produto")

	faturamento_hoje_bruto = _sum_subtotal_itens(itens_hoje)
	faturamento_mes_bruto = _sum_subtotal_itens(itens_mes)

	desconto_hoje = vendas_hoje.aggregate(
		total=Coalesce(Sum("desconto"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=14, decimal_places=2))
	)["total"]
	desconto_mes = vendas_mes.aggregate(
		total=Coalesce(Sum("desconto"), Value(Decimal("0.00")), output_field=DecimalField(max_digits=14, decimal_places=2))
	)["total"]

	lucro_expr = ExpressionWrapper(
		(F("preco_unitario") - F("produto__custo")) * F("quantidade"),
		output_field=DecimalField(max_digits=14, decimal_places=2),
	)
	lucro_mes = itens_mes.aggregate(
		total=Coalesce(Sum(lucro_expr), Value(Decimal("0.00")), output_field=DecimalField(max_digits=14, decimal_places=2))
	)["total"]

	faturamento_hoje = faturamento_hoje_bruto - desconto_hoje
	faturamento_mes = faturamento_mes_bruto - desconto_mes

	baixo_estoque = Produto.objects.filter(ativo=True, estoque__lte=F("estoque_minimo"))
	ultimas_vendas = Venda.objects.select_related("cliente").prefetch_related("itens")[:10]

	vendas_por_forma_raw = (
		itens_mes.values("venda__forma_pagamento")
		.annotate(
			qtd=Count("venda_id", distinct=True),
			total=Coalesce(
				Sum(ExpressionWrapper(F("preco_unitario") * F("quantidade"), output_field=DecimalField(max_digits=14, decimal_places=2))),
				Value(Decimal("0.00")), output_field=DecimalField(max_digits=14, decimal_places=2),
			),
		)
		.order_by("-qtd")
	)
	vendas_por_forma = [{"forma_pagamento": r["venda__forma_pagamento"], "qtd": r["qtd"], "total": r["total"]} for r in vendas_por_forma_raw]

	fiados_alerta = FiadoConta.objects.filter(status__in=["pendente", "parcial"], vencimento__lte=hoje + timedelta(days=3))
	boletos_alerta = ContaPagar.objects.filter(status__in=["pendente", "parcial"], vencimento__lte=hoje + timedelta(days=3))
	pedidos_pendentes = Pedido.objects.filter(status="pendente").count()

	analise = _calcular_dashboard_completo(periodo, hoje)

	ctx = {
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
	}
	ctx.update(analise)
	return render(request, "admin_panel/dashboard.html", ctx)


@staff_member_required(login_url="/admin/login/")
def dashboard_completo(request):
	hoje = timezone.now().date()
	periodo = request.GET.get("periodo", "mes")
	ctx = _calcular_dashboard_completo(periodo, hoje)
	return render(request, "admin_panel/dashboard_completo.html", ctx)


@staff_member_required(login_url="/admin/login/")
def lista_pedidos(request):
	status = request.GET.get("status", "pendente")
	pedidos = Pedido.objects.prefetch_related("itens__produto")
	if status:
		pedidos = pedidos.filter(status=status)
	page_obj = _paginate(request, pedidos, per_page=50)
	return render(
		request,
		"admin_panel/lista_pedidos.html",
		{
			"pedidos": page_obj.object_list,
			"page_obj": page_obj,
			"querystring": _querystring_without_page(request),
			"status": status,
			"status_choices": Pedido.STATUS,
		},
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

	vendas = Venda.objects.select_related("cliente").order_by("-data")
	if q:
		vendas = vendas.filter(Q(cliente__nome__icontains=q) | Q(id__icontains=q))
	if status:
		vendas = vendas.filter(status=status)
	if forma:
		vendas = vendas.filter(forma_pagamento=forma)

	itens_filtrados = ItemVenda.objects.filter(venda__in=vendas)
	total_bruto = _sum_subtotal_itens(itens_filtrados)
	total_desconto = vendas.aggregate(
		total=Coalesce(
			Sum("desconto"),
			Value(Decimal("0.00")),
			output_field=DecimalField(max_digits=14, decimal_places=2),
		)
	)["total"]
	total_filtrado = total_bruto - total_desconto

	vendas = vendas.prefetch_related("itens")
	page_obj = _paginate(request, vendas, per_page=35)
	return render(
		request,
		"admin_panel/lista_vendas.html",
		{
			"vendas": page_obj.object_list,
			"page_obj": page_obj,
			"querystring": _querystring_without_page(request),
			"total_filtrado": total_filtrado,
			"status_choices": Venda.STATUS,
			"forma_choices": Venda.FORMA_PAGAMENTO,
			"q": q,
			"status": status,
			"forma": forma,
			# PDV inline
			"produtos": Produto.objects.filter(ativo=True).order_by("nome"),
			"clientes": Cliente.objects.order_by("nome"),
			"formas_pagamento": Venda.FORMA_PAGAMENTO,
			"aba_pdv": request.GET.get("pdv") == "1",
			"hoje_iso": date.today().isoformat(),
		},
	)


@staff_member_required(login_url="/admin/login/")
def venda_nova(request):
	produtos = Produto.objects.filter(ativo=True).order_by("nome")
	clientes = Cliente.objects.order_by("nome")

	def _redirect_form(origem_pdv=False):
		if origem_pdv:
			return redirect("/painel/vendas/?pdv=1")
		return redirect("venda_nova")

	if request.method == "POST":
		origem_pdv = request.POST.get("origem_fluxo") == "pdv"
		forma_pagamento = request.POST.get("forma_pagamento", "dinheiro")
		formas_validas = {valor for valor, _ in Venda.FORMA_PAGAMENTO}
		if forma_pagamento not in formas_validas:
			messages.error(request, "Forma de pagamento inválida.")
			return _redirect_form(origem_pdv)

		try:
			desconto = _parse_decimal_input(request.POST.get("desconto", "0"), "0")
		except InvalidOperation:
			messages.error(request, "Desconto inválido.")
			return _redirect_form(origem_pdv)

		cliente = None
		cliente_id = request.POST.get("cliente_id", "").strip()
		if cliente_id:
			cliente = Cliente.objects.filter(pk=cliente_id).first()

		parcelas_fiado = 1
		primeiro_vencimento_fiado = None
		if forma_pagamento == "fiado":
			if not cliente:
				messages.error(request, "Para venda fiado, selecione um cliente.")
				return _redirect_form(origem_pdv)
			try:
				parcelas_fiado = int(request.POST.get("fiado_parcelas", "1") or "1")
			except ValueError:
				parcelas_fiado = 1
			parcelas_fiado = max(1, parcelas_fiado)
			try:
				primeiro_vencimento_fiado = date.fromisoformat(request.POST.get("fiado_primeiro_vencimento", ""))
			except ValueError:
				messages.error(request, "Informe a data do primeiro pagamento do fiado.")
				return _redirect_form(origem_pdv)

		itens_solicitados = []
		for key, value in request.POST.items():
			if not key.startswith("qtd_"):
				continue
			try:
				produto_id = int(key.split("_", 1)[1])
				qtd = int(value or "0")
			except (ValueError, TypeError):
				continue
			if qtd > 0:
				itens_solicitados.append((produto_id, qtd))

		if not itens_solicitados:
			messages.error(request, "Informe ao menos um item com quantidade maior que zero.")
			return _redirect_form(origem_pdv)

		produtos_map = {
			p.id: p for p in Produto.objects.filter(id__in=[pid for pid, _ in itens_solicitados], ativo=True)
		}

		for produto_id, qtd in itens_solicitados:
			produto = produtos_map.get(produto_id)
			if not produto:
				messages.error(request, "Um dos produtos selecionados não está disponível.")
				return _redirect_form(origem_pdv)
			if qtd > produto.estoque:
				messages.error(request, f"Estoque insuficiente para {produto.nome}. Disponível: {produto.estoque}.")
				return _redirect_form(origem_pdv)

		status_venda = "pendente" if forma_pagamento == "fiado" else "concluida"

		with transaction.atomic():
			venda = Venda.objects.create(
				cliente=cliente,
				forma_pagamento=forma_pagamento,
				status=status_venda,
				desconto=desconto,
				observacao=request.POST.get("observacao", "").strip(),
			)

			for produto_id, qtd in itens_solicitados:
				produto = produtos_map[produto_id]
				ItemVenda.objects.create(
					venda=venda,
					produto=produto,
					quantidade=qtd,
					preco_unitario=produto.preco,
				)
				produto.vendas += qtd
				produto.save(update_fields=["vendas"])
				MovimentacaoEstoque.objects.create(
					produto=produto,
					tipo="saida",
					quantidade=qtd,
					observacao=f"Baixa manual venda #{venda.id}",
					responsavel=request.user.username,
				)

			if forma_pagamento == "fiado":
				grupo = uuid4().hex[:12]
				valores_parcelas = _dividir_em_parcelas(venda.total, parcelas_fiado)
				for idx, valor_parcela in enumerate(valores_parcelas):
					FiadoConta.objects.create(
						cliente=cliente,
						referencia=f"Venda #{venda.id} - Parcela {idx + 1}/{parcelas_fiado}",
						valor_total=valor_parcela,
						valor_pago=Decimal("0.00"),
						vencimento=_add_months(primeiro_vencimento_fiado, idx),
						status="pendente",
						observacao=request.POST.get("observacao", "").strip(),
						grupo_referencia=grupo,
						parcela_numero=idx + 1,
						parcelas_total=parcelas_fiado,
					)

		messages.success(request, f"Venda #{venda.id} criada com sucesso.")
		if forma_pagamento == "fiado":
			messages.info(request, "Parcelas de fiado geradas automaticamente no Controle de Fiado.")
			return redirect("lista_fiados")
		return redirect("venda_detalhe", pk=venda.pk)

	return render(
		request,
		"admin_panel/venda_form.html",
		{
			"produtos": produtos,
			"clientes": clientes,
			"formas_pagamento": Venda.FORMA_PAGAMENTO,
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

	valor_estoque_expr = ExpressionWrapper(
		F("custo") * F("estoque"),
		output_field=DecimalField(max_digits=14, decimal_places=2),
	)
	produtos = Produto.objects.filter(ativo=True).select_related("categoria").annotate(
		situacao_calc=Case(
			When(estoque=0, then=Value("Zerado")),
			When(estoque__lte=F("estoque_minimo"), then=Value("Baixo")),
			default=Value("OK"),
			output_field=CharField(),
		),
		valor_estoque=valor_estoque_expr,
	)
	if q:
		produtos = produtos.filter(Q(nome__icontains=q) | Q(codigo__icontains=q))
	if situacao:
		produtos = produtos.filter(situacao_calc=situacao)

	resumo = produtos.aggregate(
		total_valor=Coalesce(
			Sum("valor_estoque"),
			Value(Decimal("0.00")),
			output_field=DecimalField(max_digits=14, decimal_places=2),
		),
		qtd_baixo=Count("id", filter=Q(situacao_calc="Baixo")),
		qtd_zerado=Count("id", filter=Q(situacao_calc="Zerado")),
	)
	page_obj = _paginate(request, produtos.order_by("nome"), per_page=40)

	return render(
		request,
		"admin_panel/lista_estoque.html",
		{
			"resultado": page_obj.object_list,
			"page_obj": page_obj,
			"querystring": _querystring_without_page(request),
			"q": q,
			"situacao": situacao,
			"qtd_baixo": resumo["qtd_baixo"],
			"qtd_zerado": resumo["qtd_zerado"],
			"total_valor": resumo["total_valor"],
		},
	)


@staff_member_required(login_url="/admin/login/")
def lista_produtos(request):
	q = request.GET.get("q", "").strip()
	cat = request.GET.get("cat", "").strip()
	per_page = _parse_per_page(request.GET.get("por_pagina"), default=24)

	produtos = Produto.objects.select_related("categoria", "categoria__parent").order_by("nome")
	if q:
		produtos = produtos.filter(Q(nome__icontains=q) | Q(codigo__icontains=q))
	if cat:
		produtos = produtos.filter(
			Q(categoria__slug=cat) | Q(categoria__parent__slug=cat)
		)
	paginator = Paginator(produtos, per_page)
	page_number = request.GET.get("page", 1)
	page_obj = paginator.get_page(page_number)

	return render(
		request,
		"admin_panel/lista_produtos.html",
		{
			"produtos": page_obj,
			"page_obj": page_obj,
			"paginator": paginator,
			"paginas_visiveis": _paginas_visiveis(paginator, page_obj),
			"per_page_options": PER_PAGE_OPTIONS,
			"per_page": per_page,
			"querystring": _querystring_without_page(request),
			"q": q,
			"cat": cat,
			"categorias_pai": Categoria.objects.filter(parent__isnull=True).prefetch_related("subcategorias").order_by("nome"),
		},
	)


@staff_member_required(login_url="/admin/login/")
def categoria_excluir(request, pk):
	if request.method != "POST":
		return redirect("lista_produtos")

	categoria = get_object_or_404(Categoria, pk=pk)
	if categoria.subcategorias.exists():
		messages.error(request, "Remova primeiro as subcategorias dessa categoria.")
		return redirect("lista_produtos")

	if Produto.objects.filter(categoria=categoria).exists():
		messages.error(request, "Existem produtos vinculados a esta categoria. Realoque antes de excluir.")
		return redirect("lista_produtos")

	nome = categoria.nome
	try:
		categoria.delete()
	except ProtectedError:
		messages.error(request, "Categoria não pode ser excluída porque possui vínculo com outros registros.")
		return redirect("lista_produtos")

	messages.success(request, f"Categoria '{nome}' excluída com sucesso.")
	return redirect("lista_produtos")


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

	try:
		Categoria.objects.create(nome=nome, slug=_gerar_slug_categoria(nome))
	except IntegrityError:
		messages.error(request, "Nao foi possivel criar a categoria. Verifique se ela ja existe.")
		return redirect(next_url)

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

	try:
		Categoria.objects.create(nome=nome, slug=_gerar_slug_categoria(nome), parent=pai)
	except IntegrityError:
		messages.error(request, "Nao foi possivel criar a subcategoria. Verifique os dados informados.")
		return redirect(next_url)

	messages.success(request, "Subcategoria criada com sucesso.")
	return redirect(next_url)


@staff_member_required(login_url="/admin/login/")
def movimentar_estoque(request, pk):
	produto = get_object_or_404(Produto, pk=pk)
	historico = produto.movimentacoes.all()[:20]

	if request.method == "POST":
		tipo = request.POST.get("tipo")
		try:
			quantidade = int(request.POST.get("quantidade", "0") or "0")
		except ValueError:
			messages.error(request, "Quantidade invalida.")
			return redirect("movimentar_estoque", pk=produto.pk)
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
	from django.urls import reverse
	
	cliente = get_object_or_404(Cliente, pk=pk) if pk else None
	next_page = request.GET.get("next", "").strip()

	if request.method == "POST":
		form = ClienteForm(request.POST, instance=cliente)
		if form.is_valid():
			novo_cliente = form.save()
			messages.success(request, "Cliente salvo com sucesso.")
			
			# Redireciona para PDV com cliente pré-selecionado
			if next_page == "pdv":
				return redirect(reverse("lista_vendas") + f"?pdv=1&cliente_id={novo_cliente.id}")
			# Redireciona para fiado com cliente pré-selecionado
			elif next_page == "fiado":
				return redirect(reverse("fiado_novo") + f"?cliente_id={novo_cliente.id}")
			
			return redirect("lista_clientes")
	else:
		form = ClienteForm(instance=cliente)

	return render(
		request,
		"admin_panel/cliente_form.html",
		{"form": form, "cliente": cliente, "next": next_page}
	)


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
	fiados = FiadoConta.objects.select_related("cliente").order_by("cliente__nome", "vencimento", "id")

	grupos_clientes = []
	grupo_atual = None
	for item in fiados:
		if not grupo_atual or grupo_atual["cliente"].id != item.cliente.id:
			grupo_atual = {
				"cliente": item.cliente,
				"itens": [],
				"total_geral": Decimal("0.00"),
				"total_aberto": Decimal("0.00"),
				"qtd_vencidos": 0,
				"qtd_alerta": 0,
			}
			grupos_clientes.append(grupo_atual)

		grupo_atual["itens"].append(item)
		grupo_atual["total_geral"] += item.valor_total
		if item.status in {"pendente", "parcial"}:
			grupo_atual["total_aberto"] += item.falta_pagar
			if item.dias_para_vencer < 0:
				grupo_atual["qtd_vencidos"] += 1
			elif item.dias_para_vencer <= 3:
				grupo_atual["qtd_alerta"] += 1

	return render(
		request,
		"admin_panel/lista_fiados.html",
		{
			"grupos_clientes": grupos_clientes,
			"qtd_alerta": sum(1 for f in fiados if f.status in {"pendente", "parcial"} and 0 <= f.dias_para_vencer <= 3),
			"qtd_vencidos": sum(1 for f in fiados if f.status in {"pendente", "parcial"} and f.dias_para_vencer < 0),
			"hoje": hoje,
		},
	)


@staff_member_required(login_url="/admin/login/")
def fiado_form(request):
	cliente_id_pre = request.GET.get("cliente_id", "").strip()
	
	if request.method == "POST":
		cliente_id = request.POST.get("cliente_id")
		if not cliente_id:
			messages.error(request, "Selecione um cliente.")
			return redirect("fiado_novo")

		try:
			cliente = get_object_or_404(Cliente, pk=cliente_id)
			valor_total = _parse_decimal_input(request.POST.get("valor_total", "0"), "0")
			vencimento = date.fromisoformat(request.POST.get("vencimento", ""))
			parcelas = int(request.POST.get("parcelas", "1") or "1")
		except (InvalidOperation, ValueError):
			messages.error(request, "Dados invalidos no cadastro de fiado. Revise valores, parcelas e vencimento.")
			return redirect("fiado_novo")

		parcelas = max(1, parcelas)
		grupo = uuid4().hex[:12]
		valores_parcelas = _dividir_em_parcelas(valor_total, parcelas)
		referencia = request.POST.get("referencia", "").strip() or "Lançamento manual"
		observacao = request.POST.get("observacao", "").strip()

		for idx, valor_parcela in enumerate(valores_parcelas):
			FiadoConta.objects.create(
				cliente=cliente,
				referencia=f"{referencia} - Parcela {idx + 1}/{parcelas}",
				valor_total=valor_parcela,
				valor_pago=Decimal("0.00"),
				vencimento=_add_months(vencimento, idx),
				status="pendente",
				observacao=observacao,
				grupo_referencia=grupo,
				parcela_numero=idx + 1,
				parcelas_total=parcelas,
			)
		messages.success(request, f"Conta fiado registrada com {parcelas} parcela(s).")
		return redirect("lista_fiados")
	return render(
		request,
		"admin_panel/fiado_form.html",
		{
			"clientes": Cliente.objects.all().order_by("nome"),
			"cliente_id_pre": cliente_id_pre,
		},
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
			valor_total = _parse_decimal_input(request.POST.get("valor_total", "0"), "0")
			valor_pago = _parse_decimal_input(request.POST.get("valor_pago", "0"), "0")
		except InvalidOperation:
			messages.error(request, "Valores invalidos para o boleto.")
			return redirect("conta_pagar_novo")
		try:
			vencimento = date.fromisoformat(request.POST.get("vencimento", ""))
		except ValueError:
			messages.error(request, "Data de vencimento invalida.")
			return redirect("conta_pagar_novo")
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


@staff_member_required(login_url="/admin/login/")
def backup_banco(request):
	"""Gera e faz download de um backup do banco de dados SQLite."""
	db_path = settings.DATABASES["default"]["NAME"]
	buffer = io.BytesIO()
	conn = sqlite3.connect(str(db_path))
	try:
		for linha in conn.iterdump():
			buffer.write((linha + "\n").encode("utf-8"))
	finally:
		conn.close()
	buffer.seek(0)
	nome_arquivo = f"backup_belacheirosa_{timezone.now().strftime('%Y%m%d_%H%M%S')}.sql"
	response = HttpResponse(buffer, content_type="application/octet-stream")
	response["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
	return response
