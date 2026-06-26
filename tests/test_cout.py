from types import SimpleNamespace

from app.temps1.cout import cout_appel


def _usage(inp=0, out=0, cache_read=0, cache_write=0):
    return SimpleNamespace(
        input_tokens=inp, output_tokens=out,
        cache_read_input_tokens=cache_read, cache_creation_input_tokens=cache_write)


def test_cout_sonnet_input_et_output():
    # 1M input + 1M output sur Sonnet = 3 + 15 = 18 $
    assert cout_appel("claude-sonnet-4-6", _usage(inp=1_000_000, out=1_000_000)) == 18.0


def test_cout_opus_plus_cher():
    assert cout_appel("claude-opus-4-8", _usage(inp=1_000_000, out=1_000_000)) == 30.0


def test_cache_lu_facture_un_dixieme():
    # 1M cache lu sur Sonnet = 1M * 0,1 * 3/1M = 0,30 $
    assert round(cout_appel("claude-sonnet-4-6", _usage(cache_read=1_000_000)), 2) == 0.30


def test_modele_inconnu_cout_nul():
    assert cout_appel("modele-inexistant", _usage(inp=1_000_000)) == 0.0
