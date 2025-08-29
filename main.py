import os
import re
import json
import shlex
import shutil
import subprocess
import datetime
import smtplib
import ssl
from email.message import EmailMessage
from html import escape

# =====================================================================
# Destinatários: SOMENTE via constants.py
# =====================================================================
try:
    from constants import EMAIL_RECIPIENTS
except Exception:
    EMAIL_RECIPIENTS = []

# =====================================================================
# .env (SMTP e outras configs, mas NÃO para destinatários)
# =====================================================================
def load_dotenv(path=".env"):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r'^([A-Za-z0-9_]+)\s*=\s*(.*)$', line)
            if not m:
                continue
            k, v = m.group(1), m.group(2)
            if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
                v = v[1:-1]
            env[k] = v
    for k, v in env.items():
        os.environ.setdefault(k, v)
    return env

# =====================================================================
# Shell helpers
# =====================================================================
def run(cmd: str, cwd: str = None):
    return subprocess.run(
        shlex.split(cmd),
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

def which_postman():
    return shutil.which("postman")

def postman_whoami_ok():
    proc = run("postman whoami")
    return proc.returncode == 0

def postman_login_if_needed():
    api_key = os.getenv("POSTMAN_API_KEY", "")
    if postman_whoami_ok():
        return
    if api_key:
        _ = run(f'postman login --with-api-key "{api_key}"')

# =====================================================================
# Descoberta (raiz/collections/<proj>/{enviroment,requests})
# =====================================================================
def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def list_projects(root: str):
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        base = os.path.join(root, name)
        if os.path.isdir(os.path.join(base, "requests")) and os.path.isdir(os.path.join(base, "enviroment")):
            out.append(name)
    return out

def list_jsons(folder: str):
    if not os.path.isdir(folder):
        return []
    return sorted([os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".json")])

def find_all_pairs(root: str):
    plan = []
    for proj in list_projects(root):
        base = os.path.join(root, proj)
        reqs = list_jsons(os.path.join(base, "requests"))
        envs = list_jsons(os.path.join(base, "enviroment"))
        for r in reqs:
            for e in envs:
                plan.append({"project": proj, "collection": r, "environment": e})
    return plan

def find_pairs_for_project(root: str, project: str, env_path: str = None):
    base = os.path.join(root, project)
    reqs = list_jsons(os.path.join(base, "requests"))
    envs = list_jsons(os.path.join(base, "enviroment"))
    if env_path:
        envs = [env_path]
    plan = []
    for r in reqs:
        for e in envs:
            plan.append({"project": project, "collection": r, "environment": e})
    return plan

def env_label_from_path(env_path: str) -> str:
    base = os.path.basename(env_path)
    return os.path.splitext(base)[0]

def strip_ansi(s: str) -> str:
    ansi = re.compile(r'\x1B\[[0-9;]*[mK]')
    return ansi.sub('', s)

# =====================================================================
# Execução (ABS paths)
# =====================================================================
def run_collection(collection_path: str, environment_path: str, out_dir: str):
    collection_abs = os.path.abspath(collection_path)
    env_abs = os.path.abspath(environment_path)
    out_dir_abs = os.path.abspath(out_dir)
    ensure_dir(out_dir_abs)
    out_json = os.path.join(out_dir_abs, "run.json")
    out_txt  = os.path.join(out_dir_abs, "cli.log.txt")
    cmd = (
        f'postman collection run "{collection_abs}" '
        f'-e "{env_abs}" '
        f'--reporters cli,json '
        f'--reporter-json-export "{out_json}"'
    )
    proc = run(cmd)
    # salva stdout/stderr limpos (sem ANSI)
    try:
        with open(out_txt, "w", encoding="utf-8", errors="replace") as f:
            f.write(strip_ansi(proc.stdout or ""))
            if proc.stderr:
                f.write("\n\n[STDERR]\n")
                f.write(strip_ansi(proc.stderr))
    except Exception:
        out_txt = None

    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "report_path": out_json if os.path.exists(out_json) else None,
        "stdout_path": out_txt if out_txt and os.path.exists(out_txt) else None
    }

