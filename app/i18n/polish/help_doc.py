"""使い方タブの説明書（polish）。節ごとに持つ（第3段 5-2 章）。"""

HELP_TITLE = "Paradox Localization Translator — Instrukcja obsługi"

STALE_NOTICE = "（Ta sekcja nie została jeszcze dostosowana do najnowszej wersji. Część informacji może być nieaktualna; najnowsze informacje znajdziesz w wersji angielskiej.）"

HELP_SECTIONS = [
    ('intro', 'Szczegółowy przewodnik po Paradox Localization Translator\n\n'),
    ('s00_overview', '''【0. Co można zrobić w tej aplikacji】
To zintegrowane narzędzie do tłumaczenia plików YAML lokalizacji gier Paradox Interactive na wybrany język docelowy za pomocą lokalnego LLM lub API w chmurze.
Oprócz tłumaczenia zbiorczego umożliwia naprawę nieprzetłumaczonych tekstów, aktualizację różnic, kontrolę jakości (QA), wyszukiwanie i poprawianie tłumaczeń, badanie stanu tłumaczenia modów, nanoszenie różnic na istniejące mody tłumaczące i zarządzanie pamięcią podręczną.

Główne obsługiwane gry:
• Crusader Kings III
• Victoria 3
• Hearts of Iron IV
• Stellaris
• Europa Universalis V

'''),
    ('s01_requirements', '''【1. Co jest potrzebne na początek】
Jeśli korzystasz z lokalnego LLM:
• Ollama lub LM Studio
• Model LLM do tłumaczenia

Jeśli korzystasz z API w chmurze:
• Klucz API OpenAI / Anthropic / Gemini / API zgodnego z OpenAI

Dystrybuowana wersja aplikacji zawiera Python, Tk/Tcl i wymagane elementy interfejsu graficznego. Nie trzeba osobno instalować Pythona.

'''),
    ('s02_first_checks', '''【2. Co sprawdzić po uruchomieniu】
Na karcie ［Ustawienia］, w polu ［Język interfejsu］, możesz wybrać jeden z 11 języków wyświetlania. Przy pierwszym uruchomieniu używany jest język systemu operacyjnego, a jeśli nie jest obsługiwany — angielski. Jeśli aplikacja była już używana, ale język interfejsu nie został ustawiony, używany jest japoński. Zmiana zaczyna obowiązywać po ponownym uruchomieniu. To ustawienie jest niezależne od języka docelowego tłumaczenia.

W górnej części okna znajdują się dwa niezależne wskaźniki stanu LLM.

LLM do tłumaczenia:
Służy do zwykłego tłumaczenia, tłumaczenia różnic, korekty przez AI w QA, testów szybkości modeli i podobnych zadań.

LLM do wyszukiwania:
Służy do wyszukiwania nieprzetłumaczonych modów oraz rozstrzygania niejednoznacznych kandydatur podczas badania stanu tłumaczenia.
Do wyszukiwania zalecany jest lekki model o rozmiarze około 3B–8B.

Pola „Ostatnia odpowiedź LLM tłumaczenia (tylko odczyt)” i „Ostatnia odpowiedź LLM wyszukiwania (tylko odczyt)” pokazują rzeczywiste odpowiedzi otrzymane od odpowiednich LLM, bez możliwości ich edycji.
Przycisk „Otwórz pełną odpowiedź” pozwala przeczytać całą odpowiedź.

'''),
    ('s03_translate_queue', '''【3. Karta Tłumaczenie / Kolejka】
To główne miejsce wykonywania zwykłych tłumaczeń.

［Język docelowy］:
Możesz wybrać angielski, francuski, niemiecki, hiszpański, japoński, koreański, polski, portugalski (Brazylia), rosyjski, chiński uproszczony lub turecki. Każda pozycja zapisuje język docelowy wybrany w chwili dodania do kolejki. Późniejsza zmiana wyboru nie zmienia języka pozycji już dodanych.

［Dodaj］:
Dodaje pliki YAML lub foldery localization/modów. Możesz również przeciągać i upuszczać pliki i foldery.

［Usuń wybrane］:
Usuwa wyłącznie zaznaczone pozycje z kolejki. Nie usuwa plików źródłowych.

［Wyczyść wszystko］:
Opróżnia kolejkę tłumaczenia. Nie usuwa źródeł ani pamięci podręcznej.

［Rozpocznij tłumaczenie］:
Tłumaczy pozycje kolejno, od góry listy.

［Wstrzymaj］:
Wstrzymuje pracę w bezpiecznym punkcie, po zakończeniu bieżącej odpowiedzi API lub LLM.

［Zapisz i przerwij］:
Zapisuje dotychczasową pamięć podręczną i sesję, a następnie zatrzymuje pracę. Możesz ją wznowić przy następnym uruchomieniu.

［Zastosuj ustawienia do bieżącego tłumaczenia］:
Jeśli podczas tłumaczenia zmienisz model, dostawcę, URL, wielkość partii, liczbę równoległych żądań, Glosariusz, ustawienia wspólnego użycia angielskiego i chińskiego lub inne opcje, naciśnij ten przycisk, aby zastosować nowe ustawienia od następnej partii.

［Nadpisz wybrane pozycje］:
Nanosi ukończone tłumaczenie na mod źródłowy lub wykryty mod tłumaczący dla języka docelowego.
Jeśli istnieje mod tłumaczący, w oknie potwierdzenia możesz wybrać „Tak”, aby nadpisać różnice w modzie tłumaczącym, „Nie”, aby nadpisać mod źródłowy, lub „Anuluj”, aby przerwać. Przed nadpisaniem aplikacja wyraźnie wskazuje cel i tworzy kopię zapasową.

'''),
    ('s04_batch_workers', '''【4. Zalecane ustawienia partii i równoległych żądań】
Możesz wybrać jeden z trzech zalecanych zestawów ustawień.

Stabilny: partia 20 / 1 równoległe żądanie
• Mody zawierające dużo długich tekstów
• Pierwsze użycie
• Komputery z niewielkim zapasem pamięci
• Sytuacje, w których najważniejsze jest sprawdzenie poprawnego działania

Standardowy: partia 40 / 1 równoległe żądanie
• Zwykle zalecany wybór
• Równowaga między szybkością a stabilnością

Szybki: partia 60 / 2 równoległe żądania
• Gdy Ollama lub LM Studio mogą przetwarzać dwa żądania jednocześnie
• Gdy dostępna jest wystarczająca ilość RAM/VRAM

Wskazówki:
• Partia 1–60: zwykły zakres
• Partia powyżej 80: przy długich tekstach częściej występują pominięcia i przekroczenia czasu oczekiwania
• Partia powyżej 120: niezalecana
• 1 równoległe żądanie: największa stabilność
• 2 równoległe żądania: zalecane, gdy na serwerze włączono przetwarzanie równoległe
• 3 lub więcej równoległych żądań: lokalny LLM może częściej powodować przeciążenie pamięci, kolejki oczekiwania i przekroczenia czasu oczekiwania

W przypadku API w chmurze przede wszystkim przestrzegaj limitów częstotliwości żądań ustalonych przez usługę.

'''),
    ('s05_llm_settings', '''【5. Ustawienia LLM i tłumaczenia】
Dostawca:
Możesz wybrać Ollama / LM Studio / OpenAI / Anthropic / Gemini / OpenAI Compatible.

URL:
Domyślnie dla Ollama: http://localhost:11434
Domyślnie dla LM Studio: http://localhost:1234/v1
Dla usług w chmurze zwykle ustawiany automatycznie.

Model:
Po sprawdzeniu połączenia wybierz model z listy dostępnych modeli.

Klucz API:
Służy do API w chmurze. Nie jest zapisywany w pliku ustawień aplikacji.

Zestaw ustawień:
Określa zasady promptu tłumaczenia dla danej gry, na przykład CK3.

Tłumaczenie oparte na chińskim:
Po dodaniu pliku YAML w chińskim uproszczonym na karcie ［Tłumaczenie oparte na chińskim］ tłumaczenie opiera się przede wszystkim na chińskim słownictwie zapisanym znakami, terminologii instytucjonalnej i terminach specyficznych dla chińskiego. Plik angielski nie jest potrzebny.
Jako język docelowy możesz wybrać japoński lub koreański. Koreański jest przeznaczony do modów osadzonych w Azji Wschodniej, zawierających wiele nazw urzędów i instytucji wywodzących się z chińskiego. W przypadku zachodnich tytułów i terminologii religijnej zwykłe tłumaczenie z angielskiego jest zazwyczaj bliższe oficjalnemu tłumaczeniu.

Naprawa nieprzetłumaczonych fragmentów istniejących tłumaczeń japońskich:
Jeśli w l_japanese pozostał angielski lub inny język, do naprawy wybierane są tylko te fragmenty.

［Po tłumaczeniu utwórz kopię zapasową, wykonaj QA i napraw błędy］:
Po tłumaczeniu sprawdza nieprzetłumaczone fragmenty i uszkodzoną składnię Paradox zgodnie z językiem docelowym.

Obsługa spacji o połowie szerokości w chińskim uproszczonym:
Usuwa tylko spacje o połowie szerokości między chińskimi znakami a interpunkcją lub nawiasami. Zachowuje odstępy między słowami w oznaczeniach modeli i nazwach wyposażenia.

'''),
    ('s06_cache', '''【6. Pamięć podręczna】
Każde tłumaczenie ma niezależną pamięć podręczną. Dane są rozdzielone według języka docelowego, więc tłumaczenia tego samego moda na różne języki nie mieszają się.
Także po aktualizacji tego samego moda aplikacja rozpoznaje wcześniejszą pamięć podręczną i nie tłumaczy ponownie niezmienionych tekstów.

［Zobacz pamięć podręczną］:
Pokazuje zawartość pamięci podręcznej zaznaczonej pozycji kolejki, liczbę wpisów i miejsce zapisu.

［Dodaj pamięć podręczną］:
Łączy inny plik translate_cache.json z bieżącym tłumaczeniem.

Aktualizacja różnic:
Porównuje source_manifest.json poprzedniego źródła z aktualnym źródłem i ponownie tłumaczy na język docelowy tylko nowe lub zmienione fragmenty.

'''),
    ('s07_review', '''【7. Karta QA / Porównanie i edycja】
Porównuje źródło z tłumaczeniem na język docelowy i wyświetla problemy w strukturze hierarchicznej.
Pliki YAML można wczytywać przez przeciąganie i upuszczanie.

Główne kontrole:
• Nieprzetłumaczone teksty
• Brakujące klucze
• Niezgodne symbole zastępcze
• Uszkodzenia [Character...] / $VALUE$ / kodów kolorów § itp.
• Znaki nieodpowiednie dla języka docelowego: znaki chińskie, kana, hangul lub cyrylica
• Wartości identyczne ze źródłem i pozostałości angielskiego; nazwy własne, oznaczenia modeli itp. mogą być wyłączone z kontroli
• Podejrzenia literówek lub pominiętych znaków, tylko dla japońskiego
• Niespójności nawiasów lub interpunkcji

Po wybraniu wiersza z problemem możesz zobaczyć źródło i tłumaczenie obok siebie.
Pole ［Tłumaczenie (do edycji)］ możesz bezpośrednio zmienić i zapisać. Niektóre przypadki nieodpowiednich znaków, wartości identycznych ze źródłem lub pozostałości angielskiego są pokazywane jako uwagi. Sprawdź treść i wprowadź odpowiednie poprawki.
Korekta przez AI używa bieżących ustawień LLM do tłumaczenia. Po ich zmianie naciśnij ［Zastosuj bieżące ustawienia tłumaczenia］.

'''),
    ('s08_diff', '''【8. Karta Analiza różnic】
Porównuje źródło z tłumaczeniem na język docelowy, zestawiając je obok siebie klucz po kluczu.
Obsługuje również przeciąganie i upuszczanie.

Przykłady klasyfikacji:
• Brak: klucz istnieje w źródle, ale nie w tłumaczeniu
• Nieprzetłumaczone: kontrola dla języka docelowego uznaje tekst za nieprzetłumaczony, na przykład gdy pozostał taki sam jak źródło
• Tylko w języku docelowym: klucz istnieje wyłącznie w tłumaczeniu; interfejs wyświetla nazwę języka
• Poprawne powiązanie: klucz ma prawidłowy odpowiednik

［Tłumacz wybrane pozycje］:
Tłumaczy tylko jeden zaznaczony klucz.

［Tłumacz wszystkie brakujące i nieprzetłumaczone klucze］:
Wysyła do LLM zbiorczo tylko problematyczne fragmenty.

Tłumaczenie różnic również używa bieżących ustawień LLM do tłumaczenia.

'''),
    ('s09_search', '''【9. Karta Wyszukiwanie tłumaczeń】
Wyszukuje w wielu japońskich plikach YAML lub folderach i pozwala poprawiać tłumaczenia bezpośrednio z wyników wyszukiwania.

Zakres wyszukiwania:
• Nazwy plików
• Klucze lokalizacji
• Tekst japoński

Po wybraniu wyniku możesz edytować bieżące tłumaczenie i zapisać je w źródłowym YAML przyciskiem ［Zapisz to japońskie tłumaczenie］.

'''),
    ('s10_glossary', '''【10. Karta Glosariusz】
Wybierz język docelowy w polu ［Język］, aby zapisywać ustalone tłumaczenia osobno dla każdego języka. Tłumaczenie, QA i analiza różnic korzystają z Glosariusza odpowiedniego języka docelowego.
Przykład w języku japońskim: Grand Campaign → 開辺

［Importuj z gry podstawowej］, import z przetłumaczonych plików YAML i modów oraz ［Utwórz Glosariusz automatycznie］ na poszczególnych kartach roboczych są dostępne dla wszystkich 11 języków.

Do promptu LLM trafiają tylko te terminy, których tekst źródłowy występuje w danej partii tłumaczenia.
Jeśli zmienisz Glosariusz w trakcie pracy, zastosowanie ustawień do bieżącego tłumaczenia pozwoli uwzględnić zmiany od następnej partii.

'''),
    ('s11_models', '''【11. Karta Modele / Połączenie】
Służy do sprawdzania połączenia, przeglądania listy modeli, testowania szybkości i zarządzania profilami.

Testuj szybkość bieżącego LLM:
Mierzy wydajność jednego aktualnie wybranego modelu.

Porównaj wybrane modele:
Wybierz maksymalnie pięć modeli, aby porównać średni czas przetwarzania, tokens/s i odsetek niepowodzeń.

Profile modeli:
Możesz wspólnie zapisać dostawcę, URL, model, wielkość partii, liczbę równoległych żądań, zestaw ustawień gry i inne opcje.
Profile można nie tylko dodawać, ale też usuwać.

Ostatnio używany dostawca, URL i model do tłumaczenia oraz wyszukiwania są automatycznie przywracane przy następnym uruchomieniu. Klucze API nie są zapisywane.

'''),
    ('s12_monitor', '''【12. Karta Monitor nieprzetłumaczonych】
Stale monitoruje w trybie tylko do odczytu lokalizacje modów zarejestrowane na karcie Stan tłumaczenia. Nie tłumaczy automatycznie.

Monitorowane lokalizacje:
Po wybraniu gry lub lokalizacji modów na karcie ［Stan tłumaczenia］ i wykonaniu ［Zbadaj mody w wybranych lokalizacjach］ ta lokalizacja jest również rejestrowana do monitorowania.

LLM przeznaczony do wyszukiwania:
Możesz wskazać inny model niż do zwykłego tłumaczenia. Zalecany jest lekki model o rozmiarze około 3B–8B.

［Rozpocznij ciągłe monitorowanie］:
Po rozpoczęciu monitorowania ten sam przycisk zmienia nazwę na ［Zatrzymaj ciągłe monitorowanie］, a pole stanu pokazuje „● Ciągłe monitorowanie”.

［Zbadaj ponownie］:
Ponownie bada stan tłumaczenia modów w zarejestrowanych monitorowanych lokalizacjach.

Podczas monitorowania aplikacja sprawdza czas modyfikacji i rozmiar plików YAML, a analizuje tylko elementy, które się zmieniły. Do lekkiego LLM wysyła jedynie niejednoznacznych kandydatów.

'''),
    ('s13_status', '''【13. Karta Stan tłumaczenia】
Ta karta skupia automatyczne wykrywanie gier i lokalizacji modów, wybór miejsc do zbadania oraz badanie stanu tłumaczenia modów.
Możesz zaznaczyć kilka lokalizacji i wykonać ［Zbadaj mody w wybranych lokalizacjach］. Wyniki są buforowane osobno dla języka docelowego, a ponownie badane są tylko zmienione mody. Po aktualizacji do v0.13 wykonaj badanie ponownie, ponieważ zmieniła się metoda klasyfikacji.

Przykładowe wyświetlane stany:
• Nieprzetłumaczony
• Ma braki
• Tłumaczenie z innego moda z brakami
• W pełni przetłumaczony przez inny mod
• Przetłumaczony

Wykrywanie modów tłumaczących:
Nawet jeśli mod źródłowy nie zawiera języka docelowego, inny mod z tej samej gry zostaje uznany za kandydata na mod tłumaczący, jeśli zawiera klucze tłumaczenia odpowiadające kluczom źródłowym.
Aplikacja pokazuje też, czy tłumaczenie jest kompletne, czy ma braki. Jeśli językiem docelowym jest angielski, zewnętrzne mody tłumaczące nie są porównywane, ponieważ wiele modów już zawiera angielski.

Karta ［Pełna diagnostyka］ również diagnozuje i ustala powiązania dla języka docelowego. Powiązania dla języków innych niż japoński sprawdzono na niewielkiej ilości rzeczywistych danych, dlatego przed nadpisaniem upewnij się, że są poprawne.

Wyszukiwanie:
Wpisz nazwę moda lub stan, aby zawęzić listę już sklasyfikowanych wyników.

Dodawanie do kolejki:
Jeśli zaznaczysz kilka modów, możesz dodać wszystkie zaznaczone pozycje do zwykłej kolejki tłumaczenia. Do kolejki opartej na chińskim trafiają wszystkie zaznaczone mody zawierające chińską lokalizację.

Wykluczanie zaznaczonych modów i dodawanie pozostałych do kolejki:
Możesz wykluczyć tylko zaznaczone mody i zbiorczo dodać pozostałe do zwykłej kolejki albo dodać do kolejki opartej na chińskim tylko mody zawierające chińską lokalizację.

Nadpisywanie moda tłumaczącego:
Jeśli istnieje mod tłumaczący dla języka docelowego, brakujące fragmenty są nanoszone jako różnice na ten mod, a nie na mod źródłowy.
Istniejące tłumaczenia zostają zachowane; dodawane lub aktualizowane są tylko brakujące i nieprzetłumaczone klucze.
Przed wykonaniem aplikacja pokazuje nazwę i ścieżkę moda docelowego, tworzy kopię zapasową i wymaga podwójnego potwierdzenia.

［Tłumacz tylko różnice］:
Tłumaczy tylko nowe lub zmienione klucze oraz brakujące tłumaczenia dla języka docelowego.

'''),
    ('s14_data_folder', '''【14. Automatycznie generowane pliki i miejsce zapisu】
Wszystkie automatycznie generowane pliki są gromadzone w jednym folderze.

Domyślna lokalizacja:
書類/Documents/Paradox Localization Translator/

Struktura:
Paradox Localization Translator/
├── 翻訳結果/
├── キャッシュ/
├── バックアップ/
├── ログ/
├── 作業データ/
└── 設定/

Foldery wyjściowe wyników tłumaczenia również są rozdzielone według języka docelowego. Nazwy kończą się na „…_japanese”, „…_french” itp., a w środku zapisywane są pliki YAML poszczególnych języków.

Przy uruchomieniu aplikacja wykrywa ParadoxLocalizationTranslator_Data obok pliku wykonywalnego starszej wersji i przenosi potrzebne dane do tej lokalizacji bez niszczenia istniejących danych. Stare ścieżki bezwzględne zapisane w wznawianych sesjach również są reinterpretowane tak, aby wskazywały aktualną lokalizację.

Na karcie ［Ustawienia］ przyciskiem ［Zmień lokalizację］ możesz wybrać inny dysk SSD lub dowolny folder. Możesz również skopiować istniejące dane podczas migracji.

'''),
    ('s15_logs_diagnostics', '''【15. Dzienniki błędów i diagnostyka】
Wyjątki aplikacji, błędy połączenia z LLM, błędy analizy YAML, błędy zapisu i podobne problemy są zapisywane w dziennikach dziennych.

［Otwórz dziennik błędów］:
Otwiera folder dzienników.

［Zbierz dzienniki diagnostyczne］:
Zbiera informacje o systemie operacyjnym, wersji aplikacji, modelu, dzienniki błędów i inne dane w diagnostycznym pliku ZIP. Nie zawiera kluczy API ani tekstów tłumaczeń.

'''),
    ('s16_close_button', '''【16. Co się dzieje po naciśnięciu przycisku ×】
Domyślnie po naciśnięciu przycisku × w prawym lub lewym górnym rogu pojawia się potwierdzenie:

„Czy chcesz zminimalizować okno, czy zakończyć aplikację?”

Minimalizuj:
• Minimalizuje tylko okno
• Nie zatrzymuje tłumaczenia, wyszukiwania ani pracy LLM

Zakończ:
• Jeśli kolejka tłumaczenia zawiera nieukończone pozycje, zapisuje sesję
• Poprawnie ukończona kolejka nie jest zachowywana jako sesja do przywrócenia
• Jeśli przy następnym uruchomieniu odmówisz przywrócenia sesji, zostanie ona odrzucona i nie pojawi się ponownie
• Przed zakończeniem aplikacji wysyła żądanie bezpiecznego zatrzymania LLM i tłumaczenia

Jeśli później chcesz zmienić to zachowanie:
W ［Ustawienia］ → ［Działanie przycisku × okna］ możesz wybrać:
• Pytaj za każdym razem
• Minimalizuj
• Zakończ

'''),
    ('s17_safety', '''【17. Zasady bezpiecznego korzystania】
• Przed bezpośrednim nadpisaniem moda źródłowego zawsze przeczytaj ostrzeżenie.
• Aktualizacje Steam Workshop mogą nadpisać ręczne zmiany.
• Przy bezpośrednim nadpisaniu powstaje automatyczna kopia zapasowa.
• Przy dużych tłumaczeniach zacznij od ustawień standardowych (40 / 1).
• Mały model LLM do wyszukiwania ogranicza obciążenie komputera.
• Klucze API usług w chmurze nie są zapisywane.
• W razie problemu utworzenie diagnostycznego ZIP z dziennikami ułatwia ustalenie przyczyny.

'''),
    ('s18_common_uses', '''【18. Typowe zastosowania】
Tłumaczenie nowego moda:
1. Wybierz ［Język docelowy］, a następnie przeciągnij mod
2. Sprawdź model do tłumaczenia
3. Rozpocznij tłumaczenie
4. QA
5. W razie potrzeby wyszukaj i popraw tłumaczenia
6. Nadpisz różnice w modzie ukończoną wersją

Naprawa braków w istniejącym modzie tłumaczącym:
1. Wybierz język docelowy i wykonaj ［Zbadaj mody w wybranych lokalizacjach］
2. Na karcie Stan tłumaczenia sprawdź „Tłumaczenie z innego moda z brakami”
3. Przetłumacz odpowiedni mod
4. W trakcie tłumaczenia możesz użyć ［Wstrzymaj］ lub ［Zapisz i przerwij］
5. Sprawdź ukończone pliki przyciskiem ［Otwórz wyjście］
6. Naciśnij ［Nadpisz wybrane pozycje］ i, jeśli wykryto mod tłumaczący dla języka docelowego, wybierz cel nadpisania w oknie potwierdzenia

Tłumaczenie dodatkowych treści tylko po aktualizacji moda:
1. Wybierz język docelowy i ponownie dodaj zaktualizowany mod
2. Poprzednia pamięć podręczna i migawka źródła są rozpoznawane automatycznie
3. Sprawdź aktualizację różnic
4. Przetłumacz tylko nowe lub zmienione klucze

Ręczne poprawianie terminów w japońskim tłumaczeniu:
1. Otwórz kartę Wyszukiwanie tłumaczeń
2. Wyszukaj klucz lub tekst japoński
3. Wybierz wynik
4. Edytuj tłumaczenie i zapisz

Karta Pomoc zawiera instrukcję wbudowaną w aplikację. Nawet użytkownik, który otrzymał tylko dystrybuowaną wersję, może poznać zarówno podstawowe operacje, jak i zaawansowane funkcje bez otwierania zewnętrznego README.

'''),
    ('unofficial', '''【To nieoficjalne narzędzie】
To nieoficjalne narzędzie rozwijane przez osobę prywatną, niezwiązane z firmą Paradox Interactive. Nazwy poszczególnych gier są znakami towarowymi ich właścicieli.
Narzędzie jest bezpłatne, a wszystkie jego funkcje są dostępne dla każdego (licencja MIT).

'''),
    ('publishing', '''【Zalecenia dotyczące publikowania przetłumaczonych modów】
• Uzyskaj zgodę autora moda źródłowego. Przy publikowaniu tłumaczenia cudzego moda w Steam Workshop lub podobnych serwisach przyjętą praktyką jest skontaktowanie się z pierwotnym autorem i poproszenie o zgodę.
• Udostępniaj tłumaczenie bezpłatnie. Warunki korzystania z Paradox Interactive nie pozwalają umieszczać modów ani innych treści tworzonych przez użytkowników za barierą płatnego dostępu; dozwolone jest przyjmowanie darowizn za poświęcony czas.
• Jeśli mod zawiera tłumaczenie maszynowe, zaznacz to w opisie, aby użytkownicy mogli świadomie ocenić jego przydatność.
'''),
]
SOURCE_HASHES = {'intro': 'dc0e64262c52', 's00_overview': '57e3f61ee91f', 's01_requirements': 'f6c2c4898718', 's02_first_checks': 'ad4282fa15f0', 's03_translate_queue': '38ceaa862083', 's04_batch_workers': '0ad57aad8db6', 's05_llm_settings': 'f50d5592d09b', 's06_cache': '053b8fd863bd', 's07_review': 'effd2b2c02b3', 's08_diff': '047b909759cf', 's09_search': '331764e4826a', 's10_glossary': 'f3d3a966a4a3', 's11_models': '101883be6b22', 's12_monitor': 'b317e0f4bc37', 's13_status': '7273a7c98ae2', 's14_data_folder': '5e1b34c6fa85', 's15_logs_diagnostics': '78e7512742d6', 's16_close_button': 'bf95d994339e', 's17_safety': 'a3ae50ab1c28', 's18_common_uses': '054ef2c9de07', 'unofficial': '4f1fb69113b7', 'publishing': '13a1da9a3844'}
