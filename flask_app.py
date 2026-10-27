import os
import json
import warnings
import re
import asyncio
import requests
from datetime import datetime
import pandas as pd
from flask import Flask, request

# 🔥 MÓDULO WEB DECLARADO NO TOPO
app = Flask(__name__)
warnings.filterwarnings("ignore", module="telegram.ext.ConversationHandler")

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from google import genai
from google.genai import types
from fpdf import FPDF
from pypdf import PdfReader, PdfWriter

# 🔥 NOVA IMPORTAÇÃO DE SEGURANÇA MILITAR (AES) 🔥
from cryptography.fernet import Fernet

# ================= CREDENCIAIS =================
from dotenv import load_dotenv
caminho_cofre = "/home/mtchello/mysite/.env"
load_dotenv(caminho_cofre)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
VIGIA_KEY = os.environ.get("VIGIA_KEY") # 🔥 PUXANDO A CHAVE MESTRA
URL_PYTHONANYWHERE = "https://mtchello.pythonanywhere.com"

# ⚠️ A PLANILHA OFICIAL COMERCIAL
SPREADSHEET_ID = '17XZfEUKiiryGJgj_nXdQ7gXzdByEwsZ7ecax44ZeJmc'
ARQUIVO_SENHA = "senha_pdf.txt"

client = genai.Client(api_key=GEMINI_API_KEY)

# ================= ESTADOS DO CONVERSATION =================
AGUARDANDO_CORRECAO = 1
VISTOS_TURMA = 2
VISTOS_NOTA = 3
VISTOS_DATAS = 4
RAIOX_TURMA = 5
AGUARDANDO_LGPD = 10
ONBOARDING_NOME = 6
ONBOARDING_UNIDADE = 11
ONBOARDING_CODIGO = 7
ONBOARDING_LOGIN = 8
ONBOARDING_SENHA = 9

# ================= NORMALIZADOR E BUSCADOR =================
def padronizar_turma(texto):
    if not texto:
        return ""
    t = str(texto).upper().strip()
    substituicoes = {
        "PRIMEIRA": "1ª", "SEGUNDA": "2ª", "TERCEIRA": "3ª",
        "QUARTA": "4ª", "QUINTA": "5ª", "SEXTA": "6ª",
        "SÉTIMA": "7ª", "OITAVA": "8ª", "NONA": "9ª",
        "PRIMEIRO": "1º", "SEGUNDO": "2º", "TERCEIRO": "3º",
        "QUARTO": "4º", "QUINTO": "5º", "SEXTO": "6º",
        "SÉTIMO": "7º", "OITAVO": "8º", "NONO": "9º"
    }
    for k, v in substituicoes.items():
        t = t.replace(k, v)

    if "SÉRIE" in t or "SERIE" in t or "EM" in t or "MÉDIO" in t:
        num = re.search(r'[1-3]', t)
        num_str = num.group(0) if num else "3"
        return f"{num_str}ª SÉRIE EM"

    num_fund = re.search(r'[6-9]', t)
    if num_fund:
        num_str = num_fund.group(0)

        # 🔥 CORREÇÃO: Captura dinâmica de turmas (A, B, C, D, E...) 🔥
        t_clean = re.sub(r'\b(ANO|LETRA|TURMA)\b', '', t).replace('º', '').replace('°', '').strip()

        match_letra = re.search(rf'{num_str}\s*([A-H])\b', t_clean)
        if not match_letra:
            match_letra = re.search(r'\b([A-H])\b', t_clean)

        letra = match_letra.group(1) if match_letra else "A"
        return f"{num_str}º ANO {letra}"

    return t

def buscar_aba_oficial(planilha, prefixo, turma_ia, unidade="", fallback=True):
    def extrair_id(texto):
        # 🔥 VACINA CONTRA O CÓDIGO DA ESCOLA (Ignora o FD e SEM) 🔥
        t = texto.upper().replace("ANO", "").replace("SÉRIE", "").replace("SERIE", "").replace("EM", "")
        t = t.replace("FD", "").replace("SEM", "")

        nums = re.findall(r'\d', t)
        num = nums[-1] if nums else ""
        letra = ""
        match_letra = re.search(r'([A-E])$', t.strip())
        if match_letra:
            letra = match_letra.group(1)
        return f"{num}{letra}"

    id_alvo = extrair_id(turma_ia)
    unidade_limpa = re.sub(r'[^A-Z0-9]', '', str(unidade).upper())

    for aba in planilha.worksheets():
        if aba.title.startswith(prefixo):
            if unidade_limpa and unidade_limpa not in aba.title.upper():
                continue

            nome_bruto = aba.title.replace(prefixo, "")
            if extrair_id(nome_bruto) == id_alvo:
                return aba.title

    if fallback:
        if unidade_limpa:
            return f"{prefixo}{unidade_limpa}_{turma_ia}"
        return f"{prefixo}{turma_ia}"
    return None

# ================= SHEETS & MULTI-USUÁRIO =================
def conectar_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", scope)
    return gspread.authorize(creds).open_by_key(SPREADSHEET_ID)

def carregar_df_sheets(planilha, nome_planilha, colunas_padrao):
    try:
        ws = planilha.worksheet(nome_planilha)
    except Exception:
        return pd.DataFrame(columns=colunas_padrao)

    dados = ws.get_all_values()
    if not dados or len(dados) < 1:
        return pd.DataFrame(columns=colunas_padrao)

    headers = [str(h).strip() for h in dados[0]]
    linhas = []
    for row in dados[1:]:
        while len(row) < len(headers):
            row.append("")
        linhas.append(row[:len(headers)])

    return pd.DataFrame(linhas, columns=headers).astype(str)

def checar_usuario_cadastrado(chat_id):
    try:
        planilha = conectar_sheets()
        dados_usuarios = planilha.worksheet("Usuarios").get_all_values()
        for linha in dados_usuarios[1:]:
            if str(linha[0]).strip() == str(chat_id):
                return {
                    "nome": linha[1],
                    "unidade": str(linha[2]).strip(),
                    "codigo": linha[3],
                    "aba_config": linha[6],
                    "status": str(linha[7]).strip().upper() if len(linha) > 7 else ""
                }
        return None
    except Exception as e:
        print(f"Erro na verificação de usuário: {e}")
        return "ERRO"

async def validar_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if 'usuario_logado' in context.user_data:
        return True

    usuario = await asyncio.to_thread(checar_usuario_cadastrado, chat_id)

    if usuario == "ERRO":
        await update.message.reply_text("🚨 Falha ao conectar ao banco de dados. Tente novamente.")
        return False

    if not usuario:
        await update.message.reply_text("🔒 *Acesso Negado*\nVocê não tem cadastro. Digite /start para iniciar a criação da sua conta.", parse_mode='Markdown')
        return False

    if usuario.get("status") == "BLOQUEADO":
        await update.message.reply_text("⛔ *Assinatura Inativa*\nSua conta está bloqueada por falta de pagamento. Entre em contato com o suporte.", parse_mode='Markdown')
        return False

    context.user_data['usuario_logado'] = usuario
    context.user_data['chat_id'] = chat_id
    return True

