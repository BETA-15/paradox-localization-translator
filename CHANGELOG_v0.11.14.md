# v0.11.14

- Fixed remaining text decoding failures that could raise `utf-8 codec can't decode byte 0xff` during translation.
- Centralized BOM-aware decoding for UTF-8, UTF-8 BOM, UTF-16 LE, UTF-16 BE, plus conservative BOM-less UTF-16 detection.
- JSON text loading now uses the same decoder, preventing encoding mismatches in auxiliary data files.
- Localization decode failures now include the exact file path in the error message for diagnostics.
- No translation logic, UI layout, queue behavior, or syntax auto-QA behavior was changed.
