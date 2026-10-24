"""使い方タブの説明書（german）。節ごとに持つ（第3段 5-2 章）。"""

HELP_TITLE = "Paradox Localization Translator — Anleitung"

STALE_NOTICE = '(Dieser Abschnitt wurde noch nicht an die neueste Version angepasst. Einige Angaben sind veraltet. Die aktuellen Informationen finden Sie in der englischen Fassung.)'

HELP_SECTIONS = [
    ('intro', 'Paradox Localization Translator — Ausführliche Anleitung\n\n'),
    ('s00_overview', '''【0. Was diese Anwendung kann】
Dieses integrierte Werkzeug übersetzt Lokalisierungs-YAML-Dateien von Spielen aus dem Hause Paradox Interactive mithilfe eines lokalen LLM oder einer Cloud-API in die gewählte Zielsprache.
Neben der einfachen Stapelübersetzung bietet es die Reparatur unübersetzter Texte, Aktualisierungen anhand von Änderungen, QA, Suche und Korrektur von Übersetzungen, die Prüfung des Übersetzungsstatus von Mods, die Übernahme von Änderungen in bestehende Übersetzungsmods und die Cacheverwaltung.

Wichtigste unterstützte Spiele:
• Crusader Kings III
• Victoria 3
• Hearts of Iron IV
• Stellaris
• Europa Universalis V

'''),
    ('s01_requirements', '''【1. Was Sie zum Einstieg benötigen】
Für ein lokales LLM:
• Ollama oder LM Studio
• Ein LLM-Modell für die Übersetzung

Für eine Cloud-API:
• Einen API-Schlüssel für OpenAI / Anthropic / Gemini / eine OpenAI-kompatible API

Die ausgelieferte Anwendung enthält Python, Tk/Tcl und alle erforderlichen GUI-Komponenten. Sie müssen Python daher nicht gesondert installieren.

'''),
    ('s02_first_checks', '''【2. Erste Prüfungen nach dem Start】
Unter ［Anzeigesprache］ im Tab ［Einstellungen］ können Sie eine von 11 Oberflächensprachen wählen. Beim ersten Start wird die Sprache des Betriebssystems verwendet, bei nicht unterstützten Sprachen Englisch. Bei bisherigen Nutzern, die noch keine Anzeigesprache festgelegt haben, wird Japanisch verwendet. Änderungen werden nach einem Neustart wirksam. Diese Einstellung ist unabhängig von der Zielsprache der Übersetzung.

Oben im Fenster gibt es zwei getrennte LLM-Statusanzeigen.

Übersetzungs-LLM:
Wird für normale Übersetzungen, die Übersetzung von Änderungen, die KI-Korrektur im QA, Modelltempotests und ähnliche Aufgaben verwendet.

Such-LLM:
Wird bei der Suche nach unübersetzten Mods und zur Beurteilung uneindeutiger Kandidaten beim Prüfen des Übersetzungsstatus verwendet.
Für die Suche empfiehlt sich ein leichtgewichtiges Modell mit etwa 3B bis 8B.

Die Felder „Letzte Antwort des Übersetzungs-LLM (nur lesen)“ und „Letzte Antwort des Such-LLM (nur lesen)“ zeigen die tatsächlich vom jeweiligen LLM erhaltene Antwort schreibgeschützt an.
Mit „Vollständige Antwort öffnen“ können Sie die gesamte Antwort ansehen.

'''),
    ('s03_translate_queue', '''【3. Tab Übersetzung / Warteschlange】
Hier findet die normale Übersetzung statt.

［Zielsprache］:
Zur Wahl stehen Englisch, Französisch, Deutsch, Spanisch, Japanisch, Koreanisch, Polnisch, Portugiesisch (Brasilien), Russisch, vereinfachtes Chinesisch und Türkisch. Jeder Eintrag speichert die beim Hinzufügen zur Warteschlange gewählte Zielsprache. Eine spätere Änderung der Auswahl ändert die Zielsprache bereits hinzugefügter Einträge nicht.

［Hinzufügen］:
Fügt YAML-Dateien oder localization-/Mod-Ordner hinzu. Drag-and-drop ist ebenfalls möglich.

［Auswahl entfernen］:
Entfernt nur die ausgewählten Warteschlangeneinträge. Die Originaldateien werden nicht gelöscht.

［Alles leeren］:
Leert die Übersetzungswarteschlange. Originaldateien und Caches werden nicht gelöscht.

［Übersetzung starten］:
Übersetzt die Einträge der Reihe nach von oben nach unten.

［Pausieren］:
Pausiert an einem sicheren Punkt, nachdem die laufende API-/LLM-Antwort abgeschlossen ist.

［Speichern und unterbrechen］:
Speichert den bisherigen Cache und die Sitzung und hält die Verarbeitung an. Beim nächsten Start können Sie fortfahren.

［Einstellungen auf aktuelle Übersetzung anwenden］:
Wenn Sie während der Übersetzung Modell, Anbieter, URL, Stapelgröße, Parallelität, Glossar, die Einstellungen für die kombinierte Nutzung von Englisch und Chinesisch usw. ändern, verwendet die Anwendung nach einem Klick auf diesen Button die neuen Einstellungen ab dem nächsten Stapel.

［Ausgewählte Einträge überschreiben］:
Überträgt die fertige Übersetzung in den Ursprungsmod oder in den für die Zielsprache erkannten Übersetzungsmod.
Wenn ein Übersetzungsmod vorhanden ist, schreibt „Ja“ im Bestätigungsdialog die Änderungen in den Übersetzungsmod, „Nein“ in den Ursprungsmod und „Abbrechen“ beendet den Vorgang ohne Übernahme. Vor dem Überschreiben wird das Ziel ausdrücklich angezeigt und eine Sicherung erstellt.

'''),
    ('s04_batch_workers', '''【4. Empfohlene Einstellungen für Stapel / Parallelität】
Es stehen drei empfohlene Voreinstellungen zur Wahl.

Stabil: Stapelgröße 20 / Parallelität 1
• Mods mit vielen langen Texten
• Erste Verwendung
• Systeme mit wenig freiem Arbeitsspeicher
• Wenn Sie zunächst den ordnungsgemäßen Betrieb prüfen möchten

Standard: Stapelgröße 40 / Parallelität 1
• Für die normale Verwendung empfohlen
• Ausgewogenes Verhältnis von Geschwindigkeit und Stabilität

Schnell: Stapelgröße 60 / Parallelität 2
• Wenn Ollama / LM Studio zwei Anfragen gleichzeitig verarbeiten kann
• Wenn genügend RAM/VRAM vorhanden ist

Richtwerte:
• Stapelgröße 1–60: üblicher Bereich
• Über 80: bei langen Texten häufiger Auslassungen und Zeitüberschreitungen
• Über 120: nicht empfohlen
• Parallelität 1: am stabilsten
• Parallelität 2: empfohlen, wenn die parallele Verarbeitung auf dem Server aktiviert ist
• Parallelität 3 oder höher: bei lokalen LLM häufiger Speicherdruck, Warteschlangen und Zeitüberschreitungen

Bei Cloud-APIs haben die Ratenlimits des jeweiligen Dienstes Vorrang.

'''),
    ('s05_llm_settings', '''【5. LLM / Übersetzungseinstellungen】
Anbieter:
Zur Wahl stehen Ollama / LM Studio / OpenAI / Anthropic / Gemini / OpenAI Compatible.

URL:
Ollama-Standard: http://localhost:11434
LM Studio-Standard: http://localhost:1234/v1
Für Cloud-Dienste wird die URL normalerweise automatisch eingestellt.

Modell:
Wählen Sie nach der Verbindungsprüfung aus der Liste der verfügbaren Modelle.

API-Schlüssel:
Wird für Cloud-APIs benötigt. Er wird nicht in der Einstellungsdatei der Anwendung gespeichert.

Spielvoreinstellung:
Legt die Übersetzungsrichtlinien im Prompt für das jeweilige Spiel, etwa CK3, fest.

Übersetzung auf chinesischer Basis:
Wenn Sie YAML-Dateien in vereinfachtem Chinesisch in den Tab ［Übersetzung auf chinesischer Basis］ aufnehmen, bilden chinesische Schriftzeichenbegriffe, institutionelle Begriffe und spezifische chinesische Ausdrücke die vorrangige Grundlage der Übersetzung. Englische Dateien sind nicht erforderlich.
Als Zielsprache können Sie Japanisch oder Koreanisch wählen. Koreanisch eignet sich für Mods über Ostasien, die viele auf chinesischen Schriftzeichen beruhende Begriffe für Ämter und Institutionen enthalten. Bei westlichen Titeln und religiösen Begriffen kommt die normale Übersetzung aus dem Englischen den offiziellen Übersetzungen näher.

Unübersetzte Texte in bestehenden japanischen Übersetzungen reparieren:
Wenn in l_japanese englische oder andere fremdsprachige Texte verbleiben, werden nur diese Stellen zur Reparatur herangezogen.

［Nach der Übersetzung sichern, QA ausführen und Fehler beheben］:
Prüft nach der Übersetzung je nach Zielsprache auf unübersetzte Texte und beschädigte Paradox-Syntax.

Behandlung von Halbbreiten-Leerzeichen in vereinfachtem Chinesisch:
Entfernt nur Halbbreiten-Leerzeichen zwischen chinesischen Zeichen und Satzzeichen oder Klammern. Leerzeichen zwischen Wörtern in Modellbezeichnungen und Ausrüstungsnamen bleiben erhalten.

'''),
    ('s06_cache', '''【6. Cache】
Jede Übersetzung besitzt einen eigenen Cache. Die Caches werden nach Zielsprache getrennt, sodass sich die Daten nicht vermischen, wenn Sie denselben Mod in eine andere Sprache übersetzen.
Auch bei einer Aktualisierung desselben Mods wird der bisherige Cache ermittelt, damit unveränderte Texte nicht erneut übersetzt werden.

［Cache anzeigen］:
Zeigt Inhalt, Eintragszahl und Speicherort des Caches für den ausgewählten Warteschlangeneintrag.

［Cache hinzufügen］:
Führt eine weitere translate_cache.json mit der aktuellen Übersetzung zusammen.

Aktualisierung anhand von Änderungen:
Vergleicht die source_manifest.json der früheren Originaltexte mit den aktuellen Originaltexten und übersetzt für die Zielsprache nur neue oder geänderte Stellen erneut.

'''),
    ('s07_review', '''【7. Tab QA / Vergleich bearbeiten】
Vergleicht Originaltexte mit Übersetzungen in der Zielsprache und zeigt Probleme hierarchisch an.
YAML-Dateien können per Drag-and-drop geladen werden.

Wichtigste Prüfungen:
• Unübersetzte Texte
• Fehlende Schlüssel
• Abweichende Platzhalter
• Beschädigungen von [Character...] / $VALUE$ / §Farbcodes usw.
• Für die Zielsprache unpassende Zeichenarten (chinesische Zeichen, Kana, Hangul, kyrillische Zeichen)
• Mit dem Original identische Werte und verbliebenes Englisch (Eigennamen, Modellbezeichnungen usw. können ausgenommen werden)
• Mögliche Tippfehler oder fehlende Zeichen (nur Japanisch)
• Unstimmigkeiten bei Klammern und Satzzeichen

Wenn Sie eine problematische Zeile auswählen, werden Original und Übersetzung nebeneinander angezeigt.
Sie können das Feld ［Übersetzung (bearbeitbar)］ direkt bearbeiten und speichern. Manche Fälle von vermischten Zeichenarten, mit dem Original identischen Werten und verbliebenem Englisch werden als Hinweise angezeigt. Prüfen Sie den Inhalt und korrigieren Sie ihn bei Bedarf.
Die KI-Korrektur verwendet die aktuellen Einstellungen des Übersetzungs-LLM. Klicken Sie nach Einstellungsänderungen auf ［Aktuelle Übersetzungseinstellungen anwenden］.

'''),
    ('s08_diff', '''【8. Tab Differenzprüfung】
Stellt Originaltexte und Übersetzungen in der Zielsprache schlüsselweise gegenüber.
Drag-and-drop wird ebenfalls unterstützt.

Beispiele für die Bewertung:
• Fehlend: im Original vorhanden, in der Übersetzung nicht
• Unübersetzt: nach den Kriterien der Zielsprache als unübersetzt eingestuft, etwa weil der Originaltext unverändert geblieben ist
• Nur in der Zielsprache: der Schlüssel existiert nur auf der Übersetzungsseite (die Oberfläche zeigt den Sprachnamen an)
• Zugeordnet: die Einträge sind korrekt zugeordnet

［Ausgewählte Einträge übersetzen］:
Übersetzt nur den einen ausgewählten Schlüssel.

［Alle fehlenden und unübersetzten Schlüssel übersetzen］:
Sendet nur die problematischen Einträge gesammelt an das LLM.

Auch die Übersetzung von Änderungen verwendet die aktuellen Einstellungen des Übersetzungs-LLM.

'''),
    ('s09_search', '''【9. Tab Übersetzungssuche】
Durchsucht japanische YAML-Dateien und Ordner übergreifend und ermöglicht die direkte Korrektur von Übersetzungen aus den Suchergebnissen heraus.

Durchsuchte Inhalte:
• Dateinamen
• Lokalisierungsschlüssel
• Japanischer Text

Nach Auswahl eines Ergebnisses können Sie die aktuelle Übersetzung bearbeiten. Mit ［Diese japanische Übersetzung speichern］ wird die Änderung in die ursprüngliche YAML-Datei übernommen.

'''),
    ('s10_glossary', '''【10. Tab Glossar】
Wählen Sie unter ［Sprache］ die Zielsprache, um je Sprache festgelegte Übersetzungen einzutragen. Übersetzung, QA und Differenzprüfung verwenden das Glossar der jeweiligen Zielsprache.
Beispiel (Japanisch): Grand Campaign → 開辺

［Aus Hauptspiel importieren］, der Import aus bereits übersetzten YAML-Dateien oder Mods sowie ［Glossar automatisch erstellen］ in den einzelnen Arbeitstabs stehen für alle 11 Sprachen zur Verfügung.

Wenn der passende Originaltext in einem Übersetzungsstapel enthalten ist, werden nur die betreffenden Begriffe in den LLM-Prompt aufgenommen.
Auch Änderungen am Glossar während der Verarbeitung werden ab dem nächsten Stapel wirksam, wenn Sie die Einstellungen auf die aktuelle Übersetzung anwenden.

'''),
    ('s11_models', '''【11. Tab Modelle / Verbindung】
Hier können Sie die Verbindung prüfen, Modelle auflisten, Tempotests durchführen und Profile verwalten.

Tempo des aktuellen LLM testen:
Misst nur das eine derzeit ausgewählte Modell.

Ausgewählte Modelle vergleichen:
Wählen Sie bis zu 5 Modelle aus, um die durchschnittliche Verarbeitungszeit, tokens/s und die Fehlerquote zu vergleichen.

Modellprofile:
Anbieter, URL, Modell, Stapelgröße, Parallelität, Spielvoreinstellung usw. können gemeinsam gespeichert werden.
Profile lassen sich nicht nur hinzufügen, sondern auch löschen.

Die zuletzt verwendeten Anbieter, URLs und Modelle für Übersetzung und Suche werden beim nächsten Start automatisch wiederhergestellt. API-Schlüssel werden nicht gespeichert.

'''),
    ('s12_monitor', '''【12. Tab Überwachung unübersetzter Texte】
Überwacht die im Tab Übersetzungsstatus eingetragenen Mod-Speicherorte dauerhaft und schreibgeschützt. Es erfolgt keine automatische Übersetzung.

Überwachte Speicherorte:
Wenn Sie im Tab ［Übersetzungsstatus］ ein Spiel beziehungsweise einen Mod-Speicherort auswählen und ［Mods an ausgewählten Speicherorten prüfen］ ausführen, wird dieser Speicherort auch für die Überwachung registriert.

Eigenes Such-LLM:
Sie können ein anderes Modell als für die normale Übersetzung festlegen. Ein leichtgewichtiges Modell mit etwa 3B bis 8B wird empfohlen.

［Dauerüberwachung starten］:
Nach dem Start wird derselbe Button zu ［Dauerüberwachung stoppen］ und das Statusfeld zeigt „● Dauerüberwachung“ an.

［Erneut prüfen］:
Prüft den Übersetzungsstatus der Mods an den bereits registrierten überwachten Speicherorten erneut.

Während der Überwachung werden Änderungszeit und Größe der YAML-Dateien geprüft. Nur geänderte Einträge werden analysiert. Lediglich uneindeutige Kandidaten werden an das leichtgewichtige LLM gesendet.

'''),
    ('s13_status', '''【13. Tab Übersetzungsstatus】
Hier sind die automatische Erkennung von Spiel-/Mod-Speicherorten, die Auswahl der zu prüfenden Orte und die Prüfung des Übersetzungsstatus von Mods zusammengefasst.
Sie können mehrere Speicherorte auswählen und ［Mods an ausgewählten Speicherorten prüfen］ ausführen. Die Ergebnisse werden je Zielsprache zwischengespeichert; nur geänderte Mods werden erneut geprüft. Führen Sie nach der Aktualisierung auf v0.13 die Prüfung erneut aus, da sich das Bewertungsverfahren geändert hat.

Anzeigebeispiele:
• Nicht übersetzt
• Lücken vorhanden
• Durch andere Mod übersetzt, mit Lücken
• Durch andere Mod vollständig übersetzt
• Übersetzt

Erkennung von Übersetzungsmods:
Auch wenn der Ursprungsmod die Zielsprache nicht enthält, wird ein anderer Mod desselben Spiels als Übersetzungsmod-Kandidat eingestuft, wenn er übersetzte Schlüssel enthält, die den Originalschlüsseln entsprechen.
Es wird auch angezeigt, ob die Übersetzung vollständig ist oder Lücken aufweist. Bei Englisch als Zielsprache werden externe Übersetzungsmods nicht abgeglichen, da viele Mods bereits Englisch enthalten.

Auch der Tab ［Gesamtdiagnose］ führt Diagnosen und Zuordnungen anhand der Zielsprache durch. Zuordnungen für andere Sprachen als Japanisch wurden bisher seltener mit echten Daten geprüft. Kontrollieren Sie deshalb vor dem Überschreiben die Zuordnung.

Suche:
Geben Sie einen Mod-Namen oder Status ein, um die bereits bewertete Liste zu filtern.

Zur Warteschlange hinzufügen:
Alle gemeinsam ausgewählten Mods können zur normalen Übersetzungswarteschlange hinzugefügt werden. Zur Warteschlange für Übersetzung auf chinesischer Basis werden alle ausgewählten Mods mit chinesischer Lokalisierung hinzugefügt.

Ausgewählte Mods ausschließen und zur Warteschlange hinzufügen:
Sie können nur die ausgewählten Mods ausschließen und alle übrigen gesammelt zur normalen Übersetzungswarteschlange hinzufügen. Alternativ werden nur die übrigen Mods mit chinesischer Lokalisierung zur Warteschlange für Übersetzung auf chinesischer Basis hinzugefügt.

Übersetzungsmods überschreiben:
Wenn ein bestehender Übersetzungsmod für die Zielsprache vorhanden ist, werden fehlende Übersetzungen als Änderungen dort ergänzt und nicht im Ursprungsmod.
Bestehende Übersetzungen bleiben erhalten; nur fehlende oder unübersetzte Schlüssel werden ergänzt beziehungsweise aktualisiert.
Vor der Ausführung werden Name und Pfad des Zielmods angezeigt. Es erfolgen eine Sicherung und eine doppelte Bestätigung.

［Nur Unterschiede übersetzen］:
Übersetzt für die Zielsprache nur neue oder geänderte Schlüssel sowie fehlende Übersetzungen.

'''),
    ('s14_data_folder', '''【14. Automatisch erzeugte Dateien und Speicherort】
Alle automatisch erzeugten Dateien werden in einem einzigen Ordner zusammengefasst.

Standard:
書類/Documents/Paradox Localization Translator/

Struktur:
Paradox Localization Translator/
├── 翻訳結果/
├── キャッシュ/
├── バックアップ/
├── ログ/
├── 作業データ/
└── 設定/

Auch die Ausgabeordner für Übersetzungsergebnisse sind nach Zielsprache getrennt. Ihre Namen enden beispielsweise auf „…_japanese“ oder „…_french“; darin werden die YAML-Dateien der jeweiligen Sprache gespeichert.

Der Ordner ParadoxLocalizationTranslator_Data neben der ausführbaren Datei einer älteren Version wird beim Start erkannt. Die benötigten Daten werden ohne zerstörerische Änderungen an vorhandenen Daten an den aktuellen Speicherort übernommen. Auch alte absolute Pfade in fortzusetzenden Sitzungen werden auf den aktuellen Speicherort umgedeutet.

Über ［Speicherort ändern］ im Tab ［Einstellungen］ können Sie eine andere SSD oder einen beliebigen Ordner wählen. Bestehende Daten können dabei auch durch Kopieren migriert werden.

'''),
    ('s15_logs_diagnostics', '''【15. Fehlerprotokolle / Diagnose】
Anwendungsausnahmen, fehlgeschlagene LLM-Verbindungen, YAML-Analysefehler, Schreibfehler und ähnliche Ereignisse werden in täglichen Protokollen gespeichert.

［Fehlerprotokolle öffnen］:
Öffnet den Protokollordner.

［Diagnoseprotokolle sammeln］:
Fasst Betriebssystem, Anwendungsversion, Modellinformationen, Fehlerprotokolle usw. in einer Diagnose-ZIP zusammen. API-Schlüssel und übersetzte Texte sind nicht enthalten.

'''),
    ('s16_close_button', '''【16. Beim Klicken auf den ×-Button】
Wenn Sie oben rechts beziehungsweise links auf den ×-Button klicken, erscheint standardmäßig folgende Rückfrage.

„Fenster minimieren oder App beenden?“

Minimieren:
• Nur das Fenster wird minimiert
• Übersetzung, Suche und LLM-Verarbeitung laufen weiter

Beenden:
• Wenn die Übersetzungswarteschlange noch unvollständige Einträge enthält, wird die Sitzung gespeichert
• Erfolgreich abgeschlossene Warteschlangen bleiben nicht als wiederherzustellende Sitzung erhalten
• Wenn Sie beim nächsten Start die Wiederherstellung einer Sitzung ablehnen, wird diese verworfen und nicht erneut angeboten
• Vor dem Beenden fordert die Anwendung einen sicheren Stopp der LLM-/Übersetzungsverarbeitung an

Wenn Sie dieses Verhalten später ändern möchten:
Unter ［Einstellungen］ → ［Verhalten beim Schließen des Fensters］ können Sie wählen:
• Jedes Mal fragen
• Minimieren
• Beenden

'''),
    ('s17_safety', '''【17. Hinweise zur sicheren Verwendung】
• Prüfen Sie vor dem direkten Überschreiben des Ursprungsmods immer den Inhalt der Warnung.
• Steam Workshop-Aktualisierungen können manuelle Änderungen überschreiben.
• Beim direkten Überschreiben wird automatisch eine Sicherung erstellt.
• Für umfangreiche Übersetzungen wird zunächst die Standardeinstellung (40 / 1) empfohlen.
• Ein kleines Modell für das Such-LLM reduziert die Belastung.
• Cloud-API-Schlüssel werden nicht gespeichert.
• Bei Problemen erleichtert eine ZIP mit Diagnoseprotokollen die Ursachenanalyse.

'''),
    ('s18_common_uses', '''【18. Häufige Anwendungsfälle】
Einen neuen Mod übersetzen:
1. Wählen Sie die ［Zielsprache］ und ziehen Sie dann den Mod in die Anwendung
2. Prüfen Sie das Übersetzungsmodell
3. Starten Sie die Übersetzung
4. Führen Sie QA durch
5. Suchen und korrigieren Sie Übersetzungen bei Bedarf
6. Übernehmen Sie die fertige Fassung durch Überschreiben der Änderungen in den Mod

Lücken in einem bestehenden Übersetzungsmod beheben:
1. Wählen Sie die Zielsprache und führen Sie ［Mods an ausgewählten Speicherorten prüfen］ aus
2. Prüfen Sie im Übersetzungsstatus den Eintrag „Durch andere Mod übersetzt, mit Lücken“
3. Übersetzen Sie den betreffenden Mod
4. Während der Übersetzung können Sie ［Pausieren］ oder ［Speichern und unterbrechen］ verwenden
5. Prüfen Sie die fertigen Dateien über ［Ausgabe öffnen］
6. Klicken Sie auf ［Ausgewählte Einträge überschreiben］; falls ein Übersetzungsmod für die Zielsprache gefunden wurde, wählen Sie im Bestätigungsdialog das Ziel

Nur nach einer Mod-Aktualisierung zusätzliche Texte übersetzen:
1. Wählen Sie die Zielsprache und fügen Sie den aktualisierten Mod erneut hinzu
2. Der frühere Cache und der Originaltext-Snapshot werden automatisch ermittelt
3. Prüfen Sie die Aktualisierung anhand der Änderungen
4. Übersetzen Sie nur neue oder geänderte Schlüssel

Japanische Übersetzungen manuell korrigieren:
1. Öffnen Sie den Tab Übersetzungssuche
2. Suchen Sie nach einem Schlüssel oder japanischem Text
3. Wählen Sie ein Ergebnis
4. Bearbeiten Sie die Übersetzung und speichern Sie sie

Dieser Hilfe-Tab ist die integrierte Anleitung der Anwendung. Auch Nutzer, die nur die ausgelieferte Anwendung erhalten haben, können grundlegende Bedienung und erweiterte Funktionen nachlesen, ohne eine externe README zu öffnen.

'''),
    ('unofficial', '''【Ein inoffizielles Werkzeug】
Dieses inoffizielle Werkzeug wird von einer Privatperson entwickelt und steht in keiner Verbindung zu Paradox Interactive. Die Namen der Spiele sind Marken ihrer jeweiligen Rechteinhaber.
Das Werkzeug ist kostenlos und alle Funktionen stehen jedem zur Verfügung (MIT-Lizenz).

'''),
    ('support', '【Spenden und Unterstützung】\nWenn Sie die Entwicklung unterstützen möchten, können Sie über GitHub Sponsors spenden:\nhttps://github.com/sponsors/BETA-15\nAlle Funktionen bleiben kostenlos, und eine Spende schaltet keine zusätzlichen Funktionen frei (keine Gegenleistung, nur unser Dank).\nEmpfänger der Spenden ist VF Software Co., Ltd.; sie werden für die Zeit und die Kosten der Entwicklung verwendet.\n\n'),
    ('publishing', '''【Bitten zur Veröffentlichung übersetzter Mods】
• Holen Sie die Erlaubnis des Autors des Ursprungsmods ein. Wenn Sie die Übersetzung eines fremden Mods auf Steam Workshop oder anderswo veröffentlichen möchten, ist es üblich, den ursprünglichen Autor zu kontaktieren und um Erlaubnis zu bitten.
• Veröffentlichen Sie die Übersetzung kostenlos. Nach den Nutzungsbedingungen von Paradox Interactive dürfen von Nutzern erstellte Inhalte wie Mods nicht hinter einer Bezahlschranke angeboten werden (Spenden als Anerkennung für die aufgewendete Zeit sind erlaubt).
• Wenn maschinell übersetzte Texte enthalten sind, hilft ein entsprechender Hinweis in der Beschreibung den Nutzern bei ihrer Entscheidung.
'''),
]
SOURCE_HASHES = {'intro': 'dc0e64262c52', 's00_overview': '57e3f61ee91f', 's01_requirements': 'f6c2c4898718', 's02_first_checks': 'ad4282fa15f0', 's03_translate_queue': '38ceaa862083', 's04_batch_workers': '0ad57aad8db6', 's05_llm_settings': 'f50d5592d09b', 's06_cache': '053b8fd863bd', 's07_review': 'effd2b2c02b3', 's08_diff': '047b909759cf', 's09_search': '331764e4826a', 's10_glossary': 'f3d3a966a4a3', 's11_models': '101883be6b22', 's12_monitor': 'b317e0f4bc37', 's13_status': '7273a7c98ae2', 's14_data_folder': '5e1b34c6fa85', 's15_logs_diagnostics': '78e7512742d6', 's16_close_button': 'bf95d994339e', 's17_safety': 'a3ae50ab1c28', 's18_common_uses': '054ef2c9de07', 'unofficial': '4f1fb69113b7', 'support': '17cde2812921', 'publishing': '13a1da9a3844'}
