"""訳語表（第3段 5 章）。アプリ独自の言葉とゲームの言葉を、11言語でそろえるための表。

段階1・段階2で画面の文字列を訳すときは、この表の訳を使う。SOURCES に出典を書く：
- "official:<ゲーム> <ファイル>"：この Mac に入っているゲームの公式の訳から取った。
- "chosen"：公式の訳が見つからなかったので決めた（著者に見せて確かめる）。
"""

LANGS = ("english", "french", "german", "spanish", "japanese", "korean", "polish", "braz_por", "russian",
         "simp_chinese", "turkish")

TERMS = {
    # ---- ゲームの言葉
    "mod": {"english": "mod", "french": "mod", "german": "Mod", "spanish": "mod", "japanese": "Mod",
            "korean": "모드", "polish": "mod", "braz_por": "mod", "russian": "мод", "simp_chinese": "模组",
            "turkish": "mod"},
    "playset": {"english": "playset", "french": "ensemble prédéfini", "german": "Playset", "spanish": "set de juego",
                "japanese": "プレイセット", "korean": "Playset", "polish": "zestaw modyfikacji", "braz_por": "playset",
                "russian": "игровой набор", "simp_chinese": "播放集", "turkish": "playset"},
    "load_order": {"english": "load order", "french": "ordre de chargement", "german": "Ladereihenfolge",
                   "spanish": "orden de carga", "japanese": "ロード順", "korean": "로드 순서", "polish": "kolejność wczytywania",
                   "braz_por": "ordem de carregamento", "russian": "порядок загрузки", "simp_chinese": "加载顺序",
                   "turkish": "yükleme sırası"},
    "localization": {"english": "localization", "french": "localisation", "german": "Lokalisierung",
                     "spanish": "localización", "japanese": "ローカライズ", "korean": "현지화", "polish": "lokalizacja",
                     "braz_por": "localização", "russian": "локализация", "simp_chinese": "本地化", "turkish": "yerelleştirme"},
    "steam_workshop": {lang: "Steam Workshop" for lang in LANGS},
    # ---- アプリ独自の言葉
    "translation_mod": {"english": "translation mod", "french": "mod de traduction", "german": "Übersetzungsmod",
                        "spanish": "mod de traducción", "japanese": "日本語化Mod", "korean": "번역 모드",
                        "polish": "mod tłumaczący", "braz_por": "mod de tradução", "russian": "мод перевода",
                        "simp_chinese": "翻译模组", "turkish": "çeviri modu"},
    "source_mod": {"english": "source mod", "french": "mod d’origine", "german": "Ursprungsmod", "spanish": "mod original",
                   "japanese": "元Mod", "korean": "원본 모드", "polish": "mod źródłowy", "braz_por": "mod original",
                   "russian": "исходный мод", "simp_chinese": "原模组", "turkish": "kaynak mod"},
    "chinese_basis_translation": {"english": "Chinese-based translation", "french": "traduction basée sur le chinois",
                                  "german": "Übersetzung auf chinesischer Basis", "spanish": "traducción basada en el chino",
                                  "japanese": "中国語基準翻訳", "korean": "중국어 기준 번역",
                                  "polish": "tłumaczenie oparte na chińskim", "braz_por": "tradução baseada no chinês",
                                  "russian": "перевод на основе китайского", "simp_chinese": "以中文为基准的翻译",
                                  "turkish": "Çince tabanlı çeviri"},
    "untranslated_monitor": {"english": "Untranslated monitor", "french": "Surveillance des non-traduits",
                             "german": "Überwachung unübersetzter Texte", "spanish": "Monitor de textos sin traducir",
                             "japanese": "未翻訳監視", "korean": "미번역 감시", "polish": "Monitor nieprzetłumaczonych",
                             "braz_por": "Monitor de não traduzidos", "russian": "Мониторинг непереведённого",
                             "simp_chinese": "未翻译监视", "turkish": "Çevrilmemiş metin izleme"},
    "translation_status": {"english": "Translation status", "french": "État de la traduction",
                           "german": "Übersetzungsstatus", "spanish": "Estado de la traducción", "japanese": "翻訳状況",
                           "korean": "번역 현황", "polish": "Stan tłumaczenia", "braz_por": "Situação da tradução",
                           "russian": "Состояние перевода", "simp_chinese": "翻译状况", "turkish": "Çeviri durumu"},
    "full_diagnostics": {"english": "Full diagnostics", "french": "Diagnostic complet", "german": "Gesamtdiagnose",
                         "spanish": "Diagnóstico completo", "japanese": "総合診断", "korean": "종합 진단",
                         "polish": "Pełna diagnostyka", "braz_por": "Diagnóstico completo", "russian": "Полная диагностика",
                         "simp_chinese": "综合诊断", "turkish": "Kapsamlı tanılama"},
    "differential_fill": {"english": "gap filling", "french": "complément des écarts", "german": "Lückenergänzung",
                          "spanish": "relleno de huecos", "japanese": "差分補完", "korean": "누락분 보완",
                          "polish": "uzupełnianie braków", "braz_por": "preenchimento de lacunas",
                          "russian": "заполнение пропусков", "simp_chinese": "差异补全", "turkish": "eksik tamamlama"},
    "qa_auto_repair": {"english": "QA auto-repair", "french": "réparation QA automatique", "german": "automatische QA-Reparatur",
                       "spanish": "reparación automática de QA", "japanese": "QA自動修復", "korean": "QA 자동 복구",
                       "polish": "automatyczna naprawa QA", "braz_por": "reparo automático de QA",
                       "russian": "автоисправление QA", "simp_chinese": "QA 自动修复", "turkish": "QA otomatik onarım"},
    "glossary": {"english": "Glossary", "french": "Glossaire", "german": "Glossar", "spanish": "Glosario",
                 "japanese": "用語集", "korean": "용어집", "polish": "Glosariusz", "braz_por": "Glossário",
                 "russian": "Глоссарий", "simp_chinese": "术语表", "turkish": "Sözlük"},
    "notation_rules": {"english": "notation rules", "french": "règles d’écriture", "german": "Schreibregeln",
                       "spanish": "reglas de escritura", "japanese": "表記ルール", "korean": "표기 규칙",
                       "polish": "zasady zapisu", "braz_por": "regras de escrita", "russian": "правила написания",
                       "simp_chinese": "书写规则", "turkish": "yazım kuralları"},
    "unattended_run": {"english": "Unattended run", "french": "Exécution sans surveillance",
                       "german": "Unbeaufsichtigter Lauf", "spanish": "Ejecución desatendida", "japanese": "夜間処理",
                       "korean": "무인 실행", "polish": "Uruchomienie bez nadzoru", "braz_por": "Execução autônoma",
                       "russian": "Автономный запуск", "simp_chinese": "无人值守运行", "turkish": "Gözetimsiz çalıştırma"},
    "legacy_translation_candidate": {"english": "old translation candidate", "french": "ancienne traduction candidate",
                                     "german": "alter Übersetzungskandidat", "spanish": "candidata de traducción antigua",
                                     "japanese": "旧版日本語化候補", "korean": "구버전 번역 후보",
                                     "polish": "kandydat starego tłumaczenia", "braz_por": "candidata de tradução antiga",
                                     "russian": "кандидат старого перевода", "simp_chinese": "旧版翻译候选",
                                     "turkish": "eski çeviri adayı"},
    "target_language": {"english": "target language", "french": "langue cible", "german": "Zielsprache",
                        "spanish": "idioma de destino", "japanese": "翻訳先の言語", "korean": "번역 대상 언어",
                        "polish": "język docelowy", "braz_por": "idioma de destino", "russian": "язык перевода",
                        "simp_chinese": "目标语言", "turkish": "hedef dil"},
    "queue": {"english": "queue", "french": "file d’attente", "german": "Warteschlange", "spanish": "cola",
              "japanese": "キュー", "korean": "대기열", "polish": "kolejka", "braz_por": "fila", "russian": "очередь",
              "simp_chinese": "队列", "turkish": "kuyruk"},
    "backup": {"english": "backup", "french": "sauvegarde", "german": "Sicherung", "spanish": "copia de seguridad",
               "japanese": "バックアップ", "korean": "백업", "polish": "kopia zapasowa", "braz_por": "backup",
               "russian": "резервная копия", "simp_chinese": "备份", "turkish": "yedek"},
}

SOURCES = {
    "playset": "official:CK3 jomini/localization/pdx_account（PDX_SDK_ERROR_86）。braz_por・turkish は公式に無いので chosen（英語のまま）。"
               "simp_chinese の「播放集」は公式の訳（不自然だがゲームの表示に合わせる。著者に確認）",
    "mod": "chosen（各言語のゲームのコミュニティで一般的な語）",
}
for _term in TERMS:
    SOURCES.setdefault(_term, "chosen")


def term(term_id: str, lang: str) -> str:
    """訳語表の語。無ければ英語。"""
    entry = TERMS.get(term_id, {})
    return entry.get(lang) or entry.get("english", term_id)
