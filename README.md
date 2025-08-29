# AUTOMATEST – Runner de coleções Postman (CLI)

Automatiza a execução de **coleções do Postman** usando o **Postman CLI**, gera um **relatório humano (HTML)** e envia por **e-mail** com os artefatos de cada run.

---

## O que este repositório faz

- Descobre projetos em `collections/<Projeto>/{requests,enviroment}`.
- Para cada **collection** (JSON exportado) e **environment** (JSON exportado), roda:
  - `postman collection run <collection> -e <environment> --reporters cli,json`
- Captura **stdout do CLI** (o mesmo que você vê no terminal: ✓/✗, HTTP, nomes dos testes) e o **run.json**.
- **Monta o relatório**:
  - Resumo por projeto/environment/collection.
  - Requests (nome + HTTP) e **todos os testes `pm.test(...)`** com **OK/FALHA**.
- **Envia e-mail HTML** para os destinatários definidos em `constants.py`.
- Salva tudo em `logs/<YYYY-MM-DD_HH-MM-SS>/...` (inclusive `cli.log.txt` sem ANSI e `run.json`).

> Observação técnica: se o `run.json` não trouxer testes (formatos variam por versão do CLI), o script **parseia o stdout** e reconstrói os testes pass/fail — ou seja, o relatório sempre mostra o que você viu no terminal.

---

## Estrutura de diretórios

├─ collections/
│ └─ <Projeto>/
│ ├─ enviroment/ # environments exportados (.json) ex.: 1.Dev.postman_environment.json
│ └─ requests/ # collections exportadas (.json) ex.: MinhaCollection.postman_collection.json
├─ logs/ # saídas por execução (auto)
├─ constants.py # DESTINATÁRIOS do e-mail (somente aqui)
├─ main.py # orquestrador (menu, runner, relatório, e-mail)
├─ requirements.txt
└─ .env # SMTP + POSTMAN_API_KEY (NÃO define destinatários)


---

## Pré-requisitos

- **Python 3.10+**
- **Postman CLI** instalado no PATH

Instalação do Postman CLI no Windows (PowerShell):
```powershell
powershell -NoProfile -InputFormat None -ExecutionPolicy AllSigned `
  -Command "[System.Net.ServicePointManager]::SecurityProtocol = 3072; `
  iex ((New-Object System.Net.WebClient).DownloadString('[https://dl-cli.pstmn.io/install/win64.ps1](https://dl-cli.pstmn.io/install/win64.ps1)'))"

postman --version

python -m venv .venv
.\.venv\Scripts\activate        # Windows
pip install -r requirements.txt

Configuração
1) Destinatários (obrigatório) – constants.py

Nunca usamos .env para destinatários. Somente aqui.

# constants.py
EMAIL_RECIPIENTS = [
    "davi.almeida@iebtinnovation.com"
]

# Postman (login automático do CLI)
POSTMAN_API_KEY=PMAK-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# SMTP (envio do relatório)
SMTP_HOST=mail.syntaxa.com.br
SMTP_PORT=465              # 465 (SSL) ou 587 (STARTTLS)
SMTP_USE_TLS=false         # true se usar 587
SMTP_USER=davi.almeida@syntaxa.com.br
SMTP_PASS=********
MAIL_FROM=davi.almeida@syntaxa.com.br   # se vazio, usa SMTP_USER

# Opcional
COLLECTIONS_ROOT=collections
MAIL_SUBJECT=[AUTOMATEST] Relatório de coleções Postman

3) Coleções e environments

Exporte do Postman a collection para collections/<Projeto>/requests/.

Exporte do Postman o environment para collections/<Projeto>/enviroment/.

Você pode ter múltiplos projetos e múltiplos environments por projeto (Dev, Homolog, Prod, …).

## Pré-requisitos
.\.venv\Scripts\activate
python main.py

Menu interativo:

Executar TUDO (todas as coleções × todos os environments de todos os projetos).

Executar projeto + environment específico (o script lista os projetos e, depois, os environments daquele projeto).

Saída:

Console: resumo textual.

logs/<timestamp>/<Projeto>/<Environment>/:

run.json (relatório do CLI)

cli.log.txt (stdout do CLI sem cores)

E-mail HTML para EMAIL_RECIPIENTS:

Cabeçalho por projeto/environment/collection

Requests + HTTP

Lista de testes ✓/✗ exatamente como no terminal

Anexos: run.json e cli.log.txt

Como o relatório é gerado

Formato novo do Postman CLI: usa run.summary e run.executions[*].tests.

Formato antigo: usa run.stats + run.executions[*].assertions.

Fallback robusto: se o JSON não trouxer testes, um parser do stdout extrai:

Nome do request (linha → ...)

Status [200 OK, ...]

Testes “√/×” (nome + pass/fail)

Com isso, o e-mail sempre contém os testes executados.

Troubleshooting

“E-mail não chegou”

Verifique .env (SMTP_HOST/USER/PASS/PORT/SSL).

Cheque spam no primeiro envio.

O console mostra erros de autenticação/destinatário rejeitado.

“Requests/Testes = 0”

Confirme se exportou a collection correta em requests/ e o environment certo em enviroment/.

O CLI precisa localizar os dois arquivos; paths são passados em absoluto.

Mesmo assim, o relatório deve trazer testes via stdout; se não vierem, veja o cli.log.txt.

“Falhou no login do Postman”

Garanta POSTMAN_API_KEY no .env.

Rode postman whoami no terminal para conferir o estado da sessão.

Boas práticas / segurança

Não versionar .env com credenciais reais.

cli.log.txt pode conter URLs/códigos — mas o script não imprime tokens por padrão. Se necessário, sanitize antes de compartilhar.

Mantenha as coleções/exportações atualizadas com os testes pm.test(...).