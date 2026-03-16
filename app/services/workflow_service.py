import json
import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models.workflow_run import WorkflowRun
from app.models.action_log import ActionLog
from app.services.approval_service import create_pending_approval
from app.services.proactive_service import create_suggestion
from app.services.memory_service import save_memory

logger = logging.getLogger(__name__)

AVAILABLE_PLAYBOOKS = {
    "website_research": {
        "name": "website_research",
        "description": "Abre uma URL, captura screenshot e extrai texto resumido da página",
        "params": "url",
        "example": "/runworkflow website_research | https://example.com",
    },
    "form_prep": {
        "name": "form_prep",
        "description": "Abre uma página, preenche campos de formulário e aguarda aprovação antes de submeter",
        "params": "url | campo1=valor1 | campo2=valor2",
        "example": "/runworkflow form_prep | https://example.com/form | name=João | email=joao@x.com",
    },
    "portal_check": {
        "name": "portal_check",
        "description": "Abre um portal, navega e extrai dados — pausa se detectar login",
        "params": "url",
        "example": "/runworkflow portal_check | https://meuportal.com.br",
    },
    "file_collect": {
        "name": "file_collect",
        "description": "Abre uma página, faz download de arquivo e registra como artefato",
        "params": "url | seletor_download",
        "example": "/runworkflow file_collect | https://example.com/relatorio | a.download-btn",
    },
    "lead_followup": {
        "name": "lead_followup",
        "description": "Cria tarefa, rascunho de e-mail e lembrete de follow-up para um lead",
        "params": "empresa | email | contexto",
        "example": "/runworkflow lead_followup | Empresa X | contato@x.com | follow-up da proposta",
    },
    "meeting_prep": {
        "name": "meeting_prep",
        "description": "Prepara briefing para a próxima reunião: contexto, pauta sugerida e e-mails relacionados",
        "params": "(nenhum — usa o próximo evento da agenda)",
        "example": "/runworkflow meeting_prep",
    },
    "inbox_triage": {
        "name": "inbox_triage",
        "description": "Analisa e-mails prioritários, resume e sugere respostas (nunca envia sem aprovação)",
        "params": "(nenhum — analisa inbox automaticamente)",
        "example": "/runworkflow inbox_triage",
    },
}


def _log_action(db: Session, event_type: str, status: str, details: dict) -> None:
    entry = ActionLog(
        event_type=event_type,
        status=status,
        details_json=json.dumps(details, ensure_ascii=False),
    )
    db.add(entry)
    db.commit()