# =====================================================================
# Parser de STDOUT (CLI bonito)
# =====================================================================
def parse_cli_stdout(stdout: str):
    if not stdout:
        return []
    s = strip_ansi(stdout)
    lines = [ln.rstrip() for ln in s.splitlines()]
    out, cur = [], None

    re_req = re.compile(r'^\s*→\s+(.*)$')                 # "→ Nome"
    re_test_ok = re.compile(r'^\s*[√✓]\s+(.*)$')          # passed
    re_test_fail = re.compile(r'^\s*[×✗]\s+(.*)$')        # failed
    re_status = re.compile(r'\[(\d{3})\s+[^\]]+\]')       # "[200 OK, ...]"

    for ln in lines:
        m = re_req.match(ln)
        if m:
            if cur:
                out.append(cur)
            cur = {"name": m.group(1).strip(), "status_code": None, "tests": []}
            continue

        if cur:
            m2 = re_status.search(ln)
            if m2:
                try:
                    cur["status_code"] = int(m2.group(1))
                except Exception:
                    pass
                continue
            m3 = re_test_ok.match(ln.strip())
            if m3:
                cur["tests"].append({"name": m3.group(1).strip(), "ok": True})
                continue
            m4 = re_test_fail.match(ln.strip())
            if m4:
                cur["tests"].append({"name": m4.group(1).strip(), "ok": False})
                continue

    if cur:
        out.append(cur)
    return out

# =====================================================================
# Resumo (JSON + fallback stdout)
# =====================================================================
def _safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def summarize_run(report_path: str, stdout_text: str) -> dict:
    items = []
    total_requests = failed_requests = total_tests = failed_tests = 0
    reason = None

    data = None
    if report_path and os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except Exception as e:
            reason = f"falha ao ler run.json: {e}"

    if data:
        run_info = data.get("run", {}) if isinstance(data, dict) else {}
        # Formato novo: run.summary + run.executions[*].tests
        summary = run_info.get("summary")
        executions = run_info.get("executions")
        if isinstance(summary, dict) and isinstance(executions, list):
            total_requests = int(_safe_get(summary, "executedRequests", "executed", default=0) or 0)
            total_tests    = int(_safe_get(summary, "tests", "executed", default=0) or 0)
            failed_tests   = int(_safe_get(summary, "tests", "failed", default=0) or 0)
            failed_requests = 0
            for ex in executions:
                req = ex.get("requestExecuted") or ex.get("request") or {}
                name = req.get("name") or "desconhecido"
                status_code = None
                resp = ex.get("response") or {}
                code = resp.get("code")
                if isinstance(code, int):
                    status_code = code
                tests = []
                for t in ex.get("tests") or []:
                    tname = t.get("name") or "teste"
                    ok = (t.get("status") == "passed")
                    tests.append({"name": tname, "ok": ok})
                    if not ok:
                        failed_tests += 1
                items.append({"name": name, "status_code": status_code, "tests": tests})
        else:
            # Formato antigo: run.stats + run.executions[*].assertions
            stats = run_info.get("stats", {})
            total_requests = int(_safe_get(stats, "requests", "total", default=0) or 0)
            failed_requests = int(_safe_get(stats, "requests", "failed", default=0) or 0)
            total_tests = int(_safe_get(stats, "tests", "total", default=0) or 0)
            failed_tests = int(_safe_get(stats, "tests", "failed", default=0) or 0)
            for ex in run_info.get("executions") or []:
                item = ex.get("item", {}) or {}
                name = item.get("name") or "desconhecido"
                status_code = None
                resp = (ex.get("response") or {})
                if isinstance(resp, dict):
                    try:
                        status_code = int(resp.get("code"))
                    except Exception:
                        status_code = None
                tests = []
                for a in ex.get("assertions") or []:
                    tname = a.get("assertion") or "teste"
                    ok = not bool(a.get("error"))
                    tests.append({"name": tname, "ok": ok})
                items.append({"name": name, "status_code": status_code, "tests": tests})

    # Completa com stdout (nome, status e testes bonitos)
    stdout_items = parse_cli_stdout(stdout_text or "")
    if stdout_items:
        by_name = {it["name"]: it for it in items if it.get("name")}
        for s in stdout_items:
            base = by_name.get(s["name"])
            if base:
                if base.get("status_code") is None and s.get("status_code") is not None:
                    base["status_code"] = s["status_code"]
                already = {t["name"] for t in base.get("tests", [])}
                for t in s.get("tests", []):
                    if t["name"] not in already:
                        base.setdefault("tests", []).append(t)
            else:
                items.append(s)

    if items:
        total_requests = max(total_requests, len(items))
        if total_tests == 0:
            total_tests = sum(len(i.get("tests", [])) for i in items)
        if failed_tests == 0:
            failed_tests = sum(1 for i in items for t in i.get("tests", []) if not t.get("ok", False))

    ok = (failed_requests == 0 and failed_tests == 0 and total_requests > 0 and total_tests >= 0)
    return {
        "ok": ok,
        "reason": reason or (None if total_requests > 0 else "sem requests contabilizados"),
        "total_requests": total_requests,
        "failed_requests": failed_requests,
        "total_tests": total_tests,
        "failed_tests": failed_tests,
        "items": items
    }

