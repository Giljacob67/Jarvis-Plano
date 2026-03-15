# Jarvis Pessoal

Personal productivity assistant API built with Python and FastAPI.

Integrates (when fully implemented) with Telegram, OpenAI, Google Calendar, Gmail, and Google Tasks.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check — returns `{"status": "ok"}` |
| GET | `/me/day` | Day overview with calendar events, tasks, and priority emails (mocked) |
| POST | `/webhooks/telegram` | Receives Telegram webhook updates |
| GET | `/auth/google/start` | Starts Google OAuth flow (stub — returns 501) |
| GET | `/auth/google/callback` | Google OAuth callback (stub — returns 501) |

## 1. Como rodar no Workspace (desenvolvimento)

### Pré-requisitos

O projeto já vem configurado para rodar no Replit. As dependências Python são instaladas automaticamente.

### Secrets no Replit

Cadastre os seguintes Secrets no painel do Replit (Tools > Secrets):

| Secret | Obrigatório? | Descrição |
|--------|:---:|-----------|
| `TELEGRAM_BOT_TOKEN` | Sim | Token do bot do Telegram (obtido via @BotFather) |
| `TELEGRAM_WEBHOOK_SECRET` | Sim | String secreta para validar webhooks do Telegram |
| `TELEGRAM_ALLOWED_USER_ID` | Recomendado | Seu user ID do Telegram para filtrar mensagens |
| `OPENAI_API_KEY` | Futuro | Chave da API OpenAI |
| `GOOGLE_CLIENT_ID` | Futuro | Client ID do Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Futuro | Client Secret do Google OAuth |
| `GOOGLE_REDIRECT_URI` | Futuro | URI de callback do Google OAuth |
| `APP_BASE_URL` | Futuro | URL pública do app (para configurar webhooks) |
| `APP_ENV` | Opcional | `development` (padrão) ou `production` |
| `TIMEZONE` | Opcional | Fuso horário, padrão `America/Sao_Paulo` |
| `JARVIS_DATABASE_URL` | Opcional | Padrão `sqlite:///./jarvis.db` |

### Rodando

O workflow está configurado para executar:

```
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Basta iniciar o workflow "Jarvis Pessoal" no Replit. O servidor estará disponível em `https://<seu-repl>.replit.dev`.

### Testes

```bash
pytest tests/ -v
```

### Webhook do Telegram

Para configurar o webhook do Telegram, use o endpoint:

```
POST https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook
```

Com o body:

```json
{
  "url": "https://<APP_BASE_URL>/webhooks/telegram",
  "secret_token": "<TELEGRAM_WEBHOOK_SECRET>"
}
```

O endpoint que recebe os updates é `POST /webhooks/telegram`. Ele valida o header `X-Telegram-Bot-Api-Secret-Token` contra o secret configurado.

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

### Pós-deploy

1. Configure o webhook do Telegram apontando para a URL de produção
2. Verifique o endpoint `/health` para confirmar que está funcionando
