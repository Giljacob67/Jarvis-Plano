# Jarvis Pessoal

Assistente pessoal de produtividade via Telegram, construído com Python e FastAPI.

Integra (quando totalmente implementado) com Telegram, OpenAI, Google Calendar, Gmail e Google Tasks.

## Arquitetura

- **Backend**: Python 3.12 + FastAPI + SQLAlchemy + SQLite
- **IA**: OpenAI Responses API com function calling
- **Bot**: Telegram Bot API via webhooks
- **Memória**: SQLite local (tabelas: users, conversations, messages, memory_items, action_logs)
- **Deploy**: Replit (workflow único, porta 8000)

## Endpoints

| Método | Caminho | Descrição |
|--------|---------|-----------|
| GET | `/health` | Health check — retorna `{"status": "ok"}` |
| GET | `/me/day` | Resumo do dia com eventos, tarefas e e-mails (dados mockados) |
| POST | `/webhooks/telegram` | Recebe updates do webhook do Telegram |
| GET | `/auth/google/start` | Início do fluxo OAuth Google (stub — retorna 501) |
| GET | `/auth/google/callback` | Callback OAuth Google (stub — retorna 501) |

## Comandos do Bot Telegram

| Comando | Descrição |
|---------|-----------|
| `/start` | Mensagem de boas-vindas e lista de comandos |
| `/help` | Lista de comandos disponíveis |
| `/myday` | Resumo do dia (agenda, tarefas, e-mails — dados mockados) |
| `/remember <texto>` | Salva uma anotação/lembrete |
| `/memories` | Lista anotações recentes |
| Texto livre | Conversa com o assistente via OpenAI |

## 1. Como rodar no Workspace (desenvolvimento)

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
| `APP_BASE_URL` | Sim (para webhook) | URL pública do app (ex: `https://jarvis-pessoal.replit.app`) |
| `GOOGLE_CLIENT_ID` | Fase 3 | Client ID do Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Fase 3 | Client Secret do Google OAuth |
| `GOOGLE_REDIRECT_URI` | Fase 3 | URI de callback do Google OAuth |
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

O endpoint que recebe os updates é `POST /webhooks/telegram`. Ele valida o header `X-Telegram-Bot-Api-Secret-Token` contra o secret configurado.

### Testando comandos no Telegram

1. Configure o webhook apontando para o Replit
2. Abra o chat com seu bot no Telegram
3. Envie `/start` — deve receber mensagem de boas-vindas
4. Envie `/myday` — deve receber resumo do dia
5. Envie `/remember Comprar leite` — deve confirmar que salvou
6. Envie `/memories` — deve listar a anotação salva
7. Envie texto livre — deve receber resposta da IA (requer `OPENAI_API_KEY`)

## 2. Como publicar (deploy always-on)

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

**Lembre-se**: no Replit, o servidor deve sempre escutar em `0.0.0.0` e apenas uma porta é exposta externamente.

### Pós-deploy

1. Configure o webhook do Telegram apontando para a URL de produção
2. Verifique o endpoint `/health` para confirmar que está funcionando

## Roadmap

### Fase 2 (atual) ✅
- Bot Telegram funcional com comandos e texto livre
- Integração real com OpenAI (Responses API + function calling)
- Memória local em SQLite (anotações, conversas, histórico)
- Idempotência por update_id
- Segurança: webhook secret + filtro por user_id
- Limite de tool call rounds para evitar loops (padrão: 3)

### Fase 3 (futuro)
- Google Calendar (eventos reais)
- Gmail (e-mails reais)
- Google Tasks (tarefas reais)
- Transcrição de voz via OpenAI Whisper
- Ações com aprovação explícita (enviar e-mail, criar evento, etc.)
