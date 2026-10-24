"""使い方タブの説明書（braz_por）。節ごとに持つ（第3段 5-2 章）。"""

HELP_TITLE = "Paradox Localization Translator — Guia de uso"
STALE_NOTICE = "(Esta seção ainda não foi atualizada para a versão mais recente. Algumas informações podem estar desatualizadas.)"

HELP_SECTIONS = [
    ('intro', '''Paradox Localization Translator — Guia detalhado

'''),
    ('s00_overview', '''【0. O que você pode fazer com este aplicativo】
Esta ferramenta integrada traduz arquivos YAML de localização dos jogos da Paradox Interactive para o idioma de destino escolhido, usando um LLM local ou uma API na nuvem.
Além da tradução em lote, permite reparar textos não traduzidos, atualizar diferenças, executar QA, buscar e corrigir traduções, analisar a situação da tradução de mods, aplicar diferenças a mods de tradução existentes e gerenciar o cache.

Principais jogos compatíveis:
• Crusader Kings III
• Victoria 3
• Hearts of Iron IV
• Stellaris
• Europa Universalis V

'''),
    ('s01_requirements', '''【1. O que você precisa para começar】
Para usar um LLM local:
• Ollama ou LM Studio
• Um modelo LLM para tradução

Para usar uma API na nuvem:
• Uma chave de API da OpenAI / Anthropic / Gemini / API compatível com OpenAI

A versão distribuída do aplicativo inclui Python, Tk/Tcl e os componentes necessários da interface gráfica. Você não precisa instalar Python separadamente.

'''),
    ('s02_first_checks', '''【2. O que verificar ao abrir o aplicativo】
Na aba ［Configurações］, use ［Idioma da interface］ para escolher entre 11 idiomas de exibição. Na primeira execução, o aplicativo usa o idioma do sistema operacional (ou inglês, se ele não for compatível). Para quem já usava o aplicativo e ainda não definiu o idioma da interface, o padrão é japonês. A mudança entra em vigor depois de reiniciar o aplicativo. Essa configuração é independente do idioma de destino da tradução.

Na parte superior da tela, há dois indicadores de estado do LLM.

LLM de tradução:
Usado para traduções normais, tradução de diferenças, revisão por IA no QA, testes de velocidade dos modelos e outras tarefas.

LLM de descoberta:
Usado para procurar mods não traduzidos e avaliar candidatos ambíguos na análise da situação da tradução.
Para a descoberta, recomendamos um modelo leve, de cerca de 3B a 8B.

Os campos 「Última resposta do LLM de tradução (somente leitura)」 e 「Última resposta do LLM de descoberta (somente leitura)」 mostram, sem permitir edição, as respostas realmente recebidas de cada LLM.
Use 「Abrir resposta completa」 para consultar a resposta inteira.

'''),
    ('s03_translate_queue', '''【3. Aba Tradução / Fila】
Esta é a área principal para traduções normais.

［Idioma de destino］:
Você pode escolher inglês, francês, alemão, espanhol, japonês, coreano, polonês, português (Brasil), russo, chinês simplificado ou turco. Cada item guarda o idioma de destino escolhido quando é adicionado à fila. Mudar a seleção depois não altera o idioma dos itens já adicionados.

［Adicionar］:
Adiciona arquivos YAML ou pastas localization/Mod. Você também pode arrastar e soltar.

［Remover selecionados］:
Remove apenas os itens selecionados da fila. Os arquivos originais não são excluídos.

［Limpar tudo］:
Esvazia a fila de tradução. Não exclui os originais nem o cache.

［Iniciar tradução］:
Traduz os itens em ordem, de cima para baixo.

［Pausar］:
Pausa em um ponto seguro, depois que a resposta atual da API/LLM termina.

［Salvar e parar］:
Salva o cache e a sessão até o ponto atual e interrompe o processamento. Você pode retomar na próxima vez que abrir o aplicativo.

［Aplicar configurações à tradução atual］:
Se você mudar o modelo, provedor, URL, tamanho do lote, paralelismo, Glossário, configuração de uso combinado de inglês e chinês ou outras opções durante a tradução, pressione este botão para usar as novas configurações a partir do próximo lote.

［Sobrescrever itens selecionados em lote］:
Aplica a tradução concluída ao mod original ou ao mod de tradução detectado para o idioma de destino.
Se houver um mod de tradução existente, escolha 「Sim」 na confirmação para aplicar as diferenças a ele, 「Não」 para sobrescrever o mod original ou 「Cancelar」 para interromper a operação. Antes da sobrescrita, o destino é informado e um backup é criado.

'''),
    ('s04_batch_workers', '''【4. Configurações recomendadas de lote / paralelismo】
Você pode escolher entre três configurações recomendadas.

Priorizar estabilidade (20 / 1): lote 20 / paralelismo 1
• Mods com muitos textos longos
• Primeiro uso
• Ambientes com pouca memória disponível
• Quando a prioridade é verificar se tudo funciona corretamente

Padrão (40 / 1): lote 40 / paralelismo 1
• Recomendado para o uso habitual
• Equilíbrio entre velocidade e estabilidade

Rápido (60 / 2): lote 60 / paralelismo 2
• Quando o Ollama / LM Studio consegue processar duas solicitações simultâneas
• Quando há RAM/VRAM suficiente

Referências:
• Lote de 1 a 60: faixa normal
• Lote acima de 80: textos longos ficam mais sujeitos a omissões e tempos limite excedidos
• Lote acima de 120: não recomendado
• Paralelismo 1: opção mais estável
• Paralelismo 2: recomendado quando o processamento paralelo está ativado no servidor
• Paralelismo 3 ou mais: com LLMs locais, tende a aumentar a pressão sobre a memória, as filas de espera e os tempos limite excedidos

Para APIs na nuvem, respeite primeiro os limites de solicitações do serviço.

'''),
    ('s05_llm_settings', '''【5. Configurações de LLM / tradução】
Provedor:
Você pode escolher Ollama / LM Studio / OpenAI / Anthropic / Gemini / OpenAI Compatible.

URL:
Padrão do Ollama: http://localhost:11434
Padrão do LM Studio: http://localhost:1234/v1
Para serviços na nuvem, a configuração normalmente é automática.

Modelo:
Após verificar a conexão, escolha um modelo na lista de modelos disponíveis.

Chave de API:
Usada para APIs na nuvem. Não é salva no arquivo de configurações do aplicativo.

Predefinição do jogo:
Define as orientações do prompt de tradução para cada jogo, como CK3.

tradução baseada no chinês:
Ao adicionar um YAML em chinês simplificado à aba ［tradução baseada no chinês］, a tradução toma como referência principal o vocabulário em caracteres chineses, os termos institucionais e os termos próprios do chinês. Não é necessário ter um arquivo em inglês.
Os idiomas de destino disponíveis são japonês e coreano. O coreano é indicado para mods ambientados no leste asiático (com muitos termos em caracteres chineses para cargos e instituições). Para títulos ocidentais e termos religiosos, a tradução normal (a partir do inglês) tende a ficar mais próxima da tradução oficial.

Reparar trechos não traduzidos no japonês existente:
Se ainda houver inglês ou outro idioma dentro de l_japanese, somente esses trechos serão selecionados para reparo.

［Fazer backup, executar QA automático e corrigir erros após a tradução］:
Depois da tradução, verifica trechos não traduzidos e danos à sintaxe da Paradox de acordo com o idioma de destino.

Tratamento de espaços de meia largura no chinês simplificado:
Remove somente os espaços de meia largura entre caracteres chineses e sinais de pontuação ou parênteses. Preserva os espaços entre palavras de códigos de modelos e nomes de equipamentos.

'''),
    ('s06_cache', '''【6. Cache】
Cada tradução tem um cache independente. Os caches são separados por idioma de destino, por isso não se misturam mesmo quando você traduz o mesmo mod para outro idioma.
Quando o mesmo mod é atualizado, o aplicativo também identifica o cache anterior e não traduz novamente os textos que não mudaram.

［Ver cache］:
Mostra o conteúdo, o número de entradas e o local de armazenamento do cache do item selecionado na fila.

［Adicionar cache］:
Integra outro translate_cache.json à tradução atual.

Atualização de diferenças:
Compara o source_manifest.json do original anterior com o original atual e traduz novamente apenas os trechos novos ou alterados para o idioma de destino.

'''),
    ('s07_review', '''【7. Aba QA / Editor comparativo】
Compara o original com a tradução no idioma de destino e exibe os problemas em uma estrutura hierárquica.
Você pode carregar arquivos YAML arrastando e soltando.

Principais verificações:
• Texto não traduzido
• Chaves ausentes
• Divergências em marcadores de posição
• Danos a [Character...] / $VALUE$ / códigos de cor § e elementos semelhantes
• Presença de tipos de caracteres inadequados ao idioma de destino (caracteres chineses, kana, hangul, cirílico)
• Valores idênticos ao original e trechos em inglês restantes (nomes próprios, códigos de modelos e itens semelhantes podem ser excluídos da verificação)
• Possíveis erros de digitação ou omissões de caracteres (somente japonês)
• Inconsistências em parênteses ou pontuação

Ao selecionar uma linha com problema, você pode conferir o original e a tradução lado a lado.
Você pode editar diretamente o campo ［Tradução (editável)］ e salvar. Alguns casos de caracteres de outro idioma, valores iguais ao original e trechos em inglês restantes aparecem como avisos. Confira o conteúdo e faça as correções necessárias.
A revisão por IA usa as configurações atuais do LLM de tradução. Depois de mudar as configurações, pressione ［Aplicar configurações atuais de tradução］.

'''),
    ('s08_diff', '''【8. Aba Análise de diferenças】
Compara, lado a lado e chave por chave, o original e a tradução no idioma de destino.
Também aceita arrastar e soltar.

Exemplos de classificação:
• Ausente: existe no original, mas não na tradução
• Não traduzido: considerado não traduzido pelos critérios do idioma de destino, por exemplo, quando a tradução permanece igual ao original
• Somente no idioma de destino: a chave existe apenas na tradução (a tela mostra o nome do idioma)
• Correspondência: os textos correspondem corretamente

［Traduzir itens selecionados］:
Traduz somente a chave selecionada.

［Traduzir todas as chaves ausentes e não traduzidas］:
Envia ao LLM, em conjunto, somente os trechos com problemas.

A tradução de diferenças também usa as configurações atuais do LLM de tradução.

'''),
    ('s09_search', '''【9. Aba Busca de traduções】
Busca em vários arquivos YAML/pastas em japonês e permite corrigir as traduções diretamente a partir dos resultados.

Alvos da busca:
• Nome do arquivo
• Chave de localização
• Texto em japonês

Selecione um resultado para editar a tradução atual e use ［Salvar esta tradução em japonês］ para aplicar a alteração ao YAML original.

'''),
    ('s10_glossary', '''【10. Aba Glossário】
Escolha o idioma de destino em ［Idioma］ para registrar traduções fixas separadamente para cada idioma. A tradução, o QA e a análise de diferenças usam o Glossário desse idioma de destino.
Exemplo (japonês): Grand Campaign → 開辺

［Importar do jogo base］, a importação de arquivos YAML e mods já traduzidos e ［Criar Glossário automaticamente］ nas abas de trabalho estão disponíveis para os 11 idiomas.

Quando um termo original registrado aparece no lote de tradução, somente esse termo é apresentado no prompt do LLM.
Se você mudar o Glossário durante a tradução, também pode aplicar as configurações à tradução atual para que as mudanças entrem em vigor a partir do próximo lote.

'''),
    ('s11_models', '''【11. Aba Modelo / Conexão】
Permite verificar a conexão, listar modelos, testar a velocidade e gerenciar perfis.

Testar velocidade do LLM atual:
Mede o desempenho de um único modelo, o que está selecionado no momento.

Comparar modelos selecionados:
Selecione até cinco modelos para comparar o tempo médio de processamento, tokens/s e a taxa de falhas.

Perfis de modelos:
Você pode salvar juntos o provedor, URL, modelo, tamanho do lote, paralelismo, predefinição do jogo e outras configurações.
É possível excluir perfis, além de adicioná-los.

O provedor, URL e modelo usados pela última vez para tradução/descoberta são restaurados automaticamente na próxima execução. As chaves de API não são salvas.

'''),
    ('s12_monitor', '''【12. Aba Monitor de não traduzidos】
Monitora continuamente, em modo somente leitura, os locais de mods registrados na aba Situação da tradução. Não traduz automaticamente.

Locais monitorados:
Selecione um local de jogo/mods na aba ［Situação da tradução］ e execute ［Analisar mods nos locais selecionados］. Esse local também será registrado para monitoramento.

LLM exclusivo para descoberta:
Você pode definir um modelo diferente do usado na tradução normal. Recomendamos um modelo leve, de cerca de 3B a 8B.

［Iniciar monitoramento contínuo］:
Depois que o monitoramento começa, o mesmo botão passa a ser ［Parar monitoramento contínuo］ e o campo de estado mostra 「● Monitoramento contínuo」.

［Analisar novamente］:
Analisa novamente a situação da tradução dos mods nos locais já registrados para monitoramento.

Durante o monitoramento, o aplicativo verifica a data de atualização e o tamanho dos arquivos YAML e analisa somente os itens alterados. Apenas os candidatos ambíguos são enviados ao LLM leve.

'''),
    ('s13_status', '''【13. Aba Situação da tradução】
Esta aba reúne a detecção automática de locais de jogos/mods, a seleção dos locais a analisar e a análise da situação da tradução dos mods.
Você pode selecionar vários locais e executar ［Analisar mods nos locais selecionados］. Os resultados são armazenados em cache por idioma de destino, e somente os mods alterados são analisados novamente. Depois de atualizar para v0.13, refaça a análise, pois o método de classificação mudou.

Exemplos de exibição:
• Sem tradução
• Com lacunas
• Traduzido por outro mod・com lacunas
• Totalmente traduzido por outro mod
• Com tradução

Detecção de mods de tradução:
Mesmo que o mod original não contenha o idioma de destino, outro mod do mesmo jogo será considerado candidato a mod de tradução se tiver chaves traduzidas correspondentes às chaves originais.
A tela também indica se a tradução está completa ou tem lacunas. Quando o destino é inglês, não são comparados mods de tradução externos, pois muitos mods já contêm inglês.

A aba ［Diagnóstico completo］ também realiza o diagnóstico e a associação com base no idioma de destino. Como as associações para idiomas diferentes do japonês foram pouco verificadas com dados reais, confira a correspondência antes de sobrescrever.

Buscar:
Digite o nome de um mod ou um estado para filtrar a lista já classificada.

Adicionar à fila de tradução normal / Adicionar à fila de tradução baseada no chinês:
Quando vários mods estão selecionados, você pode adicionar todos eles à fila de tradução normal. Na fila baseada no chinês, são adicionados todos os mods selecionados que tenham localização em chinês.

Adicionar à fila de tradução normal excluindo os mods selecionados / Adicionar à fila de tradução baseada no chinês excluindo os mods selecionados:
Exclui somente os mods selecionados e adiciona os demais em conjunto à fila de tradução normal ou, no caso da fila baseada no chinês, apenas os que têm localização em chinês.

Sobrescrita de mods de tradução:
Se houver um mod de tradução para o idioma de destino, os trechos que faltam são aplicados como diferenças a ele, e não ao mod original.
As traduções existentes são preservadas; somente chaves ausentes ou não traduzidas são adicionadas ou atualizadas.
Antes da operação, o nome e o caminho do mod de destino são exibidos, com backup e confirmação dupla.

［Traduzir apenas as diferenças］:
Traduz somente as chaves novas ou alteradas e as traduções que faltam para o idioma de destino.

'''),
    ('s14_data_folder', '''【14. Arquivos gerados automaticamente e local de armazenamento】
Todos os arquivos gerados automaticamente são reunidos em uma única pasta.

Padrão:
書類/Documents/Paradox Localization Translator/

Estrutura:
Paradox Localization Translator/
├── 翻訳結果/
├── キャッシュ/
├── バックアップ/
├── ログ/
├── 作業データ/
└── 設定/

As pastas de saída das traduções também são separadas por idioma de destino. Seus nomes terminam em 「…_japanese」, 「…_french」 e assim por diante, e cada pasta guarda os arquivos YAML do respectivo idioma.

Na inicialização, o aplicativo detecta a pasta ParadoxLocalizationTranslator_Data ao lado do executável de versões anteriores e transfere os dados necessários para este local sem destruir os dados antigos. Os caminhos absolutos antigos nas sessões retomadas também são reinterpretados para apontar ao local de armazenamento atual.

Use ［Alterar local de armazenamento］ na aba ［Configurações］ para escolher outro SSD ou qualquer pasta. Você também pode migrar copiando os dados existentes.

'''),
    ('s15_logs_diagnostics', '''【15. Logs de erros / diagnóstico】
Exceções do aplicativo, falhas de conexão com o LLM, falhas na análise de YAML, falhas de gravação e outros problemas são salvos em logs separados por dia.

［Abrir logs de erros］:
Abre a pasta de logs.

［Coletar logs de diagnóstico］:
Reúne informações sobre o sistema operacional, a versão do aplicativo, o modelo, os logs de erros e outros dados em um ZIP de diagnóstico. Não inclui chaves de API nem o texto das traduções.

'''),
    ('s16_close_button', '''【16. Ao pressionar o botão ×】
Por padrão, ao pressionar o botão × no canto superior direito/esquerdo, aparece esta confirmação:

「Minimizar a janela ou sair do aplicativo?」

Minimizar:
• Minimiza apenas a janela
• A tradução, a descoberta e o processamento do LLM continuam

Sair:
• Salva a sessão se houver itens não concluídos na fila de tradução
• Uma fila concluída com sucesso não é mantida como sessão para restauração
• Se você recusar a restauração de uma sessão na próxima execução, ela será descartada e não voltará a ser oferecida
• Solicita a parada segura do processamento do LLM/tradução antes de encerrar o aplicativo

Para mudar esse comportamento depois:
Em ［Configurações］ → ［Comportamento ao clicar no botão × da janela］,
• Perguntar sempre
• Minimizar
• Sair
pode escolher uma dessas opções.

'''),
    ('s17_safety', '''【17. Cuidados para usar com segurança】
• Sempre leia o aviso antes de sobrescrever diretamente o mod original.
• Atualizações do Steam Workshop podem sobrescrever alterações manuais.
• A sobrescrita direta cria um backup automático.
• Para traduções grandes, recomendamos começar com a configuração Padrão (40 / 1).
• Usar um modelo pequeno no LLM de descoberta reduz a carga.
• As chaves de API na nuvem não são salvas.
• Se houver um problema, criar um ZIP de logs de diagnóstico facilita a investigação da causa.

'''),
    ('s18_common_uses', '''【18. Usos frequentes】
Traduzir um novo mod:
1. Escolha ［Idioma de destino］ e depois arraste o mod
2. Confira o modelo de tradução
3. Inicie a tradução
4. Execute o QA
5. Se necessário, use a busca para corrigir traduções
6. Aplique a versão concluída ao mod sobrescrevendo as diferenças

Corrigir lacunas de um mod de tradução existente:
1. Escolha o idioma de destino e execute ［Analisar mods nos locais selecionados］
2. Na Situação da tradução, confira 「Traduzido por outro mod・com lacunas」
3. Traduza o mod desejado
4. Durante a tradução, você pode usar ［Pausar］ ou ［Salvar e parar］
5. Use ［Abrir saída］ para conferir os arquivos concluídos
6. Pressione ［Sobrescrever itens selecionados em lote］ e, se um mod de tradução do idioma de destino tiver sido encontrado, escolha o destino na tela de confirmação

Traduzir somente os acréscimos após uma atualização do mod:
1. Escolha o idioma de destino e adicione novamente o mod atualizado
2. O cache anterior e o snapshot do original são identificados automaticamente
3. Confirme a atualização de diferenças
4. Traduza somente as chaves novas ou alteradas

Corrigir manualmente termos da tradução em japonês:
1. Abra a aba Busca de traduções
2. Busque uma chave ou um texto em japonês
3. Selecione um resultado
4. Edite a tradução e salve

Esta aba de ajuda é o manual integrado do aplicativo. Mesmo quem recebeu somente a versão distribuída pode consultar desde as operações básicas até os recursos avançados sem abrir um README externo.

'''),
    ('unofficial', '''【Ferramenta não oficial】
Esta é uma ferramenta não oficial desenvolvida por uma pessoa, sem vínculo com a Paradox Interactive. Os nomes de cada jogo são marcas comerciais de seus respectivos titulares.
A ferramenta é gratuita, e todas as funções estão disponíveis para qualquer pessoa (licença MIT).

'''),
    ('support', '【Doações e apoio】\nSe quiser apoiar o desenvolvimento, você pode doar pelo GitHub Sponsors:\nhttps://github.com/sponsors/BETA-15\nTodas as funções continuam gratuitas, e doar não libera funções extras (não há recompensas, apenas nosso agradecimento).\nAs doações são recebidas pela VF Software Co., Ltd. e usadas no tempo e nos custos do desenvolvimento.\n\n'),
    ('publishing', '''【Orientações para publicar mods traduzidos】
• Peça autorização ao autor do mod original. Ao publicar a tradução de um mod de outra pessoa no Steam Workshop ou em outro lugar, é costume entrar em contato com o autor original e obter sua permissão.
• Publique gratuitamente. Os termos de uso da Paradox Interactive não permitem colocar mods e outros conteúdos criados por usuários atrás de uma barreira de pagamento (é permitido receber doações pelo tempo dedicado).
• Se a tradução incluir tradução automática, informar isso na descrição ajuda os usuários a decidir se querem utilizá-la.
'''),
]
SOURCE_HASHES = {'intro': 'dc0e64262c52', 's00_overview': '57e3f61ee91f', 's01_requirements': 'f6c2c4898718', 's02_first_checks': 'ad4282fa15f0', 's03_translate_queue': '38ceaa862083', 's04_batch_workers': '0ad57aad8db6', 's05_llm_settings': 'f50d5592d09b', 's06_cache': '053b8fd863bd', 's07_review': 'effd2b2c02b3', 's08_diff': '047b909759cf', 's09_search': '331764e4826a', 's10_glossary': 'f3d3a966a4a3', 's11_models': '101883be6b22', 's12_monitor': 'b317e0f4bc37', 's13_status': '7273a7c98ae2', 's14_data_folder': '5e1b34c6fa85', 's15_logs_diagnostics': '78e7512742d6', 's16_close_button': 'bf95d994339e', 's17_safety': 'a3ae50ab1c28', 's18_common_uses': '054ef2c9de07', 'unofficial': '4f1fb69113b7', 'support': '17cde2812921', 'publishing': '13a1da9a3844'}
