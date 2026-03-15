# Jarvis Pessoal

Assistente pessoal de produtividade via Telegram, construído com Python e FastAPI.

Integra com Telegram, OpenAI, Google Calendar e Google Tasks. Gmail será adicionado em fase futura.

## Arquitetura

- **Backend**: Python 3.12 + FastAPI + SQLAlchemy + SQLite
- **IA**: OpenAI Responses API com function calling
- **Bot**: Telegram Bot API via webhooks
- **Memória**: SQLite local (tabelas: users, conversations, messages, memory_items, action_logs, google_credentials)
- **Google**: OAuth 2.0 + Google Calendar API + Google Tasks API
- **Deploy**: Replit (workflow único, porta 8000)

## Endpoints

| Método | Caminho | Descrição |
|--------|---------|-----------|
| GET | `/health` | Health check — retorna `{"status": "ok"}` |
| GET | `/me/day` | Resumo do dia (dados reais se Google conectado, mock se não) |
| POST | `/webhooks/telegram` | Recebe updates do webhook do Telegram |
| GET | `/auth/google/start` | Inicia fluxo OAuth Google (redireciona para Google) |
| GET | `/auth/google/callback` | Callback OAuth Google (troca code por tokens) |
| GET | `/auth/google/status` | Status da conexão Google |
| POST | `/auth/google/disconnect` | Revoga e remove tokens Google |

## Comandos do Bot Telegram

| Comando | Descrição |
|---------|-----------|
| `/start` | Mensagem de boas-vindas e lista de comandos |
| `/help` | Lista de comandos disponíveis |
| `/myday` | Resumo do dia (agenda e tarefas — dados reais se Google conectado) |
| `/remember <texto>` | Salva uma anotação/lembrete |
| `/memories` | Lista anotações recentes |
| `/connectgoogle` | Envia link para conectar conta Google |
| `/google` | Mostra status da conexão Google |
| `/tasks` | Lista tarefas pendentes do Google Tasks |
| `/newtask <titulo>` | Cria nova tarefa no Google Tasks |
| `/newevent <titulo> \| <início> \| <fim>` | Cria evento no Google Calendar |
| Texto livre | Conversa com o assistente via OpenAI |

## 1. Configurar Google OAuth

### Criar credenciais no Google Cloud Console