# ================= COMANDOS E ONBOARDING =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    usuario = await asyncio.to_thread(checar_usuario_cadastrado, chat_id)

    if usuario and usuario != "ERRO":
        if usuario.get("status") == "BLOQUEADO":
            await update.message.reply_text("⛔ *Assinatura Inativa*\nSua conta está bloqueada.", parse_mode='Markdown')
            return ConversationHandler.END

        context.user_data['usuario_logado'] = usuario
        context.user_data['chat_id'] = chat_id
        context.user_data['fotos_temp'] = []

        await update.message.reply_text(
            f"👋 Olá, Professor(a) {usuario['nome']}!\n\n"
            "📸 Envie fotos do quadro para registrar a aula.\n"
            "🎙️ Envie áudio/texto para Lançar Notas.\n"
            "📚 Use /vistos para fechar a nota dos Para Casas.\n"
            "🔍 Use /raiox para gerar relatório pedagógico.\n"
            "📋 Use /fila para ver ou cancelar tarefas pendentes.\n"
            "🔐 Use /senha [PIN] para trocar a senha do seu PDF.\n"
            "⚙️ Use /etapa [Nome] para mudar a etapa do Vigia."
        )
        return ConversationHandler.END
    else:
        termos = (
            "⚖️ *TERMO DE CONSENTIMENTO E RESPONSABILIDADE*\n\n"
            "Olá! Bem-vindo ao *Assessor.IA*. Para prepararmos sua conta, precisamos do seu consentimento em conformidade com a LGPD (Lei 13.709/18):\n\n"
            "1️⃣ *Uso das Credenciais:* Você concorda em fornecer seu Login e Senha do Activesoft exclusivamente para a finalidade de automação de lançamentos.\n"
            "2️⃣ *Armazenamento Seguro:* Suas credenciais serão guardadas com Criptografia de nível militar, acessível apenas pelo robô no momento da operação.\n"
            "3️⃣ *Isenção de Responsabilidade:* O robô é um assistente de digitação. Você é integralmente responsável pelos dados enviados e por revisar as postagens. O Assessor.IA não se responsabiliza por bloqueios ou normas internas da escola.\n"
            "4️⃣ *Revogação:* Você pode excluir seu cadastro a qualquer momento.\n\n"
            "Você concorda com os termos para iniciar?"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Li e Aceito", callback_data="LGPD_ACEITO")],
            [InlineKeyboardButton("❌ Não Aceito", callback_data="LGPD_RECUSADO")]
        ]

        await update.message.reply_text(termos, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return AGUARDANDO_LGPD

async def lidar_lgpd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "LGPD_ACEITO":
        await query.edit_message_text(
            "✅ Termos aceitos! Vamos preparar o seu banco de dados escolar.\n\n"
            "1️⃣ Para começar, **como você gostaria de ser chamado(a)?** (Ex: Prof. Marcelo)",
            parse_mode='Markdown'
        )
        return ONBOARDING_NOME
    elif query.data == "LGPD_RECUSADO":
        await query.edit_message_text("❌ Cadastro cancelado. Nós respeitamos profundamente a sua privacidade e os seus dados!")
        return ConversationHandler.END

async def onboarding_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ob_nome'] = update.message.text.strip()
    await update.message.reply_text(
        f"2️⃣ Legal, {context.user_data['ob_nome']}!\n\n**Em qual Unidade ou Escola você leciona?**\n(Isso organiza as suas planilhas. Ex: M2 Fernão Dias, Simão Tamm, etc)",
        parse_mode='Markdown'
    )
    return ONBOARDING_UNIDADE

async def onboarding_unidade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ob_unidade'] = update.message.text.strip()
    await update.message.reply_text(
        f"3️⃣ Anotado! Agora preciso do **Código da Instituição** no Activesoft (aquele número que você preenche na primeira tela de login).",
        parse_mode='Markdown'
    )
    return ONBOARDING_CODIGO

async def onboarding_codigo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ob_codigo'] = update.message.text.strip()
    await update.message.reply_text(
        "4️⃣ Perfeito. Digite agora o seu **Login** do Activesoft:",
        parse_mode='Markdown'
    )
    return ONBOARDING_LOGIN

async def onboarding_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ob_login'] = update.message.text.strip()
    await update.message.reply_text(
        "5️⃣ Para finalizar, digite a sua **Senha** do Activesoft.\n\n"
        "_Segurança: Ela será embaralhada e guardada criptografada no seu banco de dados._",
        parse_mode='Markdown'
    )
    return ONBOARDING_SENHA

async def onboarding_senha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ob_senha'] = update.message.text.strip()
    chat_id = str(update.effective_chat.id)

    msg_status = await update.message.reply_text("⏳ Criptografando sua conta e provisionando o banco de dados...")

    def salvar_novo_usuario():
        planilha = conectar_sheets()
        aba = planilha.worksheet("Usuarios")

        nome = context.user_data['ob_nome']
        unidade = context.user_data['ob_unidade']
        codigo = context.user_data['ob_codigo']
        login = context.user_data['ob_login']
        senha_pura = context.user_data['ob_senha']
        aba_config = f"Config_{chat_id[:4]}"

        # 🔥 EMBARALHADOR DE SENHA (CRIPTOGRAFIA AES) 🔥
        try:
            if VIGIA_KEY:
                f = Fernet(VIGIA_KEY.encode('utf-8') if isinstance(VIGIA_KEY, str) else VIGIA_KEY)
                senha_segura = f.encrypt(senha_pura.encode('utf-8')).decode('utf-8')
            else:
                senha_segura = senha_pura # Fallback de emergência
        except Exception as e:
            print(f"Erro na Criptografia: {e}")
            senha_segura = senha_pura

        nova_linha = [chat_id, nome, unidade, codigo, login, senha_segura, aba_config, "PENDENTE"]
        aba.append_row(nova_linha)

    try:
        await asyncio.to_thread(salvar_novo_usuario)
        await msg_status.edit_text(
            f"🎉 **Bem-vindo(a) ao Assessor.IA, {context.user_data['ob_nome']}!**\n\n"
            f"Sua conta foi criada e blindada com sucesso! 🚀\n"
            f"O meu robô *Vigia Scan* já foi acionado nos bastidores para mapear todas as suas turmas e alunos.\n\n"
            f"Quando quiser usar as funcionalidades, basta enviar uma foto do quadro ou um áudio de notas!",
            parse_mode='Markdown'
        )
    except Exception as e:
        await msg_status.edit_text(f"❌ Erro ao criar conta no banco de dados: {e}")

    return ConversationHandler.END

async def comando_etapa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await validar_usuario(update, context):
        return

    nova_etapa = update.message.text.replace('/etapa', '').strip()
    if not nova_etapa:
        return

    msg_status = await update.message.reply_text("⏳ Atualizando a Etapa...")

    def atualizar():
        planilha = conectar_sheets()
        nome_aba = context.user_data['usuario_logado'].get('aba_config', 'Config')
        try:
            ws = planilha.worksheet(nome_aba)
        except Exception:
            ws = planilha.add_worksheet(title=nome_aba, rows="10", cols="2")
        ws.update_acell('A1', 'Etapa Atual')
        ws.update_acell('B1', nova_etapa)

    try:
        await asyncio.to_thread(atualizar)
        await msg_status.edit_text(f"✅ O Vigia agora vai lançar na *{nova_etapa}* para você!", parse_mode='Markdown')
    except Exception as e:
        await msg_status.edit_text(f"❌ Erro ao salvar etapa: `{e}`", parse_mode='Markdown')

async def comando_senha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await validar_usuario(update, context):
        return

    nova_senha = update.message.text.replace('/senha', '').strip()
    if not nova_senha:
        return

    arquivo_individual = f"senha_pdf_{update.effective_chat.id}.txt"
    with open(arquivo_individual, "w") as f:
        f.write(nova_senha)

    await update.message.reply_text(f"🔐 Senha dos PDFs atualizada para: `{nova_senha}`", parse_mode='Markdown')

async def comando_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await validar_usuario(update, context):
        return

    chat_id = context.user_data['chat_id']
    msg_status = await update.message.reply_text("⏳ Registrando o seu pedido de Scan na fila...")

    def registrar_pendencia():
        planilha = conectar_sheets()
        aba_usuarios = planilha.worksheet("Usuarios")
        dados_usuarios = aba_usuarios.get_all_values()

        for i, linha in enumerate(dados_usuarios):
            if str(linha[0]).strip() == str(chat_id):
                aba_usuarios.update_cell(i + 1, 8, "PENDENTE")
                return True
        return False

    try:
        sucesso = await asyncio.to_thread(registrar_pendencia)
        if sucesso:
            await msg_status.edit_text("✅ **Pedido de Scan Registrado!**\nNa próxima ronda, o Vigia vai recriar seu banco.", parse_mode='Markdown')
        else:
            await msg_status.edit_text("❌ Erro: Não encontrei o seu cadastro na planilha.")
    except Exception as e:
        await msg_status.edit_text(f"❌ Erro crítico ao registrar Scan: `{e}`", parse_mode='Markdown')

async def comando_fila(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await validar_usuario(update, context):
        return

    chat_id = str(update.effective_chat.id)
    msg_status = await update.message.reply_text("⏳ Buscando suas tarefas pendentes no servidor...")

    def buscar_pendencias():
        planilha = conectar_sheets()
        pendencias = []

        abas_reg = [aba for aba in planilha.worksheets() if aba.title.startswith("registros_")]
        for aba in abas_reg:
            dados = aba.get_all_values()
            if len(dados) < 2:
                continue

            headers = [str(h).strip().upper() for h in dados[0]]
            if "ID_PROFESSOR" not in headers:
                continue

            idx_prof = headers.index("ID_PROFESSOR")
            idx_status_d = headers.index("STATUS_DIARIO") if "STATUS_DIARIO" in headers else -1
            idx_status_o = headers.index("STATUS_OCORRENCIA") if "STATUS_OCORRENCIA" in headers else -1
            idx_status_f = headers.index("STATUS_FALTA") if "STATUS_FALTA" in headers else -1

            for i, row in enumerate(dados[1:]):
                linha_real = i + 2
                while len(row) <= max(idx_prof, idx_status_d, idx_status_o, idx_status_f):
                    row.append("")

                if str(row[idx_prof]).strip() == chat_id:
                    status_comb = str(row[idx_status_d]) + str(row[idx_status_o]) + str(row[idx_status_f])
                    if "Pendente" in status_comb:
                        data_aula = str(row[0])
                        turma_nome = aba.title.replace('registros_', '')
                        pendencias.append({
                            "tipo": "REG",
                            "aba": aba.title,
                            "linha": linha_real,
                            "desc": f"Aula - {turma_nome} ({data_aula})"
                        })

        abas_notas = [aba for aba in planilha.worksheets() if aba.title.startswith("Notas_")]
        for aba in abas_notas:
            dados = aba.get_all_values()
            if len(dados) < 6:
                continue

            for col_idx, status in enumerate(dados[2]):
                if "Pendente" in str(status) and str(dados[1][col_idx]).strip() == chat_id:
                    nome_prova = str(dados[0][col_idx])
                    turma_nome = aba.title.replace('Notas_', '')
                    pendencias.append({
                        "tipo": "NOT",
                        "aba": aba.title,
                        "col": col_idx + 1,
                        "desc": f"Notas - {nome_prova} ({turma_nome})"
                    })
        return pendencias

    try:
        lista = await asyncio.to_thread(buscar_pendencias)
        if not lista:
            await msg_status.edit_text("🟢 Você não possui tarefas pendentes na fila! O banco está limpo.")
            return

        botoes = []
        texto = "📋 *Suas Tarefas na Fila (Aguardando Vigia):*\n_Se você salvou algo errado, exclua abaixo e reenvie._\n\n"

        for i, p in enumerate(lista):
            desc_limpa = str(p['desc']).replace('_', ' ').replace('*', '')
            texto += f"🔹 {desc_limpa}\n"

            # 🔥 BOTÕES BLINDADOS (Não perdem a memória se o servidor reiniciar)
            if p['tipo'] == "REG":
                cb_data = f"DEL|REG|{p['linha']}|{p['aba']}"
            else:
                cb_data = f"DEL|NOT|{p['col']}|{p['aba']}"

            botoes.append([InlineKeyboardButton(f"❌ Excluir: {desc_limpa}", callback_data=cb_data)])

        botoes.append([InlineKeyboardButton("Fechar Aba", callback_data="FECHAR_FILA")])
        await msg_status.edit_text(texto, reply_markup=InlineKeyboardMarkup(botoes), parse_mode='Markdown')
    except Exception as e:
        await msg_status.edit_text(f"❌ Erro ao buscar fila: {e}")

# ================= RAIO-X =================
async def comando_raiox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await validar_usuario(update, context):
        return
    await update.message.reply_text("🔍 *Raio-X Pedagógico Seguro*\n\nTurma: (Ex: 8º ANO A)", parse_mode='Markdown')
    return RAIOX_TURMA

async def receber_turma_raiox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    turma = padronizar_turma(update.message.text)
    msg_status = await update.message.reply_text(f"⏳ Coletando dados da turma *{turma}*...", parse_mode='Markdown')

    chat_id = context.user_data['chat_id']
    unidade = context.user_data['usuario_logado'].get('unidade', '')

    def processar_raiox():
        planilha = conectar_sheets()

        nome_aba_alunos = buscar_aba_oficial(planilha, "alunos_", turma, unidade, fallback=False)
        if not nome_aba_alunos:
            return "ERRO: Aba de alunos não encontrada. Faça o Scan primeiro.", ""

        nome_aba_reg = buscar_aba_oficial(planilha, "registros_", turma, unidade, fallback=False)
        nome_aba_notas = buscar_aba_oficial(planilha, "Notas_", turma, unidade, fallback=False)

        dados_alunos = planilha.worksheet(nome_aba_alunos).get_all_values()
        mapa_anon = {}
        mapa_reverso = {}
        alunos_dados = {}

        for row in dados_alunos[1:]:
            if len(row) >= 2:
                num = str(row[0]).strip()
                nome = str(row[1]).strip()
                if num and nome:
                    mascara = f"Aluno {num}"
                    mapa_anon[num] = mascara
                    mapa_reverso[mascara] = f"{num} - {nome}"
                    alunos_dados[num] = {"faltas": 0, "nao_fez": 0, "advertencias": 0, "notas": []}

        if nome_aba_reg:
            dados_reg = planilha.worksheet(nome_aba_reg).get_all_values()
            if len(dados_reg) > 1:
                headers = [str(h).strip().upper() for h in dados_reg[0]]
                idx_prof = headers.index("ID_PROFESSOR") if "ID_PROFESSOR" in headers else -1
                idx_faltas = headers.index("FALTAS") if "FALTAS" in headers else -1
                idx_nao_fez = headers.index("NAO_FEZ") if "NAO_FEZ" in headers else -1
                idx_adv = headers.index("ADVERTENCIAS") if "ADVERTENCIAS" in headers else -1

                for row in dados_reg[1:]:
                    while len(row) < len(headers):
                        row.append("")

                    if idx_prof != -1 and str(row[idx_prof]).strip() != chat_id:
                        continue

                    if idx_faltas != -1:
                        for n in re.findall(r'\d+', str(row[idx_faltas])):
                            if n in alunos_dados:
                                alunos_dados[n]["faltas"] += 1
                    if idx_nao_fez != -1:
                        for n in re.findall(r'\d+', str(row[idx_nao_fez])):
                            if n in alunos_dados:
                                alunos_dados[n]["nao_fez"] += 1
                    if idx_adv != -1:
                        for n in re.findall(r'\d+', str(row[idx_adv])):
                            if n in alunos_dados:
                                alunos_dados[n]["advertencias"] += 1

        if nome_aba_notas:
            dados_notas = planilha.worksheet(nome_aba_notas).get_all_values()
            if len(dados_notas) > 5:
                cols_suas = [i for i, val in enumerate(dados_notas[1]) if str(val).strip() == chat_id]
                for row in dados_notas[5:]:
                    num = str(row[0]).strip()
                    if num in alunos_dados:
                        for c in cols_suas:
                            if c < len(row) and str(row[c]).strip():
                                alunos_dados[num]["notas"].append(str(row[c]).strip())

        linhas_ia = []
        for num, dados in alunos_dados.items():
            n_str = ", ".join(dados["notas"]) if dados["notas"] else "Sem notas"
            linhas_ia.append(f"{mapa_anon[num]} | Notas: [{n_str}] | Faltas: {dados['faltas']} | Para Casa N/F: {dados['nao_fez']} | Advertências: {dados['advertencias']}")

        if not linhas_ia:
            return "ERRO: Nenhum dado de aula encontrado para gerar o Raio-X.", ""

        prompt = (
            "Você é um Sistema Analítico Educacional. Escreva um relatório técnico, gerencial e objetivo "
            "sobre o desempenho desta turma, focado em subsidiar decisões de professores, orientadores e coordenadores.\n"
            "REGRAS DE FORMATAÇÃO ESTRITAS:\n"
            "1. NÃO USE NENHUM caractere Markdown (é TERMINANTEMENTE PROIBIDO usar *, **, #, ou _).\n"
            "2. Use letras MAIÚSCULAS para criar os títulos das seções (ex: RESUMO DA TURMA, ANÁLISE INDIVIDUAL).\n"
            "3. Escreva em texto puro, usando apenas quebras de linha (parágrafos) para separar os assuntos.\n"
            "4. Seja direto, destacando padrões coletivos e depois os desempenhos individuais atípicos.\n\n"
            f"Dados ANÔNIMOS coletados:\n{chr(10).join(linhas_ia)}"
        )

        resposta = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3)
        )
        relatorio = resposta.text

        chaves_ordenadas = sorted(mapa_reverso.keys(), key=lambda x: int(x.split()[1]), reverse=True)
        for masc in chaves_ordenadas:
            relatorio = re.sub(rf'\b{masc}\b', f"{mapa_reverso[masc].upper()}", relatorio)

        relatorio = relatorio.replace('*', '').replace('#', '').replace('_', '').replace('`', '')

        senha_pdf = "1234"
        arquivo_individual = f"senha_pdf_{chat_id}.txt"

        if os.path.exists(arquivo_individual):
            with open(arquivo_individual, "r") as f:
                senha_lida = f.read().strip()
                if senha_lida:
                    senha_pdf = senha_lida

        nome_temp = f"temp_raiox_{chat_id}.pdf"
        nome_final = f"RaioX_{turma}.pdf"

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 8, txt=relatorio.encode('latin-1', 'replace').decode('latin-1'))
        pdf.output(nome_temp)

        reader = PdfReader(nome_temp)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        writer.encrypt(senha_pdf)

        with open(nome_final, "wb") as f:
            writer.write(f)

        if os.path.exists(nome_temp):
            os.remove(nome_temp)

        return nome_final, senha_pdf

    try:
        nome_pdf, senha = await asyncio.to_thread(processar_raiox)
        if "ERRO:" in nome_pdf:
            await msg_status.edit_text(nome_pdf)
            return ConversationHandler.END

        await context.bot.send_document(
            chat_id=chat_id,
            document=open(nome_pdf, 'rb'),
            caption=f"🔐 *Relatório Gerado!*\nSenha: `{senha}`\n\n_Segurança LGPD: O documento foi criptografado e a IA avaliou os alunos anonimamente._",
            parse_mode='Markdown'
        )

        if os.path.exists(nome_pdf):
            os.remove(nome_pdf)

        await msg_status.delete()

    except Exception as e:
        await msg_status.edit_text(f"❌ Erro crítico ao gerar Raio-X: `{e}`", parse_mode='Markdown')

    return ConversationHandler.END