# =====================================================================
# Texto e HTML do relatório
# =====================================================================
def style_block_collection_text(title: str, summary: dict) -> str:
    status = "✅ OK" if summary.get("ok") else "❌ PROBLEMA"
    lines = [f"#### {title} — {status}"]
    lines.append(f"- Requests: {summary.get('total_requests',0)}")
    lines.append(f"- Tests: {summary.get('total_tests',0)} (falhas: {summary.get('failed_tests',0)})")
    if summary.get("reason"):
        lines.append(f"- Observação: {summary['reason']}")
    if summary.get("items"):
        lines.append("- Requisições e testes:")
        for it in summary["items"]:
            sc = it.get("status_code")
            sc_str = f"HTTP {sc}" if sc is not None else ""
            nm = it.get("name") or ""
            lines.append(f"  •  {nm} {sc_str}".rstrip())
            if it.get("tests"):
                for t in it["tests"]:
                    mark = "✓" if t.get("ok") else "✗"
                    lines.append(f"    {mark} {t.get('name')}")
            else:
                lines.append("    (sem testes definidos)")
    return "\n".join(lines)

def build_human_report(grouped_results: dict) -> str:
    lines = ["# Relatório de Execução (Postman CLI)", ""]
    for proj, envs in sorted(grouped_results.items()):
        lines.append(f"## {proj}")
        for env_label, items in sorted(envs.items()):
            lines.append(f"### Environment: {env_label}")
            for it in items:
                title = it["collection_name"]
                lines.append(style_block_collection_text(title, it["summary"]))
                lines.append("")
            lines.append("")
        lines.append("")
    lines.extend([
        "---",
        "### Dicas rápidas",
        "- Se **nenhum request** foi contado, confirme AUTH/ENV (tokens, URLs) e se a coleção não está filtrada por folder.",
        "- Se houver **exit code ≠ 0**, veja as últimas linhas do stderr acima para pistas imediatas.",
        "- Falhas de teste listam o *assert* que quebrou; ajuste o pre-request/headers/body ou o teste conforme necessário."
    ])
    return "\n".join(lines)

def _badge(ok: bool) -> str:
    color = "#16a34a" if ok else "#dc2626"
    text  = "OK" if ok else "FALHA"
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:9999px;background:{color};color:#fff;font:12px/1.4 system-ui,Segoe UI,Arial">{text}</span>'

