"""画面の文字列（french）。単位ごとのファイルを1つの辞書にまとめる。

PyInstaller が同梱するよう、単位のモジュールはすべて明示的に読み込む（動的な読み込みはしない）。
"""
from . import p0_common
from . import u1_translate
from . import u2_chinese
from . import u3_review
from . import u4_glossary
from . import u5_models
from . import u6_status
from . import u7_diagnostics
from . import u9_core
from . import help_doc
from . import languages

STRINGS = {}
for _part in (languages.STRINGS, p0_common.STRINGS, u1_translate.STRINGS, u2_chinese.STRINGS, u3_review.STRINGS, u4_glossary.STRINGS, u5_models.STRINGS, u6_status.STRINGS, u7_diagnostics.STRINGS, u9_core.STRINGS):
    STRINGS.update(_part)
