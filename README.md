# QuoteTrace

CLI em Python para transformar documentos operacionais e comerciais em uma cotação estruturada, rastreável e calculada de forma determinística.

O projeto foi desenvolvido para o desafio técnico de Lead AI Engineer da Aterra. A implementação privilegia correção financeira e auditabilidade: cada valor calculado registra quantidade, tarifa, fórmula, nível de confiança e referência ao documento de origem.

## Sobre o projeto

Documentos de viagem frequentemente misturam reservas, tarifas, exceções comerciais, correções por e-mail e informações incompletas. Produzir apenas um total esconderia essas incertezas e poderia transformar uma associação incorreta em um erro financeiro aparentemente válido.

O QuoteTrace separa o problema em responsabilidades explícitas:

```text
Documentos
    ↓
Extração e normalização
    ↓
Validação de evidências e regras comerciais
    ↓
Cálculos determinísticos com Decimal
    ↓
JSON rastreável + itens que exigem revisão
```

### Estratégia de extração

Existem dois caminhos de execução:

- **Adaptador determinístico:** usado para os documentos fornecidos no desafio. Valida a identidade dos arquivos e aplica regras específicas conhecidas, sem API externa.
- **Extração assistida por LLM:** usada para documentos textuais desconhecidos. O modelo propõe serviços, quantidades, fatores e associações de tarifas por meio de um schema estrito.

Quando `--extractor llm` é forçado sobre os documentos conhecidos, a LLM realmente é executada, mas
sua saída funciona como uma proposta auditada. O JSON final continua sendo precificado pelo adaptador
determinístico revisado. Isso evita que uma resposta plausível do modelo substitua silenciosamente regras
como unidade por veículo, sobreposição de temporadas, direção da rota ou precedência de um e-mail.

O LLM é usado somente onde existe ambiguidade semântica. Ele não calcula valores, subtotais ou totais e não decide se uma cotação pode ser enviada ao cliente. No caminho genérico, o QuoteTrace ainda:

- verifica se os trechos citados pelo modelo existem nos documentos locais;
- tolera apenas diferenças de apresentação nas citações (pontuação, caixa, espaços e zeros decimais)
  e grava no resultado o trecho literal recuperado do documento;
- valida datas, moedas, quantidades e strings decimais;
- calcula todos os valores localmente com `Decimal`;
- classifica resultados extraídos por LLM no máximo como `conditional`;
- interrompe o processamento quando uma evidência não pode ser comprovada.

Essa separação é intencional: um cálculo pode ser matematicamente correto e ainda estar comercialmente errado se a tarifa ou a quantidade tiver sido extraída incorretamente.

### Política de confiança

Cada linha de custo recebe uma classificação explícita:

- `confirmed`: tarifa vigente, associação inequívoca e fórmula completa;
- `conditional`: valor calculável, mas que ainda depende de validação operacional ou humana;
- `indicative`: valor conhecido, porém fora da validade aplicável;
- `unresolved`: não existe informação segura suficiente para calcular.

Os subtotais são separados por confiança. Linhas não resolvidas não entram nas somas e `client_ready_total` permanece `null` enquanto houver decisões pendentes. O sistema prefere não calcular a inventar uma certeza.

### Decisões técnicas

- Python 3.11+ e poucas dependências externas.
- Valores monetários representados por `Decimal`, nunca por `float`.
- Arredondamento financeiro explícito em duas casas decimais.
- Valores monetários serializados como strings no JSON.
- Uma linha de saída para cada serviço operacional, inclusive itens gratuitos e não resolvidos.
- Proveniência de quantidade e tarifa preservada por documento, página, seção e trecho.
- Regras de precedência, validade e unidade mantidas fora do LLM.
- Falha explícita para documentos vazios, evidências inventadas e formatos sem suporte.

## Como rodar

### Pré-requisitos

- Python 3.11 ou superior;
- uma chave da API da OpenAI somente para documentos desconhecidos ou quando o modo LLM for forçado.

### Instalação

Na raiz do projeto:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

No Windows PowerShell, ative o ambiente com:

```powershell
.venv\Scripts\Activate.ps1
```

### Configurar a chave da OpenAI

Copie o arquivo de exemplo na raiz do projeto:

```bash
cp .env.example .env
```

Abra o novo arquivo `.env` e substitua o valor de exemplo:

```dotenv
OPENAI_API_KEY=sk-sua-chave-aqui
```

O QuoteTrace carrega esse arquivo automaticamente ao iniciar. Não é necessário executar `export` nem informar a chave em cada comando. O `.env` está ignorado pelo Git e não deve ser enviado, compartilhado ou incluído no arquivo ZIP da entrega.

Uma variável `OPENAI_API_KEY` já definida no sistema tem precedência sobre o valor do `.env`. Os documentos originais continuam funcionando mesmo quando nenhum dos dois está configurado.

### Executar com os documentos do desafio

Esse fluxo é totalmente local e não precisa de chave de API:

```bash
python -m quote_trace \
  --input ../docs \
  --output output/costed-quotation.json
```

O resultado de referência já gerado está em [`output/costed-quotation.json`](output/costed-quotation.json).

### Executar com outros documentos

O modo padrão é `auto`: ele usa o adaptador determinístico quando reconhece o conjunto do desafio e recorre ao LLM para outros conjuntos suportados.

```bash
python -m quote_trace \
  --input caminho/para/documentos \
  --output output/other-quotation.json
```

São aceitos PDF com camada de texto, TXT, MD, EML e CSV. PDFs escaneados são rejeitados de forma explícita porque exigem uma etapa de OCR que não faz parte desta versão.

> O modo LLM envia o conteúdo textual dos documentos para a API da OpenAI. Ele só deve ser habilitado quando as políticas de privacidade e processamento de dados permitirem esse envio.