# ================= VISTOS =================
async def comando_vistos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await validar_usuario(update, context):
        return
    await update.message.reply_text("📚 *Vistos*\n\nTurma: (Ex: 8º ANO A)", parse_mode='Markdown')
    return VISTOS_TURMA

async def receber_turma_vistos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['vistos_turma'] = padronizar_turma(update.message.text)
    await update.message.reply_text("🏫 Qual é o valor total? (Ex: 5,0)", parse_mode='Markdown')
    return VISTOS_NOTA

async def receber_nota_vistos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['vistos_nota'] = float(update.message.text.replace(',', '.'))
        await update.message.reply_text("📅 Intervalo de datas? (Ex: *01/08 a 31/08*)", parse_mode='Markdown')
        return VISTOS_DATAS
    except Exception:
        await update.message.reply_text("❌ Valor inválido. Tente novamente (Ex: 5,0)")
        return VISTOS_NOTA

async def receber_datas_vistos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    datas = re.findall(r'(\d{2}/\d{2}(?:/\d{2,4})?)', update.message.text)
    if len(datas) < 2:
        return VISTOS_DATAS

    msg_status = await update.message.reply_text("⏳ Calculando vistos...")
    chat_id = context.user_data['chat_id']
    unidade = context.user_data['usuario_logado'].get('unidade', '')

    def processar_calculo():
        def parse_dt(d_str):
            m = re.search(r'(\d{2}/\d{2}(?:/\d{2,4})?)', str(d_str))
            if not m:
                return None
            d = m.group(1)
            if len(d) <= 5:
                d += f"/{datetime.now().year}"
            return datetime.strptime(d, "%d/%m/%Y")

        planilha = conectar_sheets()

        aba_reg = buscar_aba_oficial(planilha, "registros_", context.user_data['vistos_turma'], unidade, fallback=False)
        aba_alunos = buscar_aba_oficial(planilha, "alunos_", context.user_data['vistos_turma'], unidade, fallback=False)

        df_reg = carregar_df_sheets(planilha, aba_reg, ["Data", "Nao_Fez", "ID_Professor"])
        df_alunos = carregar_df_sheets(planilha, aba_alunos, ["Nº", "Nome"])

        if 'ID_Professor' in df_reg.columns:
            df_reg = df_reg[df_reg['ID_Professor'] == chat_id]

        dt_in = parse_dt(datas[0])
        dt_out = parse_dt(datas[1])

        total_aulas = 0
        faltas_aluno = {}

        for _, row in df_reg.iterrows():
            try:
                dt_aula = parse_dt(row.get('Data', ''))
                if dt_aula and dt_in <= dt_aula <= dt_out:
                    total_aulas += 1
                    nao_fez = str(row.get('Nao_Fez', '')).strip()
                    if nao_fez:
                        for n in re.findall(r'\d+', nao_fez):
                            faltas_aluno[n] = faltas_aluno.get(n, 0) + 1
            except Exception:
                pass

        if total_aulas == 0:
            raise Exception("Nenhuma aula sua foi encontrada nesse período.")

        notas_finais = {}
        for _, row_al in df_alunos.iterrows():
            num = str(row_al.get('Nº', '')).strip()
            if num:
                qtd_faltas = faltas_aluno.get(num, 0)
                nota_calc = max(0.0, context.user_data['vistos_nota'] - (context.user_data['vistos_nota'] / total_aulas) * qtd_faltas)
                notas_finais[num] = f"{nota_calc:.2f}".replace(".", ",")

        return notas_finais, total_aulas

    try:
        finais, tot = await asyncio.to_thread(processar_calculo)
        valor_activesoft = str(int(round(context.user_data['vistos_nota'] * 100)))

        dados_vistos = {
            "tipo": "notas",
            "turma": context.user_data['vistos_turma'],
            "nome_prova": f"Vistos {datas[1]}",
            "data": datetime.now().strftime("%d/%m/%Y"),
            "valor": valor_activesoft,
            "notas": finais
        }

        context.user_data['dados_pendentes'] = dados_vistos
        await exibir_resumo_audio(update, context, dados_vistos, msg_status, info_extra=f"📖 *Base:* {tot} aulas suas.")

    except Exception as e:
        await msg_status.edit_text(f"❌ Erro ao calcular vistos: `{e}`", parse_mode='Markdown')

    return ConversationHandler.END