def build_html_report(grouped_results: dict) -> str:
    html = [
        '<div style="font-family:system-ui,Segoe UI,Arial;font-size:14px;color:#0f172a">',
        '<h2 style="margin:0 0 12px">Relatório de Execução (Postman CLI)</h2>'
    ]
    for proj, envs in sorted(grouped_results.items()):
        html.append(f'<h3 style="margin:18px 0 6px">{escape(proj)}</h3>')
        for env_label, items in sorted(envs.items()):
            html.append(f'<h4 style="margin:12px 0 6px">Environment: {escape(env_label)}</h4>')
            for it in items:
                summ = it["summary"]
                ok = bool(summ.get("ok"))
                html.append('<div style="border:1px solid #e5e7eb;border-radius:12px;padding:12px;margin:8px 0">')
                html.append(f'<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:6px">'
                            f'<div style="font-weight:600">{escape(it["collection_name"])}</div>{_badge(ok)}</div>')
                html.append('<div style="color:#334155;margin-bottom:8px">')
                html.append(f'<div>Requests: <b>{summ.get("total_requests",0)}</b></div>')
                html.append(f'<div>Tests: <b>{summ.get("total_tests",0)}</b> (falhas: <b>{summ.get("failed_tests",0)}</b>)</div>')
                reason = summ.get("reason")
                if reason:
                    html.append(f'<div>Obs.: {escape(reason)}</div>')
                html.append('</div>')
                html.append('<table style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb">'
                            '<thead><tr>'
                            '<th style="text-align:left;padding:6px;border-bottom:1px solid #e5e7eb;background:#f8fafc">Request</th>'
                            '<th style="text-align:left;padding:6px;border-bottom:1px solid #e5e7eb;background:#f8fafc">HTTP</th>'
                            '<th style="text-align:left;padding:6px;border-bottom:1px solid #e5e7eb;background:#f8fafc">Testes</th>'
                            '</tr></thead><tbody>')
                for it2 in summ.get("items", []):
                    nm  = escape(it2.get("name") or "")
                    sc  = it2.get("status_code")
                    scs = str(sc) if sc is not None else "-"
                    tests = it2.get("tests") or []
                    if tests:
                        tests_html = "<ul style='margin:6px 0;padding-left:18px'>"
                        for t in tests:
                            li_badge = _badge(bool(t.get("ok")))
                            tests_html += f"<li>{li_badge} {escape(t.get('name') or '')}</li>"
                        tests_html += "</ul>"
                    else:
                        tests_html = "<em>(sem testes definidos)</em>"
                    html.append(f"<tr>"
                                f"<td style='vertical-align:top;padding:6px;border-bottom:1px solid #f1f5f9'>{nm}</td>"
                                f"<td style='vertical-align:top;padding:6px;border-bottom:1px solid #f1f5f9'>{scs}</td>"
                                f"<td style='vertical-align:top;padding:6px;border-bottom:1px solid #f1f5f9'>{tests_html}</td>"
                                f"</tr>")
                html.append('</tbody></table>')
                html.append('</div>')
    html.append('<p style="margin-top:12px;color:#64748b">Gerado automaticamente.</p>')
    html.append('</div>')
    return "".join(html)

# =====================================================================
# E-mail (SSL 465 ou STARTTLS) — destinatários SOMENTE constants.EMAIL_RECIPIENTS
# =====================================================================
def send_mail(subject: str, body_md: str, body_html: str, attachments: list, cfg: dict) -> bool:
    must = ("SMTP_HOST","SMTP_USER","SMTP_PASS","MAIL_FROM")
    if not all(cfg.get(k) for k in must):
        print("E-mail: configuração SMTP incompleta.")
        return False

    recipients = EMAIL_RECIPIENTS or []
    if not recipients:
        print("E-mail: nenhum destinatário definido em constants.EMAIL_RECIPIENTS.")
        return False

    msg = EmailMessage()
    msg["From"] = cfg["MAIL_FROM"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg["Reply-To"] = cfg["MAIL_FROM"]
    msg["X-Automation"] = "Automatest-Postman-CLI"
    msg.set_content(body_md or "Relatório em HTML anexo.")
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    for path in attachments or []:
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            fname = os.path.basename(path)
            if fname.endswith(".json"):
                maintype, subtype = "application", "json"
            elif fname.endswith(".txt"):
                maintype, subtype = "text", "plain"
            else:
                maintype, subtype = "application", "octet-stream"
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=fname)

    host = cfg["SMTP_HOST"]; port = int(cfg.get("SMTP_PORT","465"))
    try:
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context) as server:
                server.login(cfg["SMTP_USER"], cfg["SMTP_PASS"])
                resp = server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                if str(cfg.get("SMTP_USE_TLS","true")).lower() in ("1","true","yes","y"):
                    server.starttls(context=ssl.create_default_context())
                server.login(cfg["SMTP_USER"], cfg["SMTP_PASS"])
                resp = server.send_message(msg)

        if resp:  # dicionário de rejeitados
            print("E-mail: destinatários rejeitados:", resp)
            return False
        return True
    except Exception as e:
        print("E-mail: erro de envio:", e)
        return False

