from datetime import date

from django.db import models
from django.utils import timezone


class Categoria(models.Model):
	nome = models.CharField(max_length=120)
	slug = models.SlugField(max_length=140, unique=True)
	parent = models.ForeignKey(
		"self",
		on_delete=models.CASCADE,
		related_name="subcategorias",
		null=True,
		blank=True,
	)

	class Meta:
		ordering = ["parent__nome", "nome"]
		verbose_name = "Categoria"
		verbose_name_plural = "Categorias"
		constraints = [
			models.UniqueConstraint(
				models.functions.Lower("nome"),
				name="uniq_categoria_raiz_nome",
				condition=models.Q(parent__isnull=True),
			),
			models.UniqueConstraint(
				models.functions.Lower("nome"),
				"parent",
				name="uniq_subcategoria_nome_por_pai",
				condition=models.Q(parent__isnull=False),
			),
		]

	def __str__(self):
		if self.parent:
			return f"{self.parent.nome} > {self.nome}"
		return self.nome


class Produto(models.Model):
	categoria = models.ForeignKey(
		Categoria,
		on_delete=models.PROTECT,
		related_name="produtos",
		null=True,
		blank=True,
	)
	codigo = models.CharField(max_length=60, blank=True, default="")
	nome = models.CharField(max_length=200)
	slug = models.SlugField(max_length=220, unique=True)
	descricao = models.TextField(blank=True)
	custo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	preco = models.DecimalField(max_digits=10, decimal_places=2)
	estoque = models.PositiveIntegerField(default=0)
	estoque_minimo = models.PositiveIntegerField(default=5)
	ativo = models.BooleanField(default=True)
	vendas = models.PositiveIntegerField(default=0)
	imagem = models.ImageField(upload_to="produtos/", blank=True, null=True)
	criado_em = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["nome"]
		verbose_name = "Produto"
		verbose_name_plural = "Produtos"

	def __str__(self):
		return self.nome

	@property
	def estoque_baixo(self):
		return self.estoque <= self.estoque_minimo


class Cliente(models.Model):
	SITUACAO_CHOICES = [
		("Regular", "Regular"),
		("Inadimplente", "Inadimplente"),
		("VIP", "VIP"),
		("Bloqueado", "Bloqueado"),
	]

	nome = models.CharField(max_length=200)
	cpf = models.CharField(max_length=14, blank=True, null=True, unique=True)
	telefone = models.CharField(max_length=20, blank=True)
	email = models.EmailField(blank=True)
	endereco = models.CharField(max_length=300, blank=True)
	bairro = models.CharField(max_length=100, blank=True)
	limite_credito = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	situacao = models.CharField(max_length=20, choices=SITUACAO_CHOICES, default="Regular")
	observacao = models.TextField(blank=True)
	criado_em = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["nome"]

	def __str__(self):
		return self.nome

	@property
	def total_em_aberto(self):
		return sum(
			v.total for v in self.vendas.filter(forma_pagamento="fiado", status="pendente")
		)


class Venda(models.Model):
	FORMA_PAGAMENTO = [
		("dinheiro", "Dinheiro"),
		("pix", "PIX"),
		("cartao_debito", "Cartão Débito"),
		("cartao_credito", "Cartão Crédito"),
		("fiado", "Fiado"),
	]
	STATUS = [
		("concluida", "Concluída"),
		("pendente", "Pendente"),
		("cancelada", "Cancelada"),
	]

	cliente = models.ForeignKey(
		Cliente,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="vendas",
	)
	data = models.DateTimeField(default=timezone.now)
	forma_pagamento = models.CharField(max_length=20, choices=FORMA_PAGAMENTO, default="dinheiro")
	status = models.CharField(max_length=15, choices=STATUS, default="concluida")
	desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	observacao = models.TextField(blank=True)
	criado_em = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-data"]

	def __str__(self):
		nome = self.cliente.nome if self.cliente else "Consumidor Final"
		return f"Venda #{self.pk:05d} - {nome}"

	@property
	def subtotal(self):
		return sum(item.subtotal for item in self.itens.all())

	@property
	def total(self):
		return self.subtotal - self.desconto