# ================= FUNÇÕES DE FOTOS/ÁUDIO =================
async def receber_foto_quadro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await validar_usuario(update, context):
        return

    if 'fotos_temp' not in context.user_data:
        context.user_data['fotos_temp'] = []

    caminho = f"temp_quadro_{update.message.chat_id}_{len(context.user_data['fotos_temp'])}.jpg"
    arquivo = await update.message.photo[-1].get_file()
    await arquivo.download_to_drive(caminho)

    context.user_data['fotos_temp'].append(caminho)

    keyboard = [
        [InlineKeyboardButton(f"🧠 Ler Quadro (Aula)", callback_data="PROCESSAR_QUADRO")],
        [InlineKeyboardButton(f"📝 Ler Lista (Notas)", callback_data="PROCESSAR_NOTAS")]
    ]
    await update.message.reply_text(f"📸 Foto {len(context.user_data['fotos_temp'])} recebida!", reply_markup=InlineKeyboardMarkup(keyboard))

async def processar_fotos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get('fotos_temp'):
        return await query.edit_message_text("Nenhuma foto encontrada na memória. Tente enviar a foto novamente.")

    await query.edit_message_text("📸 Lendo o quadro...")

    try:
        def upload_fotos():
            return [client.files.upload(file=c) for c in context.user_data['fotos_temp']]

        fotos_gemini = await asyncio.to_thread(upload_fotos)

        prompt = f"""Você é um assistente de diário de classe. Extraia ESTRITAMENTE o JSON:
        {{"tipo": "aula", "turma": "...", "disciplina": "...", "data": "DD/MM/YYYY", "nao_fez": {{"atividade": "...", "alunos": [...]}}, "faltas": [...], "advertencias": [...], "destaque": [...], "para_casa": "...", "resumo_aula": "..."}}
        (REGRAS: Use o ano atual {datetime.now().year} caso não tenha. Se houver alguma Disciplina informada na foto/texto, extraia. Se não houver, deixe vazio.)"""

        config_ia = types.GenerateContentConfig(temperature=0.1)
        response = await client.aio.models.generate_content(model='gemini-3.6-flash', contents=[prompt] + fotos_gemini, config=config_ia)

        for c in context.user_data.get('fotos_temp', []):
            if os.path.exists(c):
                os.remove(c)

        context.user_data['fotos_temp'] = []

        dados = json.loads(response.text.replace("```json", "").replace("```", "").strip())
        dados["turma"] = padronizar_turma(dados.get("turma", ""))

        data_sugerida = str(dados.get("data", "")).replace(".", "/").replace("-", "/")
        if data_sugerida:
            partes = data_sugerida.split("/")
            if len(partes) >= 2:
                dia = str(partes[0]).zfill(2)
                mes = str(partes[1]).zfill(2)
                dados["data"] = f"{dia}/{mes}/{datetime.now().year}"
        else:
            dados["data"] = datetime.now().strftime("%d/%m/%Y")

        context.user_data['dados_pendentes'] = dados
        await exibir_resumo_foto(update, context, dados, query.message)

    except Exception as e:
        for c in context.user_data.get('fotos_temp', []):
            if os.path.exists(c):
                os.remove(c)

        context.user_data['fotos_temp'] = []
        await query.edit_message_text(f"❌ Erro ao ler a imagem: `{e}`", parse_mode='Markdown')

