from django.conf import settings
from django.core.cache import cache

from .models import Categoria


def lista_categorias(request):
    cache_key = "loja:categorias_globais"
    categorias = cache.get(cache_key)
    if categorias is None:
        categorias = list(
            Categoria.objects.filter(parent__isnull=True)
            .prefetch_related("subcategorias")
            .order_by("nome")
        )
        cache.set(
            cache_key,
            categorias,
            getattr(settings, "CATEGORIAS_CACHE_TIMEOUT", 300),
        )

    return {
        "categorias_globais": categorias,
        "whatsapp_numero": settings.LOJA_WHATSAPP,
    }