class ItemVenda(models.Model):
	venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name="itens")
	produto = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="itens_venda")
	quantidade = models.PositiveIntegerField(default=1)
	preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)

	class Meta:
		verbose_name = "Item da venda"
		verbose_name_plural = "Itens da venda"

	def __str__(self):
		return f"{self.produto.nome} x{self.quantidade}"

	@property
	def subtotal(self):
		return self.preco_unitario * self.quantidade


class MovimentacaoEstoque(models.Model):
	TIPO_CHOICES = [
		("entrada", "Entrada"),
		("saida", "Saída"),
		("ajuste", "Ajuste"),
	]

	produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="movimentacoes")
	tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
	quantidade = models.IntegerField()
	observacao = models.CharField(max_length=300, blank=True)
	responsavel = models.CharField(max_length=150, blank=True)
	data = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-data"]

	def __str__(self):
		return f"{self.get_tipo_display()} | {self.produto.nome} | {self.quantidade}"

	def save(self, *args, **kwargs):
		produto = self.produto
		if self.tipo == "entrada":
			produto.estoque += self.quantidade
		elif self.tipo == "saida":
			produto.estoque = max(0, produto.estoque - self.quantidade)
		elif self.tipo == "ajuste":
			produto.estoque = max(0, self.quantidade)
		produto.save(update_fields=["estoque"])
		super().save(*args, **kwargs)


class Pedido(models.Model):
	STATUS = [
		("pendente", "Pendente"),
		("concluido", "Concluído"),
		("cancelado", "Cancelado"),
	]
	FORMA_PAGAMENTO = Venda.FORMA_PAGAMENTO

	cliente_nome = models.CharField(max_length=200, blank=True)
	cliente_endereco = models.CharField(max_length=300, blank=True)
	forma_pagamento = models.CharField(max_length=20, choices=FORMA_PAGAMENTO, default="dinheiro")
	observacao = models.TextField(blank=True)
	desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	status = models.CharField(max_length=15, choices=STATUS, default="pendente")
	criado_em = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-criado_em"]

	@property
	def subtotal(self):
		return sum(item.subtotal for item in self.itens.all())

	@property
	def total(self):
		return self.subtotal - self.desconto


class ItemPedido(models.Model):
	pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens")
	produto = models.ForeignKey(Produto, on_delete=models.PROTECT)
	quantidade = models.PositiveIntegerField(default=1)
	preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)

	@property
	def subtotal(self):
		return self.preco_unitario * self.quantidade


class FiadoConta(models.Model):
	STATUS = [
		("pendente", "Pendente"),
		("pago", "Pago"),
		("parcial", "Parcial"),
	]

	cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="fiados")
	referencia = models.CharField(max_length=200)
	valor_total = models.DecimalField(max_digits=10, decimal_places=2)
	valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	vencimento = models.DateField()
	status = models.CharField(max_length=10, choices=STATUS, default="pendente")
	observacao = models.CharField(max_length=300, blank=True)
	criado_em = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["vencimento", "-id"]

	@property
	def falta_pagar(self):
		faltante = self.valor_total - self.valor_pago
		return faltante if faltante > 0 else 0

	@property
	def dias_para_vencer(self):
		return (self.vencimento - date.today()).days


class ContaPagar(models.Model):
	STATUS = [
		("pendente", "Pendente"),
		("pago", "Pago"),
		("parcial", "Parcial"),
	]

	fornecedor = models.CharField(max_length=200)
	referencia = models.CharField(max_length=220)
	grupo_referencia = models.CharField(max_length=40, blank=True, default="")
	parcela_numero = models.PositiveIntegerField(default=1)
	parcelas_total = models.PositiveIntegerField(default=1)
	valor_total = models.DecimalField(max_digits=10, decimal_places=2)
	valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	vencimento = models.DateField()
	data_pagamento = models.DateField(null=True, blank=True)
	status = models.CharField(max_length=10, choices=STATUS, default="pendente")
	observacao = models.CharField(max_length=300, blank=True)
	criado_em = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["vencimento", "grupo_referencia", "parcela_numero", "-id"]

	@property
	def falta_pagar(self):
		faltante = self.valor_total - self.valor_pago
		return faltante if faltante > 0 else 0

	@property
	def dias_para_vencer(self):
		return (self.vencimento - date.today()).days

	@property
	def parcela_label(self):
		return f"{self.parcela_numero}/{self.parcelas_total}"
