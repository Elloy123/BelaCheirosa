from django import forms

from .models import Categoria, Cliente, Produto


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            "nome",
            "cpf",
            "telefone",
            "email",
            "endereco",
            "bairro",
            "limite_credito",
            "situacao",
            "observacao",
        ]


class ProdutoForm(forms.ModelForm):
    categoria_pai = forms.ModelChoiceField(
        queryset=Categoria.objects.filter(parent__isnull=True).order_by("nome"),
        required=False,
        label="Categoria principal",
    )

    class Meta:
        model = Produto
        fields = [
            "categoria_pai",
            "categoria",
            "codigo",
            "nome",
            "descricao",
            "custo",
            "preco",
            "estoque",
            "estoque_minimo",
            "ativo",
            "imagem",
        ]
        labels = {
            "categoria": "Subcategoria",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = Categoria.objects.filter(parent__isnull=False).order_by("parent__nome", "nome")
        self.fields["categoria"].required = False

        for nome in [
            "categoria_pai",
            "categoria",
            "codigo",
            "nome",
            "descricao",
            "custo",
            "preco",
            "estoque",
            "estoque_minimo",
            "imagem",
        ]:
            self.fields[nome].widget.attrs.setdefault("class", "form-control")

        self.fields["categoria_pai"].widget.attrs["class"] = "form-select"
        self.fields["categoria"].widget.attrs["class"] = "form-select"
        self.fields["ativo"].widget.attrs.setdefault("class", "form-check-input")

        if self.instance and self.instance.pk and self.instance.categoria:
            if self.instance.categoria.parent_id:
                self.fields["categoria_pai"].initial = self.instance.categoria.parent
            else:
                self.fields["categoria_pai"].initial = self.instance.categoria

    def clean(self):
        cleaned_data = super().clean()
        categoria_pai = cleaned_data.get("categoria_pai")
        categoria = cleaned_data.get("categoria")

        if categoria and categoria_pai and categoria.parent_id != categoria_pai.id:
            self.add_error("categoria", "A subcategoria deve pertencer à categoria principal selecionada.")

        # Se subcategoria não for escolhida, usa a categoria principal.
        if not categoria and categoria_pai:
            cleaned_data["categoria"] = categoria_pai

        return cleaned_data
