from django.conf import settings

from .models import Categoria


def lista_categorias(request):
    return {
        "categorias_globais": Categoria.objects.filter(parent__isnull=True).prefetch_related("subcategorias"),
        "whatsapp_numero": settings.LOJA_WHATSAPP,
    }