async def processar_comando_notas(update, context, origem, conteudo, msg_status):
    try:
        # 🔥 CORREÇÃO 1: Prompt rigoroso forçando o formato de Dicionário
        prompt = f"Analise o comando de NOTAS. Extraia: turma, disciplina, nome_prova, data (ASSUMA O ANO {datetime.now().year}), valor e notas dos alunos. JSON: {{\"turma\":\"...\", \"disciplina\":\"...\", \"nome_prova\":\"...\", \"data\":\"...\", \"valor\":\"...\", \"notas\": {{\"1\":\"10\", \"2\":\"8.5\"}}}} (Atenção: 'notas' DEVE ser um Dicionário exato, onde a chave é o número e o valor é a nota)."
        config_ia = types.GenerateContentConfig(temperature=0.1)

        response = await client.aio.models.generate_content(model='gemini-3.6-flash', contents=[prompt, conteudo], config=config_ia)

        if origem == "audio" and os.path.exists(conteudo.name):
            os.remove(conteudo.name)

        if origem == "foto":
            for c in context.user_data.get('fotos_temp', []):
                if os.path.exists(c):
                    os.remove(c)
            context.user_data['fotos_temp'] = []

        dados = json.loads(response.text.replace("```json", "").replace("```", "").strip())

        # 🔥 CORREÇÃO 2: Blindagem caso a IA teime em enviar uma Lista
        if 'notas' in dados and isinstance(dados['notas'], list):
            notas_ditadas = {}
            for item in dados['notas']:
                if isinstance(item, dict):
                    # Caso venha como [{"numero": "1", "nota": "10"}]
                    if 'numero' in item and 'nota' in item:
                        notas_ditadas[str(item['numero'])] = str(item['nota'])
                    # Caso venha como [{"1": "10"}, {"2": "8.5"}]
                    else:
                        for k, v in item.items():
                            notas_ditadas[str(k)] = str(v)
            dados['notas'] = notas_ditadas

        dados["turma"] = padronizar_turma(dados.get("turma", ""))

        data_sugerida = str(dados.get("data", "")).replace(".", "/").replace("-", "/")
        if data_sugerida:
            partes = data_sugerida.split("/")
            if len(partes) >= 2:
                dia = str(partes[0]).zfill(2)
                mes = str(partes[1]).zfill(2)
                dados["data"] = f"{dia}/{mes}/{datetime.now().year}"
        else:
            dados["data"] = datetime.now().strftime("%d/%m/%Y")

        context.user_data['dados_pendentes'] = dados
        await exibir_resumo_audio(update, context, dados, msg_status)

    except Exception as e:
        if origem == "foto":
            for c in context.user_data.get('fotos_temp', []):
                if os.path.exists(c):
                    os.remove(c)
            context.user_data['fotos_temp'] = []

        await msg_status.edit_text(f"❌ Erro ao processar o comando de notas: `{e}`", parse_mode='Markdown')
