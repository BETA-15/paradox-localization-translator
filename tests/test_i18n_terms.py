"""訳語表（app/i18n/terms.py）がそろっていること。"""
from i18n import terms


def test_every_term_has_all_eleven_languages_and_a_source():
    for term_id, entry in terms.TERMS.items():
        assert set(entry) == set(terms.LANGS), term_id
        assert all(isinstance(v, str) and v.strip() for v in entry.values()), term_id
        assert term_id in terms.SOURCES


def test_term_lookup_falls_back_to_english():
    assert terms.term("glossary", "japanese") == "用語集"
    assert terms.term("glossary", "klingon") == "Glossary"