1. Acesse [Google Cloud Console](https://console.cloud.google.com/)
2. Crie ou selecione um projeto
3. Ative as APIs: **Google Calendar API** e **Google Tasks API**
4. Vá em **APIs & Services > Credentials**
5. Clique em **Create Credentials > OAuth 2.0 Client ID**
6. Tipo: **Web application**
7. Em **Authorized redirect URIs**, adicione a URL de callback

### ⚠️ IMPORTANTE: Redirect URI

A redirect URI cadastrada no Google Cloud **DEVE corresponder EXATAMENTE** ao valor de `GOOGLE_REDIRECT_URI` configurado no Replit:

- **Protocolo**: `https://` (não `http://`)
- **Domínio**: exatamente igual (ex: `jarvis-pessoal.replit.app`)
- **Path**: `/auth/google/callback` (sem trailing slash!)
- **Exemplo**: `https://jarvis-pessoal.replit.app/auth/google/callback`

Se houver qualquer diferença (mesmo um `/` no final), o Google retornará erro `redirect_uri_mismatch`.

### Escopos utilizados

- `https://www.googleapis.com/auth/calendar.events` — Ler e criar eventos
- `https://www.googleapis.com/auth/tasks` — Ler e criar tarefas

Gmail **não** faz parte desta fase.

## 2. Como rodar no Workspace (desenvolvimento)

### Pré-requisitos

O projeto roda no Replit. As dependências Python são instaladas automaticamente.

### Nota importante sobre o Replit

No Replit, o servidor **deve escutar em `0.0.0.0`** (não em `localhost` ou `127.0.0.1`), e **apenas uma porta externa é exposta**. Este projeto usa a porta `8000`. O workflow está configurado para:

```
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Secrets no Replit

Cadastre os seguintes Secrets no painel do Replit (Tools > Secrets):

| Secret | Obrigatório? | Descrição |
|--------|:---:|-----------|
| `TELEGRAM_BOT_TOKEN` | Sim | Token do bot do Telegram (obtido via @BotFather) |
| `TELEGRAM_WEBHOOK_SECRET` | Sim | String secreta para validar webhooks do Telegram |
| `TELEGRAM_ALLOWED_USER_ID` | Recomendado | Seu user ID do Telegram (string) para filtrar mensagens |
| `OPENAI_API_KEY` | Sim | Chave da API OpenAI |
| `OPENAI_MODEL` | Opcional | Modelo a usar (padrão: `gpt-5-mini`) |
| `APP_BASE_URL` | Sim | URL pública do app (ex: `https://jarvis-pessoal.replit.app`) |
| `GOOGLE_CLIENT_ID` | Sim | Client ID do Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Sim | Client Secret do Google OAuth |
| `GOOGLE_REDIRECT_URI` | Sim | URI de callback (ex: `https://jarvis-pessoal.replit.app/auth/google/callback`) |
| `GOOGLE_OAUTH_SCOPES` | Opcional | Escopos (padrão: `calendar.events tasks`) |
| `GOOGLE_ENCRYPTION_KEY` | Reservado | Para criptografia futura de tokens |
| `APP_ENV` | Opcional | `development` (padrão) ou `production` |
| `TIMEZONE` | Opcional | Fuso horário, padrão `America/Sao_Paulo` |
| `JARVIS_DATABASE_URL` | Opcional | Padrão `sqlite:///./jarvis.db` |

### Nota sobre o workspace

O Replit pode ter workflows adicionais pré-configurados (ex: api-server, mockup-sandbox) que são gerenciados pela plataforma. Eles não fazem parte do Jarvis Pessoal e podem ser ignorados. O único workflow relevante é **"Jarvis Pessoal"**.

### Rodando

Basta iniciar o workflow "Jarvis Pessoal" no Replit. O servidor estará disponível em `https://<seu-repl>.replit.dev`.

### Testes

```bash
pytest tests/ -v
```

### Configurar Webhook do Telegram

**Opção 1 — Script utilitário:**

```bash
APP_BASE_URL=https://seu-repl.replit.app python scripts/set_telegram_webhook.py
```

**Opção 2 — curl direto:**

```bash
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://SEU-REPL.replit.app/webhooks/telegram",
    "secret_token": "SEU_WEBHOOK_SECRET"
  }'
```

**Verificar webhook atual:**

```bash
python scripts/get_telegram_webhook_info.py
```

### Conectar conta Google

1. Configure os Secrets `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e `GOOGLE_REDIRECT_URI`
2. No Telegram, envie `/connectgoogle` ao bot
3. Clique no link recebido
4. Autorize as permissões no Google
5. Após redirecionamento, o Telegram confirmará a conexão
6. Envie `/google` para verificar o status
7. Envie `/myday` para ver dados reais da agenda

### Testando novos comandos

1. `/connectgoogle` — recebe link para conectar Google
2. `/google` — mostra "conectada" ou "não conectada"
3. `/tasks` — lista tarefas pendentes do Google Tasks
4. `/newtask Comprar leite` — cria tarefa
5. `/newevent Reunião | 2026-03-16 09:00 | 2026-03-16 10:00` — cria evento
6. `/myday` — resumo com dados reais

## 3. Como publicar (deploy always-on)

### Preparação

1. Certifique-se de que todos os Secrets obrigatórios estão cadastrados
2. Configure `APP_ENV=production` nos Secrets
3. Configure `APP_BASE_URL` com a URL pública do deploy (ex: `https://jarvis-pessoal.replit.app`)
4. Se quiser usar PostgreSQL em produção, configure `JARVIS_DATABASE_URL` com a connection string

### Publicando

Use o botão "Deploy" no Replit e selecione "Autoscale" ou "Reserved VM". O comando de execução é:

```
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Pós-deploy

1. Configure o webhook do Telegram apontando para a URL de produção
2. Verifique o endpoint `/health` para confirmar que está funcionando
3. Conecte a conta Google via `/connectgoogle` no Telegram

## Roadmap

### Fase 2 ✅
- Bot Telegram funcional com comandos e texto livre
- Integração real com OpenAI (Responses API + function calling)
- Memória local em SQLite (anotações, conversas, histórico)
- Idempotência por update_id
- Segurança: webhook secret + filtro por user_id

### Fase 3 ✅
- Google OAuth 2.0 (fluxo completo com refresh token)
- Google Calendar: listar e criar eventos reais
- Google Tasks: listar e criar tarefas reais
- Fallback para dados mockados quando Google não conectado
- Novos comandos Telegram: /connectgoogle, /google, /tasks, /newtask, /newevent
- Novas tools OpenAI: list_tasks, create_task, list_upcoming_events, create_event

### Fase futura
- Gmail (e-mails reais)
- Transcrição de voz via OpenAI Whisper
- Edição/exclusão de eventos e tarefas (com aprovação explícita)
- Criptografia de tokens Google