async def processar_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await validar_usuario(update, context):
        return

    status = await update.message.reply_text("🎙️ Ouvindo...")
    caminho = f"temp_audio_{update.message.chat_id}.ogg"
    arquivo = await update.message.voice.get_file()
    await arquivo.download_to_drive(caminho)

    def upload_audio():
        return client.files.upload(file=caminho)

    audio = await asyncio.to_thread(upload_audio)
    audio.name = caminho

    await processar_comando_notas(update, context, "audio", audio, status)

async def processar_texto_livre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await validar_usuario(update, context):
        return

    status = await update.message.reply_text("🧠 Interpretando texto...")
    await processar_comando_notas(update, context, "texto", update.message.text, status)

async def processar_fotos_notas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get('fotos_temp'):
        return await query.edit_message_text("Nenhuma foto encontrada na memória. Envie novamente.")

    await query.edit_message_text("📸 Lendo lista de notas...")

    def upload_fotos():
        return [client.files.upload(file=c) for c in context.user_data.get('fotos_temp', [])]

    fotos = await asyncio.to_thread(upload_fotos)
    await processar_comando_notas(update, context, "foto", fotos[0], query.message)

# ================= EXIBIÇÃO E SALVAMENTO =================
async def exibir_resumo_foto(update: Update, context: ContextTypes.DEFAULT_TYPE, dados_json, msg_existente=None):
    def limpa(texto):
        if not texto:
            return "N/A"
        return str(texto).replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')

    msg = f"📊 *LEITURA DO QUADRO CONCLUÍDA*\n\n"
    msg += f"🏫 *Turma:* {limpa(dados_json.get('turma'))}\n"
    if dados_json.get('disciplina'):
        msg += f"📘 *Disciplina:* {limpa(dados_json.get('disciplina'))}\n"
    msg += f"📅 *Data:* {limpa(dados_json.get('data'))}\n"

    if dados_json.get("nao_fez") and dados_json["nao_fez"].get("alunos"):
        msg += f"❌ *Não Fizeram:* Nº {', '.join(map(str, dados_json['nao_fez']['alunos']))}\n"
    if dados_json.get("faltas"):
        msg += f"🪑 *Faltas:* Nº {', '.join(map(str, dados_json['faltas']))}\n"

    msg += f"🏠 *Para Casa:* {limpa(dados_json.get('para_casa'))}\n"
    msg += f"📝 *Resumo:* {limpa(dados_json.get('resumo_aula'))}\n"

    keyboard = [
        [InlineKeyboardButton("📅 Editar Data", callback_data="EDITAR_data"), InlineKeyboardButton("🏫 Editar Turma", callback_data="EDITAR_turma")],
        [InlineKeyboardButton("🪑 Editar Faltas", callback_data="EDITAR_faltas"), InlineKeyboardButton("❌ Editar Não Fez", callback_data="EDITAR_nao_fez")],
        [InlineKeyboardButton("📝 Editar Resumo", callback_data="EDITAR_resumo_aula"), InlineKeyboardButton("🏠 Editar Casa", callback_data="EDITAR_para_casa")],
        [InlineKeyboardButton("🔄 Atualizar Aula Existente", callback_data="SALVAR_FINAL"), InlineKeyboardButton("🆕 Criar Nova Aula", callback_data="SALVAR_NOVA")],
        [InlineKeyboardButton("🗑️ Cancelar", callback_data="CANCELAR")]
    ]
    await msg_existente.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def exibir_resumo_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, dados_json, msg_existente=None, info_extra=""):
    msg = f"📊 *NOVA AVALIAÇÃO E NOTAS IDENTIFICADAS*\n\n"
    if info_extra:
        msg += f"{info_extra}\n\n"

    msg += f"🏫 *Turma:* {dados_json.get('turma')}\n"
    if dados_json.get('disciplina'):
        msg += f"📘 *Disciplina:* {dados_json.get('disciplina')}\n"
    msg += f"📌 *Prova:* {dados_json.get('nome_prova')}\n"
    msg += f"📅 *Data:* {dados_json.get('data')}\n"
    msg += f"🎯 *Valor:* {dados_json.get('valor')}\n"

    notas_str = "\n".join([f"Nº {num}: {nota}" for num, nota in dados_json.get('notas', {}).items()])
    msg += f"\n*Notas Extraídas:*\n{notas_str}"

    keyboard = [
        [InlineKeyboardButton("🏫 Editar Turma", callback_data="EDITAR_turma"), InlineKeyboardButton("📌 Editar Prova", callback_data="EDITAR_nome_prova")],
        [InlineKeyboardButton("✅ Enviar para o Vigia", callback_data="SALVAR_NOTAS")],
        [InlineKeyboardButton("🗑️ Cancelar", callback_data="CANCELAR")]
    ]
    await msg_existente.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def coletar_correcao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    campo = context.user_data.get('campo_em_edicao')
    dados = context.user_data.get('dados_pendentes')

    if campo:
        if campo in ['faltas', 'advertencias', 'destaque']:
            dados[campo] = [int(n) for n in re.findall(r'\d+', texto)]
        elif campo == 'nao_fez':
            if 'nao_fez' not in dados or not isinstance(dados['nao_fez'], dict):
                dados['nao_fez'] = {"atividade": "", "alunos": []}
            dados['nao_fez']['alunos'] = [int(n) for n in re.findall(r'\d+', texto)]
        elif campo == "turma":
            dados[campo] = padronizar_turma(texto)
        else:
            dados[campo] = texto

    nova_mensagem = await update.message.reply_text("🔄 Valor atualizado com sucesso!")

    if dados.get("tipo", "aula") == "notas":
        await exibir_resumo_audio(update, context, dados, nova_mensagem)
    else:
        await exibir_resumo_foto(update, context, dados, nova_mensagem)

    return ConversationHandler.END

