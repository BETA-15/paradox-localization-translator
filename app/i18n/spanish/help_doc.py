"""使い方タブの説明書（spanish）。節ごとに持つ（第3段 5-2 章）。"""

HELP_TITLE = "Paradox Localization Translator — Guía de uso"

STALE_NOTICE = '(Esta sección aún no se ha actualizado a la versión más reciente. Parte de su contenido puede estar desactualizado; consulta la versión inglesa para conocer las últimas novedades.)'

HELP_SECTIONS = [
    ('intro', 'Guía detallada de Paradox Localization Translator\n\n'),
    ('s00_overview', '''【0. Qué puedes hacer con esta aplicación】
Esta herramienta integra las funciones necesarias para traducir los archivos YAML de localización de los juegos de Paradox Interactive al idioma de destino elegido, mediante un LLM local o una API en la nube.
Además de la traducción en lote, permite reparar textos sin traducir, actualizar solo las diferencias, realizar controles de calidad (QA), buscar y corregir traducciones, analizar el estado de traducción de los mods, aplicar las diferencias a mods de traducción existentes y gestionar la caché.

Principales juegos compatibles:
• Crusader Kings III
• Victoria 3
• Hearts of Iron IV
• Stellaris
• Europa Universalis V

'''),
    ('s01_requirements', '''【1. Qué necesitas para empezar】
Para usar un LLM local:
• Ollama o LM Studio
• Un modelo LLM para traducir

Para usar una API en la nube:
• Una clave API de OpenAI / Anthropic / Gemini / una API compatible con OpenAI

La aplicación distribuida incluye Python, Tk/Tcl y los componentes gráficos necesarios, por lo que no tienes que instalar Python por separado.

'''),
    ('s02_first_checks', '''【2. Qué comprobar al iniciar la aplicación】
En la pestaña ［Ajustes］, el campo ［Idioma de la interfaz］ permite elegir entre 11 idiomas de visualización. En el primer inicio se usa el idioma del sistema operativo, o el inglés si no es compatible. Si ya usabas la aplicación y no habías configurado el idioma de la interfaz, se usa el japonés. Los cambios se aplican después de reiniciar la aplicación. Este ajuste es independiente del idioma de destino de la traducción.

En la parte superior de la ventana se muestran dos estados de LLM independientes.

LLM de traducción:
Se usa para la traducción normal, la traducción de diferencias, la corrección con IA en QA, las pruebas de velocidad de los modelos, etc.

LLM de búsqueda:
Se usa para buscar mods sin traducir y evaluar candidatos ambiguos al analizar el estado de traducción.
Para la búsqueda se recomienda un modelo ligero de entre 3B y 8B aproximadamente.

Los campos «Última respuesta del LLM de traducción (solo lectura)» y «Última respuesta del LLM de búsqueda (solo lectura)» muestran las respuestas que realmente ha devuelto cada LLM, sin permitir editarlas.
Con «Abrir respuesta completa» puedes consultar la respuesta íntegra.

'''),
    ('s03_translate_queue', '''【3. Pestaña Traducción / Cola】
Esta es la pestaña principal para la traducción normal.

［Idioma de destino］:
Puedes elegir inglés, francés, alemán, español, japonés, coreano, polaco, portugués (Brasil), ruso, chino simplificado o turco. Cada elemento guarda el idioma de destino seleccionado en el momento de añadirlo a la cola. Cambiar la selección después no modifica el idioma de los elementos ya añadidos.

［Añadir］:
Añade archivos YAML o carpetas de localization/mods. También puedes arrastrarlos y soltarlos.

［Quitar selección］:
Elimina solo los elementos seleccionados de la cola. No elimina los archivos originales.

［Vaciar cola］:
Vacía la cola de traducción. No elimina los originales ni la caché.

［Iniciar traducción］:
Traduce los elementos por orden, de arriba abajo.

［Pausar］:
Pausa el proceso en un punto seguro, una vez terminada la respuesta actual de la API o del LLM.

［Guardar e interrumpir］:
Guarda la caché y la sesión acumuladas hasta ese momento y detiene el proceso. Puedes reanudarlo la próxima vez que abras la aplicación.

［Aplicar ajustes a la traducción actual］:
Si cambias el modelo, el proveedor, la URL, el tamaño del lote, el número de solicitudes paralelas, el Glosario, el uso conjunto de inglés y chino u otros ajustes durante la traducción, pulsa este botón para aplicar los nuevos ajustes a partir del siguiente lote.

［Sobrescribir selección en lote］:
Aplica la traducción terminada al mod original o al mod de traducción detectado para el idioma de destino.
Si existe un mod de traducción, en la confirmación puedes elegir «Sí» para sobrescribir solo las diferencias en ese mod de traducción, «No» para sobrescribir el mod original o «Cancelar» para detener la operación. Antes de sobrescribir se indica claramente el destino y se crea una copia de seguridad.

'''),
    ('s04_batch_workers', '''【4. Ajustes recomendados de lotes y solicitudes paralelas】
Puedes elegir entre tres configuraciones recomendadas.

Estable: lote de 20 / 1 solicitud paralela
• Mods con muchos textos largos
• Primer uso
• Equipos con poca memoria disponible
• Cuando la prioridad es comprobar que todo funciona correctamente

Estándar: lote de 40 / 1 solicitud paralela
• Es la configuración recomendada para el uso habitual
• Equilibra velocidad y estabilidad

Rápida: lote de 60 / 2 solicitudes paralelas
• Cuando Ollama o LM Studio pueden procesar dos solicitudes simultáneas
• Cuando hay suficiente RAM/VRAM

Orientaciones:
• Lotes de 1 a 60: intervalo habitual
• Lotes de más de 80: los textos largos pueden provocar más omisiones y tiempos de espera agotados
• Lotes de más de 120: no recomendados
• 1 solicitud paralela: máxima estabilidad
• 2 solicitudes paralelas: recomendado si el procesamiento paralelo está activado en el servidor
• 3 o más solicitudes paralelas: con un LLM local pueden aumentar la presión sobre la memoria, las colas de espera y los tiempos de espera agotados

Con las API en la nube, respeta ante todo los límites de frecuencia del servicio.

'''),
    ('s05_llm_settings', '''【5. Ajustes del LLM y de la traducción】
Proveedor:
Puedes elegir Ollama / LM Studio / OpenAI / Anthropic / Gemini / OpenAI Compatible.

URL:
Valor predeterminado de Ollama: http://localhost:11434
Valor predeterminado de LM Studio: http://localhost:1234/v1
Para los servicios en la nube suele configurarse automáticamente.

Modelo:
Después de comprobar la conexión, elige uno de la lista de modelos disponibles.

Clave API:
Se usa para las API en la nube. No se guarda en el archivo de configuración de la aplicación.

Preajuste:
Define las pautas del prompt de traducción para cada juego, como CK3.

Traducción basada en el chino:
Al añadir un YAML en chino simplificado a la pestaña ［Traducción basada en el chino］, la traducción toma como referencia principal el vocabulario de caracteres chinos, los términos institucionales y los términos propios del chino. No necesitas un archivo en inglés.
Puedes elegir japonés o coreano como idioma de destino. El coreano está pensado para mods ambientados en Asia oriental, con muchos términos de cargos e instituciones de origen chino. Para los títulos y términos religiosos occidentales, la traducción normal desde el inglés suele acercarse más a la traducción oficial.

Reparar textos sin traducir en traducciones japonesas existentes:
Si quedan textos en inglés u otros idiomas dentro de l_japanese, solo esas partes se seleccionan para su reparación.

［Crear copia de seguridad, ejecutar QA y corregir errores tras traducir］:
Después de traducir, comprueba si hay textos sin traducir o sintaxis de Paradox dañada según el idioma de destino.

Tratamiento de los espacios de ancho medio en chino simplificado:
Elimina únicamente los espacios de ancho medio entre caracteres chinos y signos de puntuación o paréntesis. Conserva los espacios entre palabras en números de modelo y nombres de equipamiento.

'''),
    ('s06_cache', '''【6. Caché】
Cada traducción tiene una caché independiente. Las cachés se separan por idioma de destino, de modo que las traducciones de un mismo mod a distintos idiomas no se mezclan.
Cuando se actualiza el mismo mod, la aplicación también identifica la caché anterior y no vuelve a traducir los textos que no han cambiado.

［Ver caché］:
Permite consultar el contenido de la caché del elemento seleccionado en la cola, el número de entradas y su ubicación.

［Añadir caché］:
Integra otro archivo translate_cache.json en la traducción actual.

Actualización de diferencias:
Compara el archivo source_manifest.json del original anterior con el original actual y vuelve a traducir solo las partes nuevas o modificadas para el idioma de destino.

'''),
    ('s07_review', '''【7. Pestaña QA / Comparar y editar】
Compara el original con la traducción al idioma de destino y muestra los problemas en una vista jerárquica.
Puedes cargar archivos YAML arrastrándolos y soltándolos.

Comprobaciones principales:
• Textos sin traducir
• Claves ausentes
• Marcadores de posición que no coinciden
• Daños en [Character...] / $VALUE$ / códigos de color §, etc.
• Presencia de tipos de caracteres impropios del idioma de destino: caracteres chinos, kana, hangul o caracteres cirílicos
• Valores idénticos al original y restos de inglés; en algunos casos se excluyen los nombres propios, los números de modelo, etc.
• Posibles errores tipográficos u omisiones, solo en japonés
• Incoherencias en paréntesis o puntuación

Al seleccionar una fila con un problema, puedes ver el original y la traducción uno al lado del otro.
Puedes editar directamente el campo ［Traducción (editable)］ y guardar los cambios. Algunos casos de caracteres impropios, valores idénticos al original o restos de inglés se muestran como avisos. Revisa el contenido y corrígelo cuando corresponda.
La corrección con IA usa los ajustes actuales del LLM de traducción. Después de cambiarlos, pulsa ［Aplicar ajustes actuales de traducción］.

'''),
    ('s08_diff', '''【8. Pestaña Análisis de diferencias】
Compara el original y la traducción al idioma de destino, clave por clave, uno al lado del otro.
También admite arrastrar y soltar archivos.

Ejemplos de clasificación:
• Ausente: la clave existe en el original, pero no en la traducción
• Sin traducir: el análisis para el idioma de destino considera que el texto no está traducido, por ejemplo porque sigue siendo idéntico al original
• Solo en el idioma de destino: la clave existe únicamente en la traducción; en la pantalla se muestra el nombre del idioma
• Correspondencia correcta: la clave tiene su correspondencia normal

［Traducir selección］:
Traduce solo la clave seleccionada.

［Traducir todas las claves ausentes o sin traducir］:
Envía al LLM únicamente las partes problemáticas, agrupadas en lotes.

La traducción de diferencias también usa los ajustes actuales del LLM de traducción.

'''),
    ('s09_search', '''【9. Pestaña Buscar traducciones】
Busca en varios archivos YAML o carpetas en japonés y permite corregir las traducciones directamente desde los resultados.

La búsqueda abarca:
• Nombres de archivo
• Claves de localización
• Texto en japonés

Al seleccionar un resultado puedes editar la traducción actual y aplicarla al YAML original con ［Guardar esta traducción japonesa］.

'''),
    ('s10_glossary', '''【10. Pestaña Glosario】
Elige el idioma de destino en ［Idioma］ para registrar traducciones fijas por idioma. La traducción, QA y el análisis de diferencias usan el Glosario del idioma de destino correspondiente.
Ejemplo en japonés: Grand Campaign → 開辺

［Importar del juego base］, la importación desde YAML o mods ya traducidos y ［Crear Glosario automáticamente］ en las distintas pestañas de trabajo están disponibles para los 11 idiomas.

Solo se incluyen en el prompt del LLM los términos cuyo texto original aparece en el lote que se va a traducir.
Si modificas el Glosario durante la traducción, también puedes aplicar los ajustes a la traducción actual para que los cambios se usen a partir del siguiente lote.

'''),
    ('s11_models', '''【11. Pestaña Modelos / Conexión】
Permite comprobar la conexión, consultar la lista de modelos, realizar pruebas de velocidad y gestionar perfiles.

Probar velocidad del LLM actual:
Mide el rendimiento del único modelo seleccionado actualmente.

Comparar modelos seleccionados:
Elige hasta cinco modelos y compara su tiempo medio de procesamiento, tokens/s y tasa de fallos.

Perfiles de modelos:
Puedes guardar conjuntamente el proveedor, la URL, el modelo, el tamaño del lote, el número de solicitudes paralelas, el preajuste del juego, etc.
También puedes eliminar perfiles, no solo añadirlos.

El proveedor, la URL y el modelo usados por última vez para traducción y búsqueda se restauran automáticamente al iniciar de nuevo la aplicación. Las claves API no se guardan.

'''),
    ('s12_monitor', '''【12. Pestaña Monitor de textos sin traducir】
Supervisa continuamente, en modo de solo lectura, las ubicaciones de mods registradas en la pestaña Estado de la traducción. No traduce automáticamente.

Ubicaciones supervisadas:
Al seleccionar un juego o una ubicación de mods en la pestaña ［Estado de la traducción］ y ejecutar ［Analizar mods de las ubicaciones seleccionadas］, esa ubicación también se registra para su supervisión.

LLM dedicado a la búsqueda:
Puedes elegir un modelo distinto del utilizado para la traducción normal. Se recomienda un modelo ligero de entre 3B y 8B aproximadamente.

［Iniciar monitorización continua］:
Una vez iniciada, el mismo botón pasa a llamarse ［Detener supervisión continua］ y el campo de estado indica «● Monitorización continua».

［Volver a analizar］:
Vuelve a analizar el estado de traducción de los mods en las ubicaciones ya registradas para su supervisión.

Durante la supervisión se comprueban la fecha de modificación y el tamaño de los YAML, y solo se analizan los elementos que han cambiado. Solo los candidatos ambiguos se envían al LLM ligero.

'''),
    ('s13_status', '''【13. Pestaña Estado de la traducción】
Esta pestaña reúne la detección automática de juegos y ubicaciones de mods, la selección de ubicaciones y el análisis del estado de traducción de los mods.
Puedes seleccionar varias ubicaciones y ejecutar ［Analizar mods de las ubicaciones seleccionadas］. Los resultados se guardan en caché por idioma de destino y solo se vuelven a analizar los mods que han cambiado. Después de actualizar a v0.13, repite el análisis, ya que ha cambiado el método de clasificación.

Ejemplos de estados mostrados:
• Sin traducir
• Con huecos
• Traducción en otro mod con huecos
• Traducción completa en otro mod
• Traducido

Detección de mods de traducción:
Aunque el mod original no incluya el idioma de destino, si otro mod del mismo juego contiene claves traducidas que corresponden a las claves originales, se considera un candidato a mod de traducción.
También se indica si la traducción está completa o tiene huecos. Si el idioma de destino es el inglés, no se comparan mods de traducción externos, porque muchos mods ya contienen inglés.

La pestaña ［Diagnóstico completo］ también realiza el diagnóstico y establece las correspondencias para el idioma de destino. Las correspondencias para idiomas distintos del japonés se han comprobado con pocos datos reales, por lo que debes verificarlas antes de sobrescribir.

Búsqueda:
Introduce el nombre de un mod o un estado para filtrar la lista de resultados ya clasificados.

Añadir a la cola:
Si seleccionas varios mods, puedes añadirlos todos a la cola de traducción normal. En la cola basada en el chino se añaden todos los mods seleccionados que contengan localización china.

Excluir los mods seleccionados y añadir el resto a la cola:
Puedes excluir únicamente los mods seleccionados y añadir todos los demás a la cola normal, o añadir a la cola basada en el chino solo los que tengan localización china.

Sobrescribir un mod de traducción:
Si existe un mod de traducción para el idioma de destino, se aplican las partes que faltan a ese mod de traducción mediante una actualización de diferencias, en lugar de sobrescribir el mod original.
Se conservan las traducciones existentes y solo se añaden o actualizan las claves ausentes o sin traducir.
Antes de ejecutar la operación se muestran el nombre y la ruta del mod de destino, se crea una copia de seguridad y se solicita una doble confirmación.

［Traducir solo las diferencias］:
Traduce únicamente las claves nuevas o modificadas y las traducciones que faltan para el idioma de destino.

'''),
    ('s14_data_folder', '''【14. Archivos generados automáticamente y ubicación de almacenamiento】
Todos los archivos generados automáticamente se reúnen en una única carpeta.

Ubicación predeterminada:
書類/Documents/Paradox Localization Translator/

Estructura:
Paradox Localization Translator/
├── 翻訳結果/
├── キャッシュ/
├── バックアップ/
├── ログ/
├── 作業データ/
└── 設定/

Las carpetas de salida de los resultados también se separan por idioma de destino. Sus nombres terminan en «…_japanese», «…_french», etc., y dentro se guardan los YAML de cada idioma.

Al iniciar, la aplicación detecta ParadoxLocalizationTranslator_Data junto al ejecutable de versiones anteriores y transfiere los datos necesarios a esta ubicación sin destruir los existentes. Las rutas absolutas antiguas de las sesiones que se reanudan también se reinterpretan para que apunten a la ubicación actual.

Puedes elegir otro SSD o cualquier carpeta mediante ［Cambiar ubicación］ en la pestaña ［Ajustes］. También puedes copiar los datos existentes para migrarlos.

'''),
    ('s15_logs_diagnostics', '''【15. Registros de errores y diagnóstico】
Las excepciones de la aplicación, los fallos de conexión con el LLM, los errores de análisis de YAML, los fallos de escritura y otros problemas se guardan en registros diarios.

［Abrir registro de errores］:
Abre la carpeta de registros.

［Recopilar registros de diagnóstico］:
Reúne el sistema operativo, la versión de la aplicación, la información del modelo, los registros de errores, etc., en un ZIP de diagnóstico. No incluye las claves API ni el texto de las traducciones.

'''),
    ('s16_close_button', '''【16. Qué ocurre al pulsar el botón ×】
De forma predeterminada, al pulsar el botón × de la esquina superior derecha o izquierda aparece esta confirmación:

«¿Quieres minimizar la ventana o salir de la aplicación?»

Minimizar:
• Solo minimiza la ventana
• No detiene la traducción, la búsqueda ni el procesamiento del LLM

Salir:
• Si hay elementos sin terminar en la cola de traducción, guarda la sesión
• Las colas que han terminado correctamente no se conservan como sesiones para restaurar
• Si rechazas restaurar una sesión en el siguiente inicio, se descarta y no vuelve a aparecer
• Solicita la detención segura del LLM y de la traducción antes de cerrar la aplicación

Para cambiar este comportamiento más adelante:
En ［Ajustes］ → ［Acción del botón de cierre］ puedes elegir:
• Preguntar siempre
• Minimizar
• Salir

'''),
    ('s17_safety', '''【17. Precauciones para un uso seguro】
• Antes de sobrescribir directamente el mod original, lee siempre las advertencias.
• Las actualizaciones de Steam Workshop pueden sobrescribir los cambios manuales.
• Al sobrescribir directamente se crea una copia de seguridad automática.
• Para traducciones grandes, empieza con los ajustes estándar (40 / 1).
• Un modelo pequeño para el LLM de búsqueda reduce la carga del equipo.
• Las claves API de los servicios en la nube no se guardan.
• Si hay un problema, crear un ZIP con los registros de diagnóstico facilita la investigación de la causa.

'''),
    ('s18_common_uses', '''【18. Casos de uso habituales】
Traducir un mod nuevo:
1. Elige ［Idioma de destino］ y después arrastra el mod
2. Comprueba el modelo de traducción
3. Iniciar traducción
4. QA
5. Si hace falta, busca y corrige traducciones
6. Sobrescribe las diferencias en el mod con la versión terminada

Reparar los huecos de un mod de traducción existente:
1. Elige el idioma de destino y ejecuta ［Analizar mods de las ubicaciones seleccionadas］
2. En Estado de la traducción, busca «Traducción en otro mod con huecos»
3. Traduce el mod correspondiente
4. Durante la traducción puedes usar ［Pausar］ o ［Guardar e interrumpir］
5. Comprueba los archivos terminados con ［Abrir salida］
6. Pulsa ［Sobrescribir selección en lote］ y, si se ha detectado un mod de traducción para el idioma de destino, elige el destino en la confirmación

Traducir solo las incorporaciones tras actualizar un mod:
1. Elige el idioma de destino y vuelve a añadir el mod actualizado
2. La caché anterior y la instantánea del original se identifican automáticamente
3. Comprueba la actualización de diferencias
4. Traduce solo las claves nuevas o modificadas

Corregir manualmente términos de la traducción japonesa:
1. Abre la pestaña Buscar traducciones
2. Busca una clave o un texto en japonés
3. Selecciona un resultado
4. Edita la traducción y guarda los cambios

Esta pestaña Ayuda es el manual integrado en la aplicación. Incluso si solo has recibido la versión distribuida, puedes consultar desde las operaciones básicas hasta las funciones avanzadas sin abrir un README externo.

'''),
    ('unofficial', '''【Esta herramienta no es oficial】
Esta es una herramienta no oficial desarrollada por una persona, sin relación con Paradox Interactive. Los nombres de los juegos son marcas comerciales de sus respectivos titulares.
La herramienta es gratuita y cualquiera puede usar todas sus funciones (licencia MIT).

'''),
    ('support', '【Donaciones y apoyo】\nSi quieres apoyar el desarrollo, puedes donar a través de GitHub Sponsors:\nhttps://github.com/sponsors/BETA-15\nTodas las funciones siguen siendo gratuitas y donar no desbloquea funciones adicionales (no hay recompensas, solo nuestro agradecimiento).\nLas donaciones las recibe VF Software Co., Ltd. y se destinan al tiempo y los gastos del desarrollo.\n\n'),
    ('publishing', '''【Recomendaciones al publicar un mod traducido】
• Obtén el permiso del autor del mod original. Al publicar una traducción del mod de otra persona en Steam Workshop u otros sitios, la práctica habitual es contactar con el autor original y pedirle permiso.
• Publícalo gratuitamente. Las condiciones de uso de Paradox Interactive no permiten ofrecer mods u otros contenidos creados por usuarios tras una barrera de pago; sí permiten aceptar donaciones por el tiempo dedicado.
• Si incluye traducción automática, indícalo en la descripción para que los usuarios puedan decidir con conocimiento de causa.
'''),
]
SOURCE_HASHES = {'intro': 'dc0e64262c52', 's00_overview': '57e3f61ee91f', 's01_requirements': 'f6c2c4898718', 's02_first_checks': 'ad4282fa15f0', 's03_translate_queue': '38ceaa862083', 's04_batch_workers': '0ad57aad8db6', 's05_llm_settings': 'f50d5592d09b', 's06_cache': '053b8fd863bd', 's07_review': 'effd2b2c02b3', 's08_diff': '047b909759cf', 's09_search': '331764e4826a', 's10_glossary': 'f3d3a966a4a3', 's11_models': '101883be6b22', 's12_monitor': 'b317e0f4bc37', 's13_status': '7273a7c98ae2', 's14_data_folder': '5e1b34c6fa85', 's15_logs_diagnostics': '78e7512742d6', 's16_close_button': 'bf95d994339e', 's17_safety': 'a3ae50ab1c28', 's18_common_uses': '054ef2c9de07', 'unofficial': '4f1fb69113b7', 'support': '17cde2812921', 'publishing': '13a1da9a3844'}