# =====================================================================
# UI Terminal
# =====================================================================
def prompt_menu(options, title="Como deseja executar?"):
    print(f"\n{title}")
    for i, opt in enumerate(options, start=1):
        print(f"{i}) {opt}")
    while True:
        sel = input("> ").strip()
        if sel.isdigit():
            idx = int(sel) - 1
            if 0 <= idx < len(options):
                return idx
        print("Entrada inválida. Digite o número da opção.")

def choose_project(root: str):
    projects = list_projects(root)
    if not projects:
        print("Nenhum projeto encontrado em 'collections/'.")
        return None
    idx = prompt_menu(projects, "Qual projeto deseja executar?")
    return projects[idx]

def choose_environment(root: str, project: str):
    env_dir = os.path.join(root, project, "enviroment")
    envs = list_jsons(env_dir)
    if not envs:
        print("Nenhum environment (.json) encontrado para esse projeto.")
        return None
    labels = [os.path.basename(p) for p in envs]
    idx = prompt_menu(labels, "Qual environment deseja usar?")
    return envs[idx]

# =====================================================================
# Main
# =====================================================================
def main():
    load_dotenv()  # SMTP e outras configs (NÃO usa destinatários)

    if not which_postman():
        print("ERRO: Postman CLI não encontrado no PATH. Instale-o e garanta o comando 'postman'.")
        raise SystemExit(2)

    postman_login_if_needed()

    collections_root = os.getenv("COLLECTIONS_ROOT", "collections")
    email_cfg = {
        "SMTP_HOST": os.getenv("SMTP_HOST",""),
        "SMTP_PORT": os.getenv("SMTP_PORT","465"),
        "SMTP_USE_TLS": os.getenv("SMTP_USE_TLS","false"),
        "SMTP_USER": os.getenv("SMTP_USER",""),
        "SMTP_PASS": os.getenv("SMTP_PASS",""),
        # MAIL_FROM cai para SMTP_USER se vazio
        "MAIL_FROM": os.getenv("MAIL_FROM","") or os.getenv("SMTP_USER",""),
        "MAIL_SUBJECT": os.getenv("MAIL_SUBJECT","[AUTOMATEST] Relatório de coleções Postman"),
    }

    choice = prompt_menu(
        ["Executar TUDO (todas coleções x todos environments)",
         "Executar projeto + environment específico"],
        "Como deseja executar?"
    )

    if choice == 0:
        exec_plan = find_all_pairs(collections_root)
    else:
        proj = choose_project(collections_root)
        if not proj:
            return
        env_path = choose_environment(collections_root, proj)
        if not env_path:
            return
        exec_plan = find_pairs_for_project(collections_root, proj, env_path)

    if not exec_plan:
        print("Nada para executar.")
        return

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base_log_dir = os.path.join("logs", timestamp)

    grouped = {}
    attachments = []

    for job in exec_plan:
        proj = job["project"]
        col = job["collection"]
        env = job["environment"]
        env_label = env_label_from_path(env)
        out_dir = os.path.join(base_log_dir, proj, env_label)

        print(f"\n=== Executando: {proj} | env={os.path.basename(env)} | col={os.path.basename(col)}")
        result = run_collection(col, env, out_dir)

        if result.get("report_path"):
            attachments.append(result["report_path"])
        if result.get("stdout_path"):
            attachments.append(result["stdout_path"])

        summary = summarize_run(result.get("report_path"), result.get("stdout"))
        grouped.setdefault(proj, {})
        grouped[proj].setdefault(env_label, [])
        grouped[proj][env_label].append({
            "collection_name": os.path.basename(col),
            "summary": summary,
            "exec_meta": {
                "returncode": result["returncode"],
                "stderr": result["stderr"],
                "stdout": result["stdout"],
                "cmd": result["cmd"]
            }
        })

    body_txt = build_human_report(grouped)
    body_html = build_html_report(grouped)

    print("\n" + body_txt)

    ok_send = send_mail(email_cfg["MAIL_SUBJECT"], body_txt, body_html, attachments, email_cfg)
    print("E-mail enviado." if ok_send else "E-mail NÃO enviado (ver console).")

if __name__ == "__main__":
    main()
