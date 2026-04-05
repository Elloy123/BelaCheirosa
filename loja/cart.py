from decimal import Decimal


class Carrinho:
    SESSION_KEY = "carrinho"

    def __init__(self, request):
        self.session = request.session
        self.data = self.session.get(self.SESSION_KEY, {})

    def save(self):
        self.session[self.SESSION_KEY] = self.data
        self.session.modified = True

    def add(self, produto, qtd=1, override=False):
        pid = str(produto.id)
        if pid not in self.data:
            self.data[pid] = {
                "produto_id": produto.id,
                "nome": produto.nome,
                "preco": str(produto.preco),
                "qtd": 0,
            }
        if override:
            self.data[pid]["qtd"] = max(0, int(qtd))
        else:
            self.data[pid]["qtd"] += int(qtd)
        if self.data[pid]["qtd"] <= 0:
            self.data.pop(pid, None)
        self.save()

    def remove(self, produto_id):
        self.data.pop(str(produto_id), None)
        self.save()

    def clear(self):
        self.data = {}
        self.save()

    def __iter__(self):
        for item in self.data.values():
            preco = Decimal(item["preco"])
            qtd = int(item["qtd"])
            yield {
                **item,
                "preco": preco,
                "qtd": qtd,
                "subtotal": preco * qtd,
            }

    def count(self):
        return sum(int(item["qtd"]) for item in self.data.values())

    def total(self):
        return sum((Decimal(item["preco"]) * int(item["qtd"])) for item in self.data.values())
