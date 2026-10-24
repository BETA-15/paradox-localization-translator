"""使い方タブの説明書（english）。節ごとに持つ（第3段 5-2 章）。"""

HELP_TITLE = "Paradox Localization Translator Help"
STALE_NOTICE = "(This section has not been updated for the latest version yet. Some details may be out of date.)"

HELP_SECTIONS = [
    ('intro', 'Paradox Localization Translator Detailed Guide\n\n'),
    ('s00_overview', '''【0. What this app can do】
This is an integrated tool for translating localization YAML for Paradox Interactive games into your chosen target language using a local LLM or a cloud API.
In addition to simple bulk translation, it supports repairing untranslated text, differential updates, QA, searching and correcting translations, checking mod translation status, applying differences to existing translation mods, and cache management.

Main supported titles:
- Crusader Kings III
- Victoria 3
- Hearts of Iron IV
- Stellaris
- Europa Universalis V

'''),
    ('s01_requirements', '''【1. What you need first】
When using a local LLM:
- Ollama or LM Studio
- An LLM model to use for translation

When using a cloud API:
- An API key for OpenAI / Anthropic / Gemini / an OpenAI-compatible API

The distributed app includes Python, Tk/Tcl, and the required GUI components, so users do not need to install Python separately.

'''),
    ('s02_first_checks', '''【2. What to check first after launching】
In the ［Settings］ tab, use ［Display language］ to choose from 11 interface languages. On first launch, the app uses your OS language, or English if that language is not supported. For existing users who have not set an interface language, it uses Japanese. Changes take effect after restarting the app. This setting is separate from the target language for translation.

At the top of the window, there are two separate LLM status displays.

Translation LLM:
Used for standard translation, differential translation, AI proofreading in QA, model speed tests, and more.

Discovery LLM:
Used to discover untranslated mods and assess ambiguous candidates when checking translation status.
A lightweight model of around 3B–8B is recommended for discovery.

The ［Latest translation LLM response (read-only)］ and ［Latest discovery LLM response (read-only)］ fields display the actual responses returned by each LLM and cannot be edited.
Use ［Open full response］ to view the complete response.

'''),
    ('s03_translate_queue', '''【3. Translation / Queue tab】
This is the main tab for standard translation.

［Target language］:
Choose from English, French, German, Spanish, Japanese, Korean, Polish, Portuguese (Brazil), Russian, Simplified Chinese, and Turkish. Each item saves the target language selected when it is added to the queue. Changing the selection later does not change the target language of items already in the queue.

［Add］:
Add YAML files or localization/mod folders. Drag and drop is also supported.

［Remove selected］:
Remove only the selected queue items. The source files are not deleted.

［Clear all］:
Empty the translation queue. Source files and caches are not deleted.

［Start translation］:
Translate items in order, starting from the top.

［Pause］:
Pause at a safe point after the current API/LLM response finishes.

［Save and stop］:
Save the cache and session up to this point, then stop. You can resume the next time you launch the app.

［Apply settings to current translation］:
After changing the model, provider, URL, batch size, worker count, Glossary, combined English/Chinese settings, or other settings during translation, press this button to use the new settings from the next batch onward.

［Overwrite］:
Apply the completed translation to the source mod or a detected translation mod for the target language.
If an existing translation mod has been found, choose “Yes” in the confirmation dialog to overwrite differences in the translation mod, “No” to overwrite the source mod, or “Cancel” to stop. The destination is shown explicitly and a backup is created before overwriting.

'''),
    ('s04_batch_workers', '''【4. Recommended batch / parallel worker settings】
You can choose from three recommended presets.

Stable: batch size 20 / parallel workers 1
- Mods with a lot of long text
- First-time use
- Environments with little memory to spare
- When verifying that everything works is the priority

Standard: batch size 40 / parallel workers 1
- Generally recommended
- A balance between speed and stability

Fast: batch size 60 / parallel workers 2
- When Ollama / LM Studio can handle two requests simultaneously
- When sufficient RAM/VRAM is available

Guidelines:
- Batch size 1–60: normal range
- Batch size above 80: omissions and timeouts are more likely with long text
- Batch size above 120: not recommended
- Parallel workers 1: most stable
- Parallel workers 2: recommended when server-side parallel processing is enabled
- Parallel workers 3 or more: memory pressure, queuing, and timeouts are more likely with local LLMs

For cloud APIs, give priority to the service's rate limits.

'''),
    ('s05_llm_settings', '''【5. LLM / translation settings】
Provider:
Choose from Ollama / LM Studio / OpenAI / Anthropic / Gemini / OpenAI Compatible.

URL:
Ollama default: http://localhost:11434
LM Studio default: http://localhost:1234/v1
Cloud URLs are usually configured automatically.

Model:
After checking the connection, select a model from the list of available models.

API key:
Used for cloud APIs. It is not saved in the app's settings file.

Preset:
Used to set game-specific translation prompt guidelines, such as those for CK3.

Chinese-based translation:
Add Simplified Chinese YAML to the ［Chinese-based translation］ tab to translate with Chinese character vocabulary, institutional terminology, and culture-specific terms as the primary reference. No English file is required.
The available target languages are Japanese and Korean. Korean is intended for mods set in East Asia, particularly those with many Sino-Korean terms for official posts and institutions. For Western titles and religious terminology, standard translation from English tends to produce results closer to the official translations.

Repair untranslated text in existing Japanese localization:
If English or other untranslated text remains in l_japanese, only those portions are targeted for repair.

［Back up, run QA and fix errors after translation］:
After translation, check for untranslated text and broken Paradox syntax using checks appropriate to the target language.

Half-width space handling for Simplified Chinese:
Remove only half-width spaces between Chinese characters and punctuation or brackets. Spaces between words in model numbers and equipment names are preserved.

'''),
    ('s06_cache', '''【6. Cache】
Each translation has its own independent cache. Caches are separated by target language, so translating the same mod into different languages does not mix them together.
When the same mod is updated, the previous cache is identified and unchanged text is not translated again.

［View cache］:
Check the cache contents, entry count, and save location for the selected queue item.

［Add cache］:
Merge another translate_cache.json into the current translation.

Differential updates:
Compare the previous source text in source_manifest.json with the current source text, and retranslate only new or changed portions for the target language.

'''),
    ('s07_review', '''【7. QA / Comparison editor tab】
Compare the source text with the translation in the target language and display issues in a hierarchical view.
You can load YAML files by dragging and dropping them.

Main checks:
- Untranslated text
- Missing keys
- Placeholder mismatches
- Broken [Character...] / $VALUE$ / § color codes and similar syntax
- Unexpected character types for the target language (Chinese characters, kana, Hangul, or Cyrillic)
- Values identical to the source and leftover English (proper nouns, model numbers, and similar items may be excluded)
- Possible typos or missing characters (Japanese only)
- Inconsistent brackets or punctuation

Select a row with an issue to view the source text and translation side by side.
You can edit the ［Translation (editable)］ field directly and save it. Some instances of unexpected characters, values identical to the source, or leftover English are shown as warnings. Review the content and correct it as needed.
AI proofreading uses the current translation LLM settings. After changing settings, press ［Apply current translation settings］.

'''),
    ('s08_diff', '''【8. Difference scan tab】
Compare the source text and the translation in the target language side by side, key by key.
Drag and drop is also supported.

Example classifications:
- Missing: present in the source but absent from the translation
- Untranslated: considered untranslated by the checks for the target language, for example because the value is still the source text
- Target language only: the key exists only on the translation side (the interface displays the language name)
- Matched: the entries correspond correctly

［Translate selected items］:
Translate only the single selected key.

［Translate all missing and untranslated keys］:
Send only the problematic entries to the LLM in bulk.

Differential translation also uses the current translation LLM settings.

'''),
    ('s09_search', '''【9. Translation search tab】
Search across Japanese YAML files/folders and correct translations directly from the search results.

Search targets:
- File names
- Localization keys
- Japanese text

Select a result to edit its current translation, then use ［Save this Japanese translation］ to apply it to the original YAML.

'''),
    ('s10_glossary', '''【10. Glossary tab】
Choose a target language with ［Language］ and register fixed translations separately for each language. Translation, QA, and difference scans use the Glossary for that target language.
Example (Japanese): Grand Campaign → 開辺

［Import from base game］, importing from translated YAML files or mods, and automatic Glossary creation in the work tabs are available for all 11 languages. The automatic creation buttons are ［Auto-create Glossary］ in Translation / Queue, ［Generate Glossary］ in Chinese-based translation, and ［Create Glossary automatically］ in QA / Comparison editor.

When the corresponding source text is included in a translation batch, only the relevant terms are supplied in the LLM prompt.
If you change the Glossary during translation, applying settings to the current translation makes the changes take effect from the next batch onward.

'''),
    ('s11_models', '''【11. Model / Connection tab】
Check connections, list models, run speed tests, and manage profiles.

Speed-test current model:
Measure the single model currently selected.

Compare selected models:
Select up to five models and compare average processing time, tokens/s, and failure rate.

Model profiles:
Save the provider, URL, model, batch size, parallel workers, game preset, and other settings together.
You can delete profiles as well as add them.

The last-used translation/discovery providers, URLs, and models are automatically restored the next time you start the app. API keys are not saved.

'''),
    ('s12_monitor', '''【12. Untranslated monitor tab】
Continuously monitor mod locations registered in the Translation status tab in read-only mode. This does not translate automatically.

Monitor targets:
Select a game/mod location in the ［Translation status］ tab and run ［Research mods in selected locations］ to register that location as a monitor target as well.

Dedicated discovery LLM:
You can specify a model separate from the one used for standard translation. A lightweight model of around 3B–8B is recommended.

［Start continuous monitoring］:
After monitoring starts, the same button changes to ［Stop continuous monitoring］, and the status field displays “● Continuous monitoring active”.

［Rescan］:
Check mod translation status again for the registered monitor targets.

While monitoring, the app checks YAML modification times and sizes and analyzes only targets that have changed. Only ambiguous candidates are sent to the lightweight LLM.

'''),
    ('s13_status', '''【13. Translation status tab】
This tab brings together automatic detection of game/mod locations, selection of scan targets, and mod translation status checks.
You can select multiple locations and run ［Research mods in selected locations］. Results are cached separately for each target language, and only mods that have changed are rescanned. After updating to v0.13, run the scan again because the classification method has changed.

Example statuses:
- Not translated
- Has gaps
- Translated by another mod, with gaps
- Fully translated by another mod
- Translated

Translation mod detection:
Even if the source mod has no localization in the target language, another mod in the same game is considered a translation mod candidate if it has translated keys corresponding to the source keys.
The app also shows whether the translation is complete or has gaps. When the target language is English, external translation mods are not matched because many mods already have English localization.

The ［Full diagnostics］ tab also performs diagnostics and links mods using the target language. Links for languages other than Japanese have had limited verification with real data, so check that the mods have been linked correctly before overwriting.

Search:
Enter a mod name or status to filter the classified list.

Add to queue:
When multiple mods are selected, you can add all selected mods to the standard translation queue. For the Chinese-based queue, all selected mods that have Chinese localization are added.

Add to queue excluding selected mods:
Exclude only the selected mods and add the remaining mods to the standard translation queue in bulk, or add only those with Chinese localization to the Chinese-based queue.

Overwrite translation mod:
If an existing translation mod for the target language is found, apply the missing entries as differences to the translation mod rather than the source mod.
Preserve existing translations, and add or update only missing or untranslated keys.
Before execution, the destination mod name and path are displayed, a backup is created, and confirmation is requested twice.

［Translate differences only］:
For the target language, translate only new or changed keys and missing translations.

'''),
    ('s14_data_folder', '''【14. Automatically generated files and save locations】
All automatically generated files are kept together in a single folder.

Default:
書類/Documents/Paradox Localization Translator/

Structure:
Paradox Localization Translator/
├── 翻訳結果/
├── キャッシュ/
├── バックアップ/
├── ログ/
├── 作業データ/
└── 設定/

Translation output folders are also separated by target language. Folder names end in suffixes such as “…_japanese” or “…_french”, and each folder contains YAML files for that language.

At startup, the app detects ParadoxLocalizationTranslator_Data next to the executable from an older version and transfers the necessary data to this save location without destroying the old data. Old absolute paths in resumable sessions are also remapped to the current save location.

Use ［Change location］ in the ［Settings］ tab to choose another SSD or any folder. You can also copy existing data when migrating.

'''),
    ('s15_logs_diagnostics', '''【15. Error logs / diagnostics】
App exceptions, LLM connection failures, YAML parsing failures, write failures, and similar errors are saved in daily logs.

［Open error logs］:
Open the logs folder.

［Collect diagnostic logs］:
Bundle the OS, app version, model information, error logs, and other details into a diagnostic ZIP. API keys and translation text are not included.

'''),
    ('s16_close_button', '''【16. When you press the × button】
By default, pressing the × button in the upper-right/upper-left corner displays this confirmation:

“Minimize the window or quit the app?”

Minimize:
- Only minimizes the window
- Translation, discovery, and LLM processing do not stop

Quit:
- Saves the session if there are unfinished translation queue items
- Does not retain successfully completed queue items as a resumable session
- A session you decline to restore at the next startup is discarded and will not appear again
- Requests a safe stop of LLM/translation processing before exiting the app

To change this later:
Under ［Settings］ → ［Action when pressing the window's × button］,
choose one of the following:
- Ask every time
- Minimize
- Quit

'''),
    ('s17_safety', '''【17. Safety precautions】
- Always read the warning before overwriting the source mod directly.
- Steam Workshop updates may overwrite manual changes.
- An automatic backup is created when overwriting directly.
- For large translations, start with the Standard settings (40 / 1).
- Use a small discovery LLM model to reduce resource usage.
- Cloud API keys are not saved.
- If a problem occurs, creating a diagnostic logs ZIP makes it easier to investigate the cause.

'''),
    ('s18_common_uses', '''【18. Common workflows】
Translate a new mod:
1. Choose the ［Target language］, then drag in the mod
2. Check the translation model
3. Start translation
4. Run QA
5. Search and correct translations if needed
6. Apply the completed translation to the mod by overwriting differences

Repair gaps in an existing translation mod:
1. Choose the target language and run ［Research mods in selected locations］
2. Check for “Translated by another mod, with gaps” in Translation status
3. Translate the target mod
4. During translation, you can use ［Pause］ or ［Save and stop］
5. Use ［Open output］ to check the completed files
6. Press ［Overwrite］; if a translation mod for the target language has been found, select the destination in the confirmation dialog

Translate additions only after a mod update:
1. Choose the target language and add the updated mod again
2. The previous cache/source snapshot is identified automatically
3. Check the differential update
4. Translate only new or changed keys

Correct Japanese translations manually:
1. Open the Translation search tab
2. Search for a key or Japanese text
3. Select a result
4. Edit and save the translation

This Help tab is the app's built-in manual. Even users who receive only the distributed app can consult everything from basic operations to advanced features without opening an external README.

'''),
    ('unofficial', '''【This is an unofficial tool】
This is an unofficial tool developed by an individual and is not affiliated with Paradox Interactive. The names of the games are trademarks of their respective owners.
The tool is free, and all features are available to everyone (MIT license).

'''),
    ('support', '【Donations and support】\nIf you would like to support development, you can donate through GitHub Sponsors:\nhttps://github.com/sponsors/BETA-15\nAll features stay free, and donating does not unlock any extra features (there are no rewards, only our thanks).\nDonations are received by 株式会社ＶＦソフトウェア (VF Software) and go toward the time and costs of development.\n\n'),
    ('publishing', '''【When publishing a translated mod】
- Obtain permission from the source mod's author. When publishing a translation of someone else's mod on Steam Workshop or a similar platform, it is customary to contact the original author and obtain permission.
- Publish it for free. Paradox Interactive's terms of use do not allow user-created content such as mods to be placed behind a paywall (donations for the time spent are allowed).
- If it includes machine translation, mentioning this in the description helps users make an informed decision.
'''),
]
SOURCE_HASHES = {'intro': 'dc0e64262c52', 's00_overview': '57e3f61ee91f', 's01_requirements': 'f6c2c4898718', 's02_first_checks': 'ad4282fa15f0', 's03_translate_queue': '38ceaa862083', 's04_batch_workers': '0ad57aad8db6', 's05_llm_settings': 'f50d5592d09b', 's06_cache': '053b8fd863bd', 's07_review': 'effd2b2c02b3', 's08_diff': '047b909759cf', 's09_search': '331764e4826a', 's10_glossary': 'f3d3a966a4a3', 's11_models': '101883be6b22', 's12_monitor': 'b317e0f4bc37', 's13_status': '7273a7c98ae2', 's14_data_folder': '5e1b34c6fa85', 's15_logs_diagnostics': '78e7512742d6', 's16_close_button': 'bf95d994339e', 's17_safety': 'a3ae50ab1c28', 's18_common_uses': '054ef2c9de07', 'unofficial': '4f1fb69113b7', 'support': '17cde2812921', 'publishing': '13a1da9a3844'}