### Selecionar o modo de extração

```bash
# Seleção automática — comportamento padrão
python -m quote_trace --input ../docs --output output/result.json --extractor auto

# Proíbe qualquer chamada ao LLM
python -m quote_trace --input ../docs --output output/result.json --extractor deterministic

# Força a extração via LLM
python -m quote_trace --input caminho/para/documentos --output output/result.json --extractor llm

# Seleciona outro modelo para a extração
python -m quote_trace --input caminho/para/documentos --output output/result.json --model gpt-5-mini

# Aumenta o limite total para uma extração excepcionalmente demorada
python -m quote_trace --input caminho/para/documentos --output output/result.json --extractor llm --timeout-seconds 900
```

O modelo padrão é `gpt-5-mini`. A extração LLM é iniciada em background e consultada até terminar,
com limite total padrão de 600 segundos. Isso evita manter uma única conexão HTTP aberta durante toda
a geração. O programa não repete automaticamente a criação da resposta, pois uma repetição após uma
falha de rede poderia gerar processamento e cobrança duplicados.

Ao forçar `--extractor llm` sobre a pasta original do desafio, somente a cotação operacional, o rate
pack e o e-mail do fornecedor são enviados. Briefs e transcrições são documentação de contexto, não
fontes comerciais, e por isso ficam fora da extração. Nesse caso, `extraction.mode` será
`llm_assisted_deterministic`: a quantidade de linhas candidatas fica registrada em `extraction.audit`,
mas tarifas, fatores e totais da LLM não entram no orçamento autoritativo. Se a proposta citar uma
evidência inexistente ou falhar na validação local, ela será marcada como `rejected` na auditoria sem
impedir que o adaptador conhecido produza o orçamento determinístico.

### Executar os testes

```bash
python -m pytest
```

Para reproduzir toda a validação de aceite:

```bash
python -m pytest
python -m quote_trace --input ../docs --output output/costed-quotation.json
python -m json.tool output/costed-quotation.json >/dev/null
```

Os testes cobrem precedência do e-mail do fornecedor, semântica de unidades, inclusões gratuitas, temporadas sobrepostas, tarifas vencidas, incompatibilidades de rota, ausência de preços, proveniência e reconciliação exata dos subtotais. O caminho LLM é testado com uma fronteira HTTP simulada, sem consumir chamadas externas.

### Interpretar a saída

O JSON possui quatro áreas principais:

- `cost_lines`: serviços, quantidades, tarifas, fórmulas, valores e proveniência;
- `totals`: subtotais separados por confiança e o bloqueio do total final;
- `needs_review`: problemas encontrados, impacto e ação humana necessária;
- `extraction`: metadados do extrator, presentes no caminho LLM.

`known_amounts_total_not_client_ready` serve apenas para reconciliação interna. Ele não representa um total aprovado para o cliente.

No schema genérico (`1.2`), `currency` no topo recebe a única moeda efetivamente precificada. Uma linha
sem tarifa ou moeda é contabilizada em `totals.unresolved_without_currency`; ela não cria uma moeda
fictícia `UNKNOWN` nem faz `currency` virar `null`. O valor `null` permanece correto quando não existe
nenhuma moeda precificada ou quando há mais de uma moeda real no orçamento.

## Como o projeto está estruturado

```text
quote-trace/
├── src/quote_trace/
│   ├── __main__.py          # CLI, argumentos e seleção do extrator
│   ├── documents.py         # Leitura e validação do conjunto conhecido
│   ├── llm_extractor.py     # Extração genérica, schema e validações de evidência
│   ├── models.py            # Modelos, confiança e utilitários monetários
│   └── pipeline.py          # Regras comerciais e composição da cotação
├── tests/
│   ├── fixtures/
│   │   └── golden-summary.json
│   └── test_pipeline.py     # Testes determinísticos e da fronteira LLM
├── output/
│   └── costed-quotation.json
├── .env.example             # Modelo seguro para configuração da API
├── NOTE.md                  # Nota técnica do desafio
├── RECORDING.md             # Roteiro sugerido para apresentação
└── pyproject.toml           # Pacote, dependências e configuração de testes
```

### Responsabilidades dos módulos

`documents.py` conhece apenas o formato fornecido no desafio. Ele garante que os arquivos esperados existem, extrai o texto dos PDFs e valida marcadores mínimos de identidade antes que qualquer regra comercial seja executada.

`llm_extractor.py` é a fronteira probabilística. Ele lê formatos textuais suportados, solicita uma saída estruturada à API, verifica as evidências retornadas e converte a proposta em linhas sempre sujeitas a revisão. Para o conjunto conhecido, delega a precificação final ao adaptador determinístico e registra a proposta apenas como auditoria. A função de requisição é injetável para permitir testes sem rede.

`models.py` concentra os contratos do domínio e a política monetária. `pipeline.py` contém as regras determinísticas específicas do desafio, incluindo precedência de tarifas, unidades de cobrança, validade e classificação de confiança.

`__main__.py` mantém a interface fina: interpreta argumentos, escolhe o extrator, grava o JSON somente após uma execução bem-sucedida e retorna erro legível quando a entrada não pode ser processada com segurança.

### Limites conhecidos

Esta versão não é um parser universal. Não há OCR, processamento de imagens, suporte a planilhas ou integração com sistemas de reserva. Documentos muito grandes também exigiriam segmentação e reconciliação entre partes antes de serem enviados a um modelo.

Em uma evolução para produção, os próximos passos seriam OCR com preservação de coordenadas, schemas versionados por fornecedor, validação cruzada de entidades, observabilidade sem exposição de dados sensíveis e um workflow auditável para aprovação humana das linhas condicionais.
