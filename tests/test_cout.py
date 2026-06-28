from types import SimpleNamespace

from app.temps1.cout import cout_appel


def _usage(inp=0, out=0, cache_read=0, cache_write=0):
    return SimpleNamespace(
        input_tokens=inp, output_tokens=out,
        cache_read_input_tokens=cache_read, cache_creation_input_tokens=cache_write)


def test_cout_sonnet_input_et_output():
    # 1M input + 1M output sur Sonnet = (3 + 15) $ = 18 $ -> 16,56 € (×0,92)
    assert round(cout_appel("claude-sonnet-4-6", _usage(inp=1_000_000, out=1_000_000)), 2) == 16.56


def test_cout_opus_plus_cher():
    # 30 $ -> 27,60 €
    assert round(cout_appel("claude-opus-4-8", _usage(inp=1_000_000, out=1_000_000)), 2) == 27.60


def test_cache_lu_facture_un_dixieme():
    # 1M cache lu sur Sonnet = 0,30 $ -> 0,28 € (0,276 arrondi)
    assert round(cout_appel("claude-sonnet-4-6", _usage(cache_read=1_000_000)), 2) == 0.28


def test_modele_inconnu_cout_nul():
    assert cout_appel("modele-inexistant", _usage(inp=1_000_000)) == 0.0