def _create_workflow_run(db: Session, user_id: str, workflow_name: str, input_data: dict | None = None) -> WorkflowRun:
    run = WorkflowRun(
        user_id=user_id,
        workflow_name=workflow_name,
        status="running",
        input_json=json.dumps(input_data, ensure_ascii=False) if input_data else None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _complete_workflow_run(db: Session, run: WorkflowRun, status: str, output: dict | None = None) -> None:
    run.status = status
    run.output_json = json.dumps(output, ensure_ascii=False) if output else None
    db.commit()


async def run_workflow(db: Session, user_id: str, workflow_name: str, params: list[str] | None = None) -> str:
    if workflow_name not in AVAILABLE_PLAYBOOKS:
        available = ", ".join(AVAILABLE_PLAYBOOKS.keys())
        return f"❌ Workflow '{workflow_name}' não encontrado. Disponíveis: {available}"

    params = params or []

    if workflow_name == "website_research":
        return await _run_website_research(db, user_id, params)
    elif workflow_name == "form_prep":
        return await _run_form_prep(db, user_id, params)
    elif workflow_name == "portal_check":
        return await _run_portal_check(db, user_id, params)
    elif workflow_name == "file_collect":
        return await _run_file_collect(db, user_id, params)
    elif workflow_name == "lead_followup":
        return await _run_lead_followup(db, user_id, params)
    elif workflow_name == "meeting_prep":
        return await _run_meeting_prep(db, user_id, params)
    elif workflow_name == "inbox_triage":
        return await _run_inbox_triage(db, user_id, params)

    return "❌ Workflow não implementado."


async def _run_website_research(db: Session, user_id: str, params: list[str]) -> str:
    if not params:
        return (
            "❌ Parâmetros insuficientes.\n"
            "Uso: /runworkflow website_research | https://example.com"
        )
    url = params[0].strip()
    run = _create_workflow_run(db, user_id, "website_research", {"url": url})

    try:
        from app.services import browser_service
        result = await browser_service.start_session(db, user_id, url)
        if "error" in result:
            _complete_workflow_run(db, run, "failed", result)
            return f"❌ {result['error']}"
        session_id = result["session_id"]

        nav = await browser_service.open_url(db, user_id, session_id, url)
        if "error" in nav:
            await browser_service.close_session(db, user_id, session_id, reason="workflow_error")
            _complete_workflow_run(db, run, "failed", nav)
            return f"❌ {nav['error']}"
        if nav.get("status") == "paused_for_login":
            _complete_workflow_run(db, run, "paused", nav)
            return nav["message"]

        screen = await browser_service.capture_screenshot(db, user_id, session_id)
        text_result = await browser_service.extract_visible_text(db, user_id, session_id)

        await browser_service.close_session(db, user_id, session_id, reason="workflow_done")

        lines = [
            "🔍 *Workflow: Website Research*\n",
            f"🌐 URL: {url}",
            f"📄 Título: {nav.get('title', '?')}\n",
        ]
        if "error" not in screen:
            lines.append(f"📸 Screenshot salvo: `{screen.get('file_path', '')}`")
        if "error" not in text_result:
            lines.append(f"\n📝 *Conteúdo resumido:*\n{text_result.get('text', '')[:1500]}")
        else:
            lines.append(f"⚠️ Não foi possível extrair texto: {text_result.get('error', '')}")

        output_msg = "\n".join(lines)
        _complete_workflow_run(db, run, "completed", {"message": output_msg})
        _log_action(db, "workflow_completed", "success", {"workflow": "website_research", "user_id": user_id})
        return output_msg

    except Exception as e:
        logger.exception("website_research workflow failed")
        _complete_workflow_run(db, run, "failed", {"error": str(e)})
        return f"❌ Erro no workflow website_research: {e}"


async def _run_form_prep(db: Session, user_id: str, params: list[str]) -> str:
    if not params:
        return (
            "❌ Parâmetros insuficientes.\n"
            "Uso: /runworkflow form_prep | url | campo1=valor1 | campo2=valor2"
        )
    url = params[0].strip()
    fields: dict[str, str] = {}
    for p in params[1:]:
        if "=" in p:
            k, _, v = p.partition("=")
            fields[k.strip()] = v.strip()

    run = _create_workflow_run(db, user_id, "form_prep", {"url": url, "fields": fields})

    try:
        from app.services import browser_service
        result = await browser_service.start_session(db, user_id, url)
        if "error" in result:
            _complete_workflow_run(db, run, "failed", result)
            return f"❌ {result['error']}"
        session_id = result["session_id"]

        nav = await browser_service.open_url(db, user_id, session_id, url)
        if "error" in nav:
            await browser_service.close_session(db, user_id, session_id, reason="workflow_error")
            _complete_workflow_run(db, run, "failed", nav)
            return f"❌ {nav['error']}"
        if nav.get("status") == "paused_for_login":
            _complete_workflow_run(db, run, "paused", nav)
            return nav["message"]

        fill_results = []
        for selector, value in fields.items():
            fr = await browser_service.fill(db, user_id, session_id, selector, value)
            fill_err = fr.get("error", "")
            fill_icon = "✅" if "error" not in fr else f"❌ {fill_err}"
            fill_results.append(f"  • `{selector}`: {fill_icon}")

        screen = await browser_service.capture_screenshot(db, user_id, session_id)

        from app.services.approval_service import create_pending_approval
        approval = create_pending_approval(
            db, user_id,
            action_type="browser_submit_form",
            title=f"Submeter formulário em {url}",
            summary=f"Campos preenchidos: {list(fields.keys())}\nURL: {url}",
            payload={"session_id": session_id, "action_type": "browser_submit_form",
                     "selector": "button[type=submit]", "value": None,
                     "current_url": nav.get("url", url), "screenshot_path": screen.get("file_path")},
            source="workflow:form_prep",
        )

        lines = [
            "📋 *Workflow: Form Prep*\n",
            f"🌐 URL: {url}",
            f"📄 Título: {nav.get('title', '?')}\n",
            "✏️ *Campos preenchidos:*",
        ]
        lines.extend(fill_results)
        if approval:
            lines.append(f"\n⏳ Aguardando aprovação #{approval.id} para submeter o formulário.")
            lines.append(f"Use /approve {approval.id} para confirmar ou /reject {approval.id} para cancelar.")
        else:
            lines.append("\n⚠️ Não foi possível criar aprovação para submissão. Sessão mantida aberta.")

        output_msg = "\n".join(lines)
        _complete_workflow_run(db, run, "pending_approval", {"message": output_msg})
        _log_action(db, "workflow_completed", "success", {"workflow": "form_prep", "user_id": user_id})
        return output_msg

    except Exception as e:
        logger.exception("form_prep workflow failed")
        _complete_workflow_run(db, run, "failed", {"error": str(e)})
        return f"❌ Erro no workflow form_prep: {e}"


async def _run_portal_check(db: Session, user_id: str, params: list[str]) -> str:
    if not params:
        return (
            "❌ Parâmetros insuficientes.\n"
            "Uso: /runworkflow portal_check | https://meuportal.com.br"
        )
    url = params[0].strip()
    run = _create_workflow_run(db, user_id, "portal_check", {"url": url})

    try:
        from app.services import browser_service
        result = await browser_service.start_session(db, user_id, url)
        if "error" in result:
            _complete_workflow_run(db, run, "failed", result)
            return f"❌ {result['error']}"
        session_id = result["session_id"]

        nav = await browser_service.open_url(db, user_id, session_id, url)
        if "error" in nav:
            await browser_service.close_session(db, user_id, session_id, reason="workflow_error")
            _complete_workflow_run(db, run, "failed", nav)
            return f"❌ {nav['error']}"

        if nav.get("status") == "paused_for_login":
            _complete_workflow_run(db, run, "paused", nav)
            return nav["message"]

        text_result = await browser_service.extract_visible_text(db, user_id, session_id)
        screen = await browser_service.capture_screenshot(db, user_id, session_id)
        await browser_service.close_session(db, user_id, session_id, reason="workflow_done")

        lines = [
            "🏢 *Workflow: Portal Check*\n",
            f"🌐 URL: {url}",
            f"📄 Título: {nav.get('title', '?')}\n",
        ]
        if "error" not in screen:
            lines.append(f"📸 Screenshot: `{screen.get('file_path', '')}`")
        if "error" not in text_result:
            lines.append(f"\n📝 *Dados extraídos:*\n{text_result.get('text', '')[:1500]}")
        else:
            lines.append(f"⚠️ {text_result.get('error', '')}")

        output_msg = "\n".join(lines)
        _complete_workflow_run(db, run, "completed", {"message": output_msg})
        _log_action(db, "workflow_completed", "success", {"workflow": "portal_check", "user_id": user_id})
        return output_msg

    except Exception as e:
        logger.exception("portal_check workflow failed")
        _complete_workflow_run(db, run, "failed", {"error": str(e)})
        return f"❌ Erro no workflow portal_check: {e}"


async def _run_file_collect(db: Session, user_id: str, params: list[str]) -> str:
    if len(params) < 2:
        return (
            "❌ Parâmetros insuficientes.\n"
            "Uso: /runworkflow file_collect | https://example.com/relatorio | a.download-btn"
        )
    url = params[0].strip()
    trigger_selector = params[1].strip()
    run = _create_workflow_run(db, user_id, "file_collect", {"url": url, "selector": trigger_selector})

    try:
        from app.services import browser_service
        result = await browser_service.start_session(db, user_id, url)
        if "error" in result:
            _complete_workflow_run(db, run, "failed", result)
            return f"❌ {result['error']}"
        session_id = result["session_id"]

        nav = await browser_service.open_url(db, user_id, session_id, url)
        if "error" in nav:
            await browser_service.close_session(db, user_id, session_id, reason="workflow_error")
            _complete_workflow_run(db, run, "failed", nav)
            return f"❌ {nav['error']}"
        if nav.get("status") == "paused_for_login":
            _complete_workflow_run(db, run, "paused", nav)
            return nav["message"]

        dl = await browser_service.download_file(db, user_id, session_id, trigger_selector)
        await browser_service.close_session(db, user_id, session_id, reason="workflow_done")

        if "error" in dl:
            _complete_workflow_run(db, run, "failed", dl)
            return f"❌ Erro ao baixar arquivo: {dl['error']}"

        lines = [
            "📥 *Workflow: File Collect*\n",
            f"🌐 URL: {url}",
            f"✅ Arquivo baixado: `{dl.get('file_path', '')}`",
            f"📦 Tamanho: {dl.get('size_bytes', '?')} bytes",
            f"🗂 Artefato registrado (ID: {dl.get('artifact_id', '?')})",
        ]
        output_msg = "\n".join(lines)
        _complete_workflow_run(db, run, "completed", {"message": output_msg, "file_path": dl.get("file_path")})
        _log_action(db, "workflow_completed", "success", {"workflow": "file_collect", "user_id": user_id})
        return output_msg

    except Exception as e:
        logger.exception("file_collect workflow failed")
        _complete_workflow_run(db, run, "failed", {"error": str(e)})
        return f"❌ Erro no workflow file_collect: {e}"


async def _run_lead_followup(db: Session, user_id: str, params: list[str]) -> str:
    if len(params) < 2:
        return (
            "❌ Parâmetros insuficientes.\n"
            "Uso: /runworkflow lead_followup | empresa | email | contexto\n"
            "Exemplo: /runworkflow lead_followup | Empresa X | contato@x.com | follow-up da proposta"
        )

    company = params[0].strip()
    email = params[1].strip()
    context = params[2].strip() if len(params) > 2 else f"Follow-up com {company}"

    run = _create_workflow_run(db, user_id, "lead_followup", {
        "company": company, "email": email, "context": context,
    })

    try:
        from app.services import google_oauth_service
        status = google_oauth_service.get_status(db, user_id)
        connected = status.get("connected", False)

        task_result = "⚠️ Google não conectado — tarefa não criada"
        if connected:
            from app.services import google_tasks as google_tasks_service
            due_date = (date.today() + timedelta(days=settings.followup_default_days)).isoformat()
            result = await google_tasks_service.create_task(
                db, user_id,
                title=f"Follow-up: {company} — {context}",
                notes=f"Contato: {email}\n{context}",
                due=due_date,
            )
            if "error" not in result:
                task_result = f"✅ Tarefa criada: '{result.get('title', '')}' (vence: {due_date})"
            else:
                task_result = f"⚠️ Erro ao criar tarefa: {result['error']}"

        draft_result = "⚠️ Gmail não disponível — rascunho não criado"
        draft_id = None
        if connected and status.get("gmail_enabled"):
            from app.services import google_gmail_service
            subject = f"Follow-up: {context}"
            body = (
                f"Olá,\n\n"
                f"Gostaria de dar seguimento à nossa conversa sobre {context}.\n\n"
                f"Fico à disposição para agendar uma próxima conversa.\n\n"
                f"Atenciosamente"
            )
            result = await google_gmail_service.create_draft(
                db, user_id, to=email, subject=subject, body=body,
            )
            if "error" not in result:
                draft_id = result.get("draft_id", "")
                draft_result = f"✅ Rascunho criado (ID: {draft_id})"
            else:
                draft_result = f"⚠️ Erro ao criar rascunho: {result['error']}"

        if draft_id:
            create_pending_approval(
                db, user_id,
                action_type="send_email_draft",
                title=f"Enviar follow-up para {company}",
                summary=f"E-mail de follow-up para {email} sobre: {context}",
                payload={"draft_id": draft_id, "to": email, "subject": f"Follow-up: {context}"},
                source="workflow:lead_followup",
                idempotency_key=f"lead_followup_{email}_{date.today().isoformat()}",
            )

        save_memory(db, user_id, f"Follow-up pendente: {company} ({email}) — {context}", category="followup", source="workflow")

        lines = [
            f"🔄 *Workflow: Lead Follow-up*\n",
            f"🏢 Empresa: {company}",
            f"📧 Contato: {email}",
            f"📝 Contexto: {context}\n",
            f"📋 {task_result}",
            f"✉️ {draft_result}",
        ]
        if draft_id:
            lines.append(f"⏳ Aprovação criada para envio do rascunho (use /approvals para ver)")
        lines.append(f"\n🧠 Lembrete salvo na memória")

        output_msg = "\n".join(lines)
        _complete_workflow_run(db, run, "completed", {"message": output_msg})
        _log_action(db, "workflow_completed", "success", {"workflow": "lead_followup", "user_id": user_id})
        return output_msg

    except Exception as e:
        logger.exception("lead_followup workflow failed")
        _complete_workflow_run(db, run, "failed", {"error": str(e)})
        return f"❌ Erro no workflow lead_followup: {e}"


async def _run_meeting_prep(db: Session, user_id: str, params: list[str]) -> str:
    run = _create_workflow_run(db, user_id, "meeting_prep", {"params": params})

    try:
        from app.services import google_oauth_service
        from app.services import google_calendar as google_calendar_service

        status = google_oauth_service.get_status(db, user_id)
        if not status.get("connected"):
            msg = "❌ Google não conectado. Use /connectgoogle para conectar."
            _complete_workflow_run(db, run, "failed", {"error": msg})
            return msg

        events = await google_calendar_service.list_upcoming_events(
            db, user_id, days=2, limit=5, tz=settings.default_timezone,
        )
        if not events:
            msg = "📆 Nenhum evento próximo encontrado."
            _complete_workflow_run(db, run, "completed", {"message": msg})
            return msg

        next_event = events[0]
        lines = [
            "📋 *Workflow: Meeting Prep*\n",
            f"📆 *Próximo evento:* {next_event.get('title', '?')}",
            f"⏰ {next_event.get('start', '')} — {next_event.get('end', '')}",
        ]
        if next_event.get("location"):
            lines.append(f"📍 {next_event['location']}")
        if next_event.get("description"):
            lines.append(f"\n📝 *Descrição:*\n{next_event['description'][:300]}")

        from app.services.memory_service import get_memories_by_context
        memories = get_memories_by_context(db, user_id, ["project", "contact", "decision"], limit=5)
        if memories:
            lines.append("\n🧠 *Contexto relevante:*")
            for m in memories[:3]:
                lines.append(f"  • [{m.category}] {m.content[:100]}")

        lines.append("\n📌 *Pauta sugerida:*")
        lines.append("  1. Alinhamento de objetivos")
        lines.append("  2. Status de pendências")
        lines.append("  3. Próximos passos e prazos")

        if status.get("gmail_enabled"):
            title = next_event.get("title", "")
            if title:
                from app.services import google_gmail_service
                try:
                    search_result = await google_gmail_service.search_emails(
                        db, user_id, query=title, max_results=3,
                    )
                    related = search_result.get("messages", [])
                    if related:
                        lines.append(f"\n📧 *{len(related)} e-mail(s) relacionados:*")
                        for m in related[:3]:
                            lines.append(f"  • {m.get('subject', '?')} (de {m.get('from', '?')[:30]})")
                except Exception:
                    logger.exception("meeting_prep: failed to search emails")

        output_msg = "\n".join(lines)
        _complete_workflow_run(db, run, "completed", {"message": output_msg})
        _log_action(db, "workflow_completed", "success", {"workflow": "meeting_prep", "user_id": user_id})
        return output_msg

    except Exception as e:
        logger.exception("meeting_prep workflow failed")
        _complete_workflow_run(db, run, "failed", {"error": str(e)})
        return f"❌ Erro no workflow meeting_prep: {e}"


async def _run_inbox_triage(db: Session, user_id: str, params: list[str]) -> str:
    run = _create_workflow_run(db, user_id, "inbox_triage", {"params": params})

    try:
        from app.services import google_oauth_service
        from app.services import google_gmail_service

        status = google_oauth_service.get_status(db, user_id)
        if not status.get("connected") or not status.get("gmail_enabled"):
            msg = "❌ Gmail não conectado ou não autorizado. Use /connectgoogle."
            _complete_workflow_run(db, run, "failed", {"error": msg})
            return msg

        priority_emails = await google_gmail_service.get_priority_emails(db, user_id, max_results=5)
        if not priority_emails:
            msg = "📧 Inbox limpa! Nenhum e-mail prioritário encontrado."
            _complete_workflow_run(db, run, "completed", {"message": msg})
            return msg

        lines = [
            f"📧 *Workflow: Inbox Triage*\n",
            f"Encontrados *{len(priority_emails)} e-mail(s) prioritário(s):*\n",
        ]

        for i, m in enumerate(priority_emails, 1):
            sender = m.get("from", "?")
            if "<" in sender:
                sender = sender.split("<")[0].strip().strip('"')
            subject = m.get("subject", "(sem assunto)")
            snippet = m.get("snippet", "")[:100]

            lines.append(f"*{i}. {subject}*")
            lines.append(f"   De: {sender}")
            if snippet:
                lines.append(f"   _{snippet}_")

            create_suggestion(
                db, user_id,
                suggestion_type="email_response",
                title=f"Responder: {subject}",
                body=f"E-mail de {sender}: {snippet}",
                source="workflow:inbox_triage",
            )
            lines.append("")

        lines.append("💡 Sugestões de resposta foram criadas. Nenhum e-mail será enviado sem sua aprovação.")
        lines.append("Use /approvals para ver ações pendentes.")

        output_msg = "\n".join(lines)
        _complete_workflow_run(db, run, "completed", {"message": output_msg})
        _log_action(db, "workflow_completed", "success", {"workflow": "inbox_triage", "user_id": user_id})
        return output_msg

    except Exception as e:
        logger.exception("inbox_triage workflow failed")
        _complete_workflow_run(db, run, "failed", {"error": str(e)})
        return f"❌ Erro no workflow inbox_triage: {e}"


def list_playbooks() -> str:
    lines = ["📚 *Playbooks disponíveis:*\n"]
    for name, info in AVAILABLE_PLAYBOOKS.items():
        lines.append(f"*{name}*")
        lines.append(f"  {info['description']}")
        lines.append(f"  Parâmetros: {info['params']}")
        lines.append(f"  Exemplo: `{info['example']}`")
        lines.append("")
    lines.append("Use: /runworkflow <nome> | param1 | param2 | ...")
    return "\n".join(lines)
