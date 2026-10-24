"""使い方タブの説明書（french）。節ごとに持つ（第3段 5-2 章）。"""

HELP_TITLE = "Paradox Localization Translator — Mode d’emploi"

STALE_NOTICE = "（Cette section n’a pas encore été mise à jour pour la dernière version. Certains passages sont obsolètes. Consultez la version anglaise pour les informations les plus récentes.）"

HELP_SECTIONS = [
    ('intro', 'Paradox Localization Translator — Guide détaillé\n\n'),
    ('s00_overview', '''【0. Ce que permet cette application】
Cet outil intégré traduit les fichiers YAML de localisation des jeux Paradox Interactive dans la langue cible choisie, à l’aide d’un LLM local ou d’une API cloud.
Au-delà de la traduction en masse, il permet de réparer les passages non traduits, de mettre à jour les traductions par différences, d’effectuer un QA, de rechercher et corriger des traductions, d’analyser l’état de traduction des mods, de reporter les différences dans un mod de traduction existant et de gérer les caches.

Principaux jeux pris en charge :
• Crusader Kings III
• Victoria 3
• Hearts of Iron IV
• Stellaris
• Europa Universalis V

'''),
    ('s01_requirements', '''【1. Ce qu’il vous faut pour commencer】
Pour utiliser un LLM local :
• Ollama ou LM Studio
• Un modèle LLM pour la traduction

Pour utiliser une API cloud :
• Une clé API OpenAI / Anthropic / Gemini / d’une API compatible OpenAI

La version distribuée de l’application intègre Python, Tk/Tcl et les composants d’interface nécessaires. Vous n’avez donc pas besoin d’installer Python séparément.

'''),
    ('s02_first_checks', '''【2. Les premiers points à vérifier au démarrage】
Dans l’onglet ［Paramètres］, ［Langue d’affichage］ permet de choisir parmi 11 langues d’interface. Au premier lancement, la langue du système est utilisée, ou l’anglais si elle n’est pas prise en charge. Pour les utilisateurs d’une version antérieure qui n’ont pas encore défini la langue d’affichage, le japonais est utilisé. Le changement prend effet après redémarrage. Ce réglage est indépendant de la langue cible de traduction.

En haut de la fenêtre, deux indicateurs distincts affichent l’état des LLM.

LLM de traduction :
Il sert à la traduction normale, à la traduction des différences, à la correction par IA du QA, aux tests de vitesse des modèles, etc.

LLM d’exploration :
Il sert à rechercher les mods non traduits et à départager les candidats ambigus lors de l’analyse de l’état de traduction.
Pour l’exploration, un modèle léger d’environ 3B à 8B est recommandé.

Les champs « Dernière réponse du LLM de traduction (lecture seule) » et « Dernière réponse du LLM d’exploration (lecture seule) » affichent, sans possibilité de modification, les réponses réellement reçues des LLM.
« Ouvrir la réponse complète » permet de consulter la réponse intégrale.

'''),
    ('s03_translate_queue', '''【3. Onglet Traduction / File d’attente】
C’est ici que se déroule la traduction normale.

［Langue cible］ :
Vous pouvez choisir l’anglais, le français, l’allemand, l’espagnol, le japonais, le coréen, le polonais, le portugais (Brésil), le russe, le chinois simplifié ou le turc. Chaque élément conserve la langue cible choisie lors de son ajout à la file d’attente. Modifier ensuite la sélection ne change pas la langue cible des éléments déjà ajoutés.

［Ajouter］ :
Ajoute des fichiers YAML ou des dossiers localization/mod. Le glisser-déposer est également disponible.

［Supprimer la sélection］ :
Supprime uniquement les éléments sélectionnés de la file d’attente, sans supprimer les fichiers sources.

［Tout effacer］ :
Vide la file d’attente de traduction, sans supprimer les sources ni les caches.

［Démarrer la traduction］ :
Traduit les éléments dans l’ordre, en commençant par le haut.

［Pause］ :
Suspend le traitement à un point sûr, une fois la réponse API/LLM en cours terminée.

［Enregistrer et interrompre］ :
Enregistre le cache et la session dans leur état actuel, puis arrête le traitement. Vous pouvez reprendre au prochain lancement.

［Appliquer les paramètres à la traduction actuelle］ :
Si vous modifiez en cours de traduction le modèle, le fournisseur, l’URL, la taille des lots, le parallélisme, le Glossaire, les réglages combinant anglais et chinois, etc., ce bouton applique les nouveaux paramètres à partir du lot suivant.

［Écraser les éléments sélectionnés］ :
Reporte la traduction terminée dans le mod d’origine ou dans le mod de traduction détecté pour la langue cible.
Si un mod de traduction existe, « Oui » dans la fenêtre de confirmation écrit les différences dans ce mod de traduction, « Non » écrit dans le mod d’origine et « Annuler » abandonne l’opération. La destination est explicitement indiquée et une sauvegarde est créée avant l’écriture.

'''),
    ('s04_batch_workers', '''【4. Réglages recommandés pour les lots / le parallélisme】
Trois préréglages recommandés sont disponibles.

Stabilité : lots de 20 / parallélisme 1
• Mods contenant beaucoup de textes longs
• Première utilisation
• Environnements disposant de peu de mémoire libre
• Lorsque vous souhaitez d’abord vérifier le bon fonctionnement

Standard : lots de 40 / parallélisme 1
• Recommandé dans les cas habituels
• Équilibre entre vitesse et stabilité

Rapidité : lots de 60 / parallélisme 2
• Si Ollama / LM Studio peut traiter deux requêtes simultanément
• Si vous disposez de suffisamment de RAM/VRAM

Repères :
• Lots de 1 à 60 : plage habituelle
• Au-delà de 80 : les textes longs risquent davantage de subir des omissions ou des dépassements de délai
• Au-delà de 120 : déconseillé
• Parallélisme 1 : le plus stable
• Parallélisme 2 : recommandé si le traitement parallèle est activé côté serveur
• Parallélisme 3 ou plus : avec un LLM local, risque accru de saturation mémoire, de files d’attente et de dépassements de délai

Avec une API cloud, respectez en priorité les limites de débit du service.

'''),
    ('s05_llm_settings', '''【5. LLM / Paramètres de traduction】
Fournisseur :
Vous pouvez choisir Ollama / LM Studio / OpenAI / Anthropic / Gemini / OpenAI Compatible.

URL :
Ollama par défaut : http://localhost:11434
LM Studio par défaut : http://localhost:1234/v1
Pour le cloud, l’URL est généralement définie automatiquement.

Modèle :
Après avoir vérifié la connexion, choisissez dans la liste des modèles disponibles.

Clé API :
Elle sert aux API cloud et n’est pas enregistrée dans le fichier de paramètres de l’application.

Profil de jeu :
Définit les orientations du prompt de traduction propres à chaque jeu, comme CK3.

Traduction basée sur le chinois :
Si vous ajoutez des YAML en chinois simplifié dans l’onglet ［Traduction basée sur le chinois］, le vocabulaire en caractères chinois, les termes institutionnels et les termes spécifiques du chinois servent de référence principale pour la traduction. Aucun fichier anglais n’est nécessaire.
Les langues cibles disponibles sont le japonais et le coréen. Le coréen convient aux mods portant sur l’Asie de l’Est, notamment ceux riches en termes d’origine chinoise désignant des fonctions et des institutions. Pour les titres occidentaux et les termes religieux, la traduction normale depuis l’anglais est plus proche des traductions officielles.

Réparer les passages non traduits dans une traduction japonaise existante :
Si de l’anglais ou d’autres langues subsistent dans l_japanese, seuls ces passages sont ciblés pour réparation.

［Sauvegarder, exécuter le QA et corriger les erreurs après traduction］ :
Après la traduction, vérifie les passages non traduits et les altérations de la syntaxe Paradox en fonction de la langue cible.

Traitement des espaces demi-chasse en chinois simplifié :
Supprime uniquement les espaces demi-chasse entre les caractères chinois et les signes de ponctuation ou les parenthèses. Les espaces séparant les mots dans les références de modèles et les noms d’équipements sont conservés.

'''),
    ('s06_cache', '''【6. Cache】
Chaque traduction dispose de son propre cache. Les caches sont séparés par langue cible : traduire le même mod dans une autre langue ne mélange donc pas les données.
Lors d’une mise à jour du même mod, le cache précédent est également retrouvé afin de ne pas retraduire les textes inchangés.

［Voir le cache］ :
Affiche le contenu du cache, le nombre d’entrées et l’emplacement de stockage de l’élément sélectionné dans la file d’attente.

［Ajouter un cache］ :
Intègre un autre translate_cache.json à la traduction actuelle.

Mise à jour par différences :
Compare le source_manifest.json des textes sources précédents aux sources actuelles et ne retraduit que les parties nouvelles ou modifiées pour la langue cible.

'''),
    ('s07_review', '''【7. Onglet QA / Comparaison et édition】
Compare les sources aux traductions dans la langue cible et présente les problèmes sous forme hiérarchique.
Vous pouvez charger des YAML par glisser-déposer.

Principales vérifications :
• Passages non traduits
• Clés manquantes
• Incohérences de variables de substitution
• Altérations de [Character...] / $VALUE$ / §codes couleur, etc.
• Présence de types de caractères inappropriés pour la langue cible (caractères chinois, kana, hangul, caractères cyrilliques)
• Valeurs identiques aux sources et restes d’anglais (les noms propres et les références de modèles peuvent être exclus)
• Erreurs typographiques possibles (japonais uniquement)
• Incohérences de parenthèses et de ponctuation

Sélectionner une ligne signalée affiche la source et la traduction côte à côte.
Vous pouvez modifier directement le champ ［Traduction (modifiable)］ et enregistrer. Certains cas de mélange de caractères, de valeurs identiques aux sources ou de restes d’anglais sont présentés comme des remarques. Vérifiez le contenu avant de le corriger.
La correction par IA utilise les paramètres actuels du LLM de traduction. Après avoir modifié les paramètres, cliquez sur ［Appliquer les paramètres de traduction actuels］.

'''),
    ('s08_diff', '''【8. Onglet Analyse des écarts】
Compare les sources et les traductions dans la langue cible, clé par clé, en les affichant face à face.
Le glisser-déposer est également pris en charge.

Exemples de résultats :
• Manquant : présent dans la source, mais absent de la traduction
• Non traduit : considéré comme non traduit selon les critères de la langue cible, par exemple si le texte source est resté inchangé
• Uniquement dans la langue cible : la clé n’existe que du côté de la traduction (le nom de la langue est affiché à l’écran)
• Correspondance : les entrées correspondent correctement

［Traduire la sélection］ :
Traduit uniquement la clé sélectionnée.

［Traduire toutes les clés manquantes et non traduites］ :
Envoie au LLM, en une opération groupée, uniquement les entrées problématiques.

La traduction des différences utilise elle aussi les paramètres actuels du LLM de traduction.

'''),
    ('s09_search', '''【9. Onglet Recherche de traductions】
Recherche dans plusieurs YAML/dossiers japonais et permet de corriger les traductions directement depuis les résultats.

Éléments recherchés :
• Noms de fichiers
• Clés de localisation
• Texte japonais

Sélectionnez un résultat pour modifier la traduction actuelle, puis cliquez sur ［Enregistrer cette traduction japonaise］ pour reporter la modification dans le YAML d’origine.

'''),
    ('s10_glossary', '''【10. Onglet Glossaire】
Choisissez la langue cible dans ［Langue］ pour enregistrer des traductions fixes propres à chaque langue. La traduction, le QA et l’analyse des écarts utilisent le Glossaire de la langue cible concernée.
Exemple (japonais) : Grand Campaign → 開辺

［Importer depuis le jeu de base］, l’importation depuis des YAML ou des mods déjà traduits, ainsi que ［Créer le Glossaire automatiquement］ dans les différents onglets de travail sont disponibles pour les 11 langues.

Lorsque le texte source correspondant figure dans un lot de traduction, seuls les termes concernés sont transmis au prompt du LLM.
Si vous modifiez le Glossaire en cours de traitement, appliquez les paramètres à la traduction actuelle pour que les changements prennent effet à partir du lot suivant.

'''),
    ('s11_models', '''【11. Onglet Modèles / Connexion】
Permet de vérifier la connexion, de consulter les modèles, de tester leur vitesse et de gérer les profils.

Tester la vitesse du LLM actuel :
Mesure les performances du seul modèle actuellement sélectionné.

Comparer les modèles sélectionnés :
Sélectionnez jusqu’à 5 modèles pour comparer le temps de traitement moyen, les tokens/s et le taux d’échec.

Profils de modèles :
Vous pouvez enregistrer ensemble le fournisseur, l’URL, le modèle, la taille des lots, le parallélisme, le préréglage de jeu, etc.
Les profils peuvent être supprimés aussi bien qu’ajoutés.

Le fournisseur, l’URL et le modèle utilisés en dernier pour la traduction et l’exploration sont automatiquement restaurés au prochain lancement. Les clés API ne sont pas enregistrées.

'''),
    ('s12_monitor', '''【12. Onglet Surveillance des non-traduits】
Surveille en continu, en lecture seule, les emplacements de mods enregistrés dans l’onglet État de la traduction. Aucune traduction automatique n’est effectuée.

Emplacements surveillés :
Dans l’onglet ［État de la traduction］, sélectionnez un jeu/emplacement de mods et lancez ［Analyser les mods aux emplacements sélectionnés］. Cet emplacement est également enregistré comme cible de surveillance.

LLM réservé à l’exploration :
Vous pouvez définir un modèle différent de celui de la traduction normale. Un modèle léger d’environ 3B à 8B est recommandé.

［Démarrer la surveillance continue］ :
Après le démarrage, le même bouton devient ［Arrêter la surveillance continue］ et le champ d’état affiche « ● Surveillance continue ».

［Relancer l’analyse］ :
Analyse de nouveau l’état de traduction des mods aux emplacements de surveillance déjà enregistrés.

Pendant la surveillance, l’application vérifie la date de modification et la taille des YAML et n’analyse que les éléments modifiés. Seuls les candidats ambigus sont envoyés au LLM léger.

'''),
    ('s13_status', '''【13. Onglet État de la traduction】
Cet onglet regroupe la détection automatique des emplacements de jeux/mods, la sélection des emplacements à analyser et l’analyse de l’état de traduction des mods.
Vous pouvez sélectionner plusieurs emplacements et lancer ［Analyser les mods aux emplacements sélectionnés］. Les résultats sont mis en cache par langue cible et seuls les mods modifiés sont réanalysés. Après le passage à v0.13, relancez l’analyse, car la méthode de classification a changé.

Exemples d’affichage :
• Non traduit
• Entrées manquantes
• Traduit par un autre mod, avec omissions
• Entièrement traduit par un autre mod
• Traduit

Détection des mods de traduction :
Même si le mod d’origine ne contient pas la langue cible, un autre mod du même jeu est considéré comme candidat à la traduction s’il possède des clés traduites correspondant aux clés sources.
L’application indique également si la traduction est complète ou comporte des entrées manquantes. Lorsque la langue cible est l’anglais, les mods de traduction externes ne sont pas comparés, car de nombreux mods contiennent déjà de l’anglais.

L’onglet ［Diagnostic complet］ effectue lui aussi ses diagnostics et ses associations selon la langue cible. Les associations pour les langues autres que le japonais ont été moins vérifiées sur des données réelles : contrôlez donc les correspondances avant toute écriture.

Recherche :
Saisissez un nom de mod ou un état pour filtrer la liste des résultats déjà classés.

Ajout à la file d’attente :
Vous pouvez ajouter tous les mods sélectionnés à la file d’attente de traduction normale. Dans la file d’attente de traduction basée sur le chinois, tous les mods sélectionnés possédant une localisation chinoise sont ajoutés.

Ajout à la file d’attente en excluant les mods sélectionnés :
Vous pouvez exclure uniquement les mods sélectionnés et ajouter tous les autres à la file d’attente normale, ou ajouter uniquement ceux possédant une localisation chinoise à la file d’attente de traduction basée sur le chinois.

Écriture dans un mod de traduction :
Si un mod de traduction existe déjà pour la langue cible, les traductions manquantes sont reportées par différences dans ce mod, et non dans le mod d’origine.
Les traductions existantes sont conservées ; seules les clés manquantes ou non traduites sont ajoutées ou mises à jour.
Avant l’opération, le nom et le chemin du mod de destination sont affichés. Une sauvegarde et une double confirmation sont prévues.

［Traduire uniquement les écarts］ :
Traduit uniquement les clés nouvelles ou modifiées et les traductions manquantes pour la langue cible.

'''),
    ('s14_data_folder', '''【14. Fichiers générés automatiquement et emplacement de stockage】
Tous les fichiers générés automatiquement sont regroupés dans un seul dossier.

Par défaut :
書類/Documents/Paradox Localization Translator/

Structure :
Paradox Localization Translator/
├── 翻訳結果/
├── キャッシュ/
├── バックアップ/
├── ログ/
├── 作業データ/
└── 設定/

Les dossiers de sortie des traductions sont également séparés par langue cible. Leur nom se termine par « …_japanese », « …_french », etc., et chaque dossier contient les YAML de la langue correspondante.

Au démarrage, l’application détecte le dossier ParadoxLocalizationTranslator_Data situé à côté de l’exécutable d’une ancienne version et transfère les données nécessaires vers cet emplacement sans détruire les données existantes. Les anciens chemins absolus des sessions à reprendre sont également réinterprétés pour correspondre à l’emplacement actuel.

Dans l’onglet ［Paramètres］, ［Changer l’emplacement］ permet de choisir un autre SSD ou un dossier de votre choix. Vous pouvez également migrer les données existantes en les copiant.

'''),
    ('s15_logs_diagnostics', '''【15. Journaux d’erreurs / Diagnostic】
Les exceptions de l’application, les échecs de connexion au LLM, d’analyse YAML ou d’écriture, etc., sont enregistrés dans des journaux quotidiens.

［Ouvrir les journaux d’erreurs］ :
Ouvre le dossier des journaux.

［Collecter les journaux de diagnostic］ :
Regroupe le système d’exploitation, la version de l’application, les informations sur les modèles, les journaux d’erreurs, etc., dans un ZIP de diagnostic. Les clés API et les textes traduits n’y figurent pas.

'''),
    ('s16_close_button', '''【16. Lorsque vous cliquez sur le bouton ×】
Par défaut, cliquer sur le bouton × en haut à droite ou à gauche affiche la confirmation suivante.

« Réduire la fenêtre ou quitter l’application ? »

Réduire :
• Seule la fenêtre est réduite
• La traduction, l’exploration et les traitements LLM continuent

Quitter :
• Si la file d’attente contient des traductions inachevées, la session est enregistrée
• Une file d’attente entièrement terminée avec succès n’est pas conservée comme session à restaurer
• Si vous refusez de restaurer une session au prochain lancement, elle est supprimée et ne sera plus proposée
• L’application envoie une demande d’arrêt sûr aux traitements LLM/de traduction avant de quitter

Pour modifier ce comportement ultérieurement :
Dans ［Paramètres］ → ［Comportement du bouton × de la fenêtre］, vous pouvez choisir :
• Demander à chaque fois
• Réduire
• Quitter

'''),
    ('s17_safety', '''【17. Précautions pour une utilisation sûre】
• Vérifiez toujours les avertissements avant d’écrire directement dans le mod d’origine.
• Une mise à jour Steam Workshop peut écraser vos modifications manuelles.
• Une sauvegarde automatique est créée lors d’une écriture directe.
• Pour les traductions volumineuses, commencez de préférence avec le réglage Standard (40 / 1).
• Un petit modèle pour le LLM d’exploration permet de réduire la charge.
• Les clés API cloud ne sont pas enregistrées.
• En cas de problème, créer un ZIP des journaux de diagnostic facilite l’identification de la cause.

'''),
    ('s18_common_uses', '''【18. Utilisations courantes】
Traduire un nouveau mod :
1. Choisissez la ［Langue cible］, puis faites glisser le mod
2. Vérifiez le modèle de traduction
3. Démarrez la traduction
4. Effectuez un QA
5. Recherchez et corrigez les traductions si nécessaire
6. Reportez la version terminée dans le mod en écrivant les différences

Réparer les entrées manquantes d’un mod de traduction existant :
1. Choisissez la langue cible et lancez ［Analyser les mods aux emplacements sélectionnés］
2. Vérifiez l’état « Traduit par un autre mod, avec omissions » dans État de la traduction
3. Traduisez le mod concerné
4. Pendant la traduction, vous pouvez utiliser ［Pause］ ou ［Enregistrer et interrompre］
5. Vérifiez les fichiers terminés avec ［Ouvrir la sortie］
6. Cliquez sur ［Écraser les éléments sélectionnés］ ; si un mod de traduction a été détecté pour la langue cible, choisissez la destination dans la fenêtre de confirmation

Traduire uniquement les ajouts après une mise à jour du mod :
1. Choisissez la langue cible et ajoutez de nouveau le mod mis à jour
2. Le cache précédent et l’instantané des sources sont retrouvés automatiquement
3. Vérifiez la mise à jour par différences
4. Traduisez uniquement les clés nouvelles ou modifiées

Corriger manuellement des traductions japonaises :
1. Ouvrez l’onglet Recherche de traductions
2. Recherchez une clé ou du texte japonais
3. Sélectionnez un résultat
4. Modifiez la traduction et enregistrez

Cet onglet d’aide constitue le manuel intégré de l’application. Même les utilisateurs ne disposant que de la version distribuée peuvent consulter les opérations de base et les fonctions avancées sans ouvrir de README externe.

'''),
    ('unofficial', '''【Un outil non officiel】
Cet outil non officiel est développé par un particulier et n’est pas affilié à Paradox Interactive. Les noms des jeux sont des marques de leurs détenteurs respectifs.
L’outil est gratuit et toutes ses fonctions sont accessibles à tous (licence MIT).

'''),
    ('support', '【Dons et soutien】\nSi vous souhaitez soutenir le développement, vous pouvez faire un don via GitHub Sponsors :\nhttps://github.com/sponsors/BETA-15\nToutes les fonctions restent gratuites, et un don ne débloque aucune fonction supplémentaire (pas de contrepartie, seulement nos remerciements).\nLes dons sont reçus par 株式会社ＶＦソフトウェア (VF Software) et servent à couvrir le temps et les frais de développement.\n\n'),
    ('publishing', '''【Recommandations pour publier un mod traduit】
• Obtenez l’autorisation de l’auteur du mod d’origine. Avant de publier la traduction du mod d’une autre personne sur Steam Workshop ou ailleurs, il est d’usage de contacter l’auteur original et d’obtenir son accord.
• Publiez gratuitement. Les conditions d’utilisation de Paradox Interactive n’autorisent pas à placer les contenus créés par les utilisateurs, tels que les mods, derrière un accès payant (les dons en reconnaissance du temps consacré sont autorisés).
• Si la traduction comprend des passages traduits automatiquement, le mentionner dans la description aide les utilisateurs à faire leur choix.
'''),
]
SOURCE_HASHES = {'intro': 'dc0e64262c52', 's00_overview': '57e3f61ee91f', 's01_requirements': 'f6c2c4898718', 's02_first_checks': 'ad4282fa15f0', 's03_translate_queue': '38ceaa862083', 's04_batch_workers': '0ad57aad8db6', 's05_llm_settings': 'f50d5592d09b', 's06_cache': '053b8fd863bd', 's07_review': 'effd2b2c02b3', 's08_diff': '047b909759cf', 's09_search': '331764e4826a', 's10_glossary': 'f3d3a966a4a3', 's11_models': '101883be6b22', 's12_monitor': 'b317e0f4bc37', 's13_status': '7273a7c98ae2', 's14_data_folder': '5e1b34c6fa85', 's15_logs_diagnostics': '78e7512742d6', 's16_close_button': 'bf95d994339e', 's17_safety': 'a3ae50ab1c28', 's18_common_uses': '054ef2c9de07', 'unofficial': '4f1fb69113b7', 'support': '17cde2812921', 'publishing': '13a1da9a3844'}