async def lidar_botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data in ["LGPD_ACEITO", "LGPD_RECUSADO"]:
        return

    if query.data == "PROCESSAR_QUADRO":
        return await processar_fotos(update, context)

    elif query.data == "PROCESSAR_NOTAS":
        return await processar_fotos_notas(update, context)

    elif query.data == "CANCELAR":
        context.user_data['dados_pendentes'] = None
        context.user_data['fotos_temp'] = []
        return await query.edit_message_text("🗑️ Operação cancelada com sucesso.")

    elif query.data == "FECHAR_FILA":
        return await query.edit_message_text("📋 Gerenciador de fila fechado.")

    # 🔥 NOVO BLOCO: MOTOR DE EXCLUSÃO BLINDADO 🔥
    elif query.data.startswith("DEL|"):
        partes = query.data.split("|")
        tipo = partes[1]
        idx_planilha = int(partes[2])
        aba_nome = partes[3]

        await query.edit_message_text(f"⏳ Excluindo tarefa do banco de dados...")

        def excluir_job_direto():
            planilha = conectar_sheets()
            aba = planilha.worksheet(aba_nome)

            if tipo == "REG":
                headers = [str(h).strip().upper() for h in aba.row_values(1)]
                i_d = headers.index("STATUS_DIARIO") + 1 if "STATUS_DIARIO" in headers else -1
                i_o = headers.index("STATUS_OCORRENCIA") + 1 if "STATUS_OCORRENCIA" in headers else -1
                i_f = headers.index("STATUS_FALTA") + 1 if "STATUS_FALTA" in headers else -1

                if i_d > 0: aba.update_cell(idx_planilha, i_d, "Cancelado")
                if i_o > 0: aba.update_cell(idx_planilha, i_o, "Cancelado")
                if i_f > 0: aba.update_cell(idx_planilha, i_f, "Cancelado")

            elif tipo == "NOT":
                aba.update_cell(3, idx_planilha, "Cancelado")

        try:
            await asyncio.to_thread(excluir_job_direto)
            await query.edit_message_text(f"🗑️ *Tarefa Excluída com Sucesso!*\nO Vigia vai ignorar esse lançamento.", parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Erro ao excluir: {e}")
        return

    elif query.data.startswith("EDITAR_"):
        campo = query.data.split("_", 1)[1]
        context.user_data['campo_em_edicao'] = campo
        await query.message.reply_text(f"✏️ Digite o novo valor para: *{campo}*", parse_mode='Markdown')
        return AGUARDANDO_CORRECAO

    dados = context.user_data.get('dados_pendentes')
    chat_id = context.user_data.get('chat_id')
    unidade = context.user_data['usuario_logado'].get('unidade', '')

    if not dados:
        return ConversationHandler.END

    if dados.get("tipo", "aula") == "aula":
        await query.edit_message_text("⏳ Salvando dados no banco de aulas...")

        def job_salvar_diario():
            planilha = conectar_sheets()
            nome_aba = buscar_aba_oficial(planilha, "registros_", str(dados.get("turma", "")).strip(), unidade)

            try:
                ws = planilha.worksheet(nome_aba)
            except Exception:
                ws = planilha.add_worksheet(title=nome_aba, rows="100", cols="15")
                ws.append_row(["Data", "Resumo", "Para Casa", "Faltas", "Nao_Fez", "Tarefa_Nao_Feita", "Advertencias", "Destaques", "Status_Diario", "Status_Ocorrencia", "Status_Falta", "Disciplina", "ID_Professor"])

            nao_fez_dict = dados.get("nao_fez") or {}

            if query.data == "SALVAR_NOVA":
                status_diario = "Pendente_Nova"
                status_falta = "Pendente_Nova"
            else:
                status_diario = "Pendente"
                status_falta = "Lançado"

            if nao_fez_dict.get("alunos"):
                status_ocorrencia = "Pendente"
            else:
                status_ocorrencia = "Lançado"

            nova_linha = [
                dados.get("data", ""),
                dados.get("resumo_aula", ""),
                dados.get("para_casa", ""),
                ", ".join(map(str, dados.get("faltas", []))),
                ", ".join(map(str, nao_fez_dict.get("alunos", []))),
                nao_fez_dict.get("atividade", ""),
                ", ".join(map(str, dados.get("advertencias", []))),
                ", ".join(map(str, dados.get("destaque", []))),
                status_diario,
                status_ocorrencia,
                status_falta,
                str(dados.get("disciplina", "")),
                str(chat_id)
            ]

            ws.append_row(nova_linha, value_input_option='USER_ENTERED')
            return nome_aba

        try:
            await asyncio.to_thread(job_salvar_diario)
            nao_fez_dict = dados.get("nao_fez") or {}
            resumo_aula = (
                f"✅ **Aula Lançada no Banco!**\n\n"
                f"🏫 *Turma:* {dados.get('turma')}\n"
                f"📅 *Data:* {dados.get('data')}\n"
                f"📝 *Resumo:* {dados.get('resumo_aula')}\n"
                f"🏠 *Para Casa:* {dados.get('para_casa')}\n"
                f"❌ *Não Fez:* {', '.join(map(str, nao_fez_dict.get('alunos', []))) if nao_fez_dict.get('alunos') else 'Nenhum'}\n"
                f"🪑 *Faltas:* {', '.join(map(str, dados.get('faltas', []))) if dados.get('faltas') else 'Nenhuma'}\n\n"
                f"_Se errou algo, digite /fila para cancelar antes do Vigia passar._"
            )
            await query.edit_message_text(resumo_aula, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Erro ao salvar aula na planilha: `{e}`", parse_mode='Markdown')

    elif query.data == "SALVAR_NOTAS":
        await query.edit_message_text("⏳ Estruturando a planilha de notas para o Vigia...")

        notas_ditadas = dados.get("notas", {})

        def job_salvar_notas():
            planilha = conectar_sheets()
            nome_aba_alunos = buscar_aba_oficial(planilha, "alunos_", str(dados.get("turma", "")).strip(), unidade, fallback=False)
            nome_aba_notas = buscar_aba_oficial(planilha, "Notas_", str(dados.get("turma", "")).strip(), unidade)

            if nome_aba_alunos:
                dados_alunos = planilha.worksheet(nome_aba_alunos).get_all_values()
            else:
                dados_alunos = []

            try:
                matriz_notas = planilha.worksheet(nome_aba_notas).get_all_values()
            except Exception:
                planilha.add_worksheet(title=nome_aba_notas, rows="100", cols="20")
                matriz_notas = []

            if len(matriz_notas) < 7:
                matriz_notas = [
                    ["Nº", "Nome da Avaliação"],
                    ["-", "-"],
                    ["-", "-"],
                    ["-", "-"],
                    ["-", "-"],
                    ["-", "-"]
                ]
                if dados_alunos:
                    for linha_aluno in dados_alunos[1:]:
                        matriz_notas.append([linha_aluno[0], linha_aluno[1]])

            nome_prova = str(dados.get("nome_prova", "")).strip()
            col_idx = next((i for i, cab in enumerate(matriz_notas[0]) if str(cab).lower() == nome_prova.lower()), -1)

            if col_idx == -1:
                col_idx = len(matriz_notas[0])
                for linha in matriz_notas:
                    linha.append("")

            max_cols = max(len(linha) for linha in matriz_notas)
            for linha in matriz_notas:
                while len(linha) < max_cols:
                    linha.append("")

            matriz_notas[0][col_idx] = nome_prova
            matriz_notas[1][col_idx] = str(chat_id)
            matriz_notas[2][col_idx] = "Pendente"
            matriz_notas[3][col_idx] = str(dados.get("data", ""))
            matriz_notas[4][col_idx] = str(dados.get("valor", ""))
            matriz_notas[5][col_idx] = str(dados.get("disciplina", ""))

            for row_idx in range(6, len(matriz_notas)):
                num_aluno = str(matriz_notas[row_idx][0]).strip()
                if num_aluno in notas_ditadas:
                    matriz_notas[row_idx][col_idx] = str(notas_ditadas[num_aluno])

            ws_notas = planilha.worksheet(nome_aba_notas)
            ws_notas.clear()
            ws_notas.update(matriz_notas)

        try:
            await asyncio.to_thread(job_salvar_notas)
            resumo_notas = (
                f"✅ **Notas Lançadas no Banco!**\n\n"
                f"🏫 *Turma:* {dados.get('turma')}\n"
                f"📌 *Prova:* {dados.get('nome_prova')}\n"
                f"📅 *Data:* {dados.get('data')}\n"
                f"🎯 *Valor:* {dados.get('valor')}\n"
                f"👥 *Alunos Avaliados:* {len(notas_ditadas)}\n\n"
                f"_Se errou algo, digite /fila para cancelar antes do Vigia passar._"
            )
            await query.edit_message_text(resumo_notas, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Erro ao estruturar notas na planilha: `{e}`", parse_mode='Markdown')

    return ConversationHandler.END

# ================= MÓDULO DO FLASK E TELEGRAM =================
bot_app = Application.builder().token(TELEGRAM_TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        MessageHandler(filters.PHOTO, receber_foto_quadro),
        MessageHandler(filters.VOICE, processar_audio),
        MessageHandler(filters.TEXT & ~filters.COMMAND, processar_texto_livre),
        CallbackQueryHandler(lidar_botoes),
        CommandHandler("vistos", comando_vistos),
        CommandHandler("raiox", comando_raiox)
    ],
    states={
        AGUARDANDO_CORRECAO: [MessageHandler(filters.TEXT & ~filters.COMMAND, coletar_correcao)],
        VISTOS_TURMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_turma_vistos)],
        VISTOS_NOTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nota_vistos)],
        VISTOS_DATAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_datas_vistos)],
        RAIOX_TURMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_turma_raiox)],
        AGUARDANDO_LGPD: [CallbackQueryHandler(lidar_lgpd)],
        ONBOARDING_NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_nome)],
        ONBOARDING_UNIDADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_unidade)],
        ONBOARDING_CODIGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_codigo)],
        ONBOARDING_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_login)],
        ONBOARDING_SENHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_senha)]
    },
    fallbacks=[CommandHandler("start", start)],
    per_message=False
)

bot_app.add_handler(CommandHandler("etapa", comando_etapa))
bot_app.add_handler(CommandHandler("senha", comando_senha))
bot_app.add_handler(CommandHandler("scan", comando_scan))
bot_app.add_handler(CommandHandler("fila", comando_fila))
bot_app.add_handler(conv_handler)

_bot_initialized = False

@app.route('/')
def index():
    return "Bot Assessor.IA Multi-Usuário 24/7", 200

@app.route('/setup')
def setup_webhook():
    requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={URL_PYTHONANYWHERE}/{TELEGRAM_TOKEN}")
    return "OK", 200

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    global _bot_initialized
    update = Update.de_json(request.get_json(force=True), bot_app.bot)

    try:
        loop = asyncio.get_event_loop()
    except Exception:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if not _bot_initialized:
        loop.run_until_complete(bot_app.initialize())
        _bot_initialized = True

    loop.run_until_complete(bot_app.process_update(update))
    return 'OK', 200

if __name__ == "__main__":
    bot_app.run_polling()
