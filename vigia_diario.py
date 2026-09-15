import os
import time
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import urllib3
import ssl
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try: ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError: pass

SPREADSHEET_ID = '17XZfEUKiiryGJgj_nXdQ7gXzdByEwsZ7ecax44ZeJmc'
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def avisar_telegram(chat_id, mensagem):
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try: requests.post(url, json={"chat_id": chat_id, "text": mensagem, "parse_mode": "HTML"}, timeout=10)
    except: pass

def mandar_print_telegram(chat_id, caminho_imagem, legenda=""):
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        with open(caminho_imagem, 'rb') as f:
            requests.post(url, data={"chat_id": chat_id, "caption": legenda}, files={"photo": f}, timeout=15)
    except: pass

def conectar_sheets():
    creds = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", SCOPE) 
    return gspread.authorize(creds).open_by_key(SPREADSHEET_ID)

def selecionar_dropdown(navegador, xpath_input, texto_para_digitar):
    """
    Simula o clique humano em menus suspensos do Activesoft: clica, digita, espera e aperta ENTER.
    """
    wait = WebDriverWait(navegador, 10)
    try:
        # Tenta achar o campo de input (geralmente escondido dentro da caixa visível)
        campo = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_input)))
        navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo)
        time.sleep(0.5)
        campo.click()
        time.sleep(0.5)
        campo.send_keys(Keys.CONTROL + "a")
        campo.send_keys(Keys.DELETE)
        campo.send_keys(texto_para_digitar)
        time.sleep(1.5) # Tempo crucial para o Activesoft filtrar a listinha
        campo.send_keys(Keys.ENTER) # O "clique" matador na opção
        time.sleep(1)
        return True
    except Exception as e:
        print(f"Erro ao selecionar dropdown: {e}")
        return False

def rodar_lancamentos():
    print("="*60)
    print(" 🚀 VIGIA DIÁRIO: LANÇADOR DE FALTAS E NOTAS")
    print("="*60)
    
    planilha = conectar_sheets()
    
    # Busca a etapa atual e o nome da turma na aba de Configurações
    try:
        aba_config = planilha.worksheet("Configuracoes")
        etapa_atual = aba_config.acell('B1').value or "3ª Etapa"
    except:
        etapa_atual = "3ª Etapa" # Padrão se não achar
        
    aba_usuarios = planilha.worksheet("Usuarios")
    dados_usuarios = aba_usuarios.get_all_values()
    
    professores_ativos = []
    for i, row in enumerate(dados_usuarios[1:]):
        if len(row) >= 6 and str(row[0]).strip():
            professores_ativos.append({
                "chat_id": str(row[0]).strip(),
                "nome": str(row[1]).strip(),
                "codigo": str(row[3]).strip(),
                "login": str(row[4]).strip(),
                "senha": str(row[5]).strip()
            })

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")

    for prof in professores_ativos:
        print(f"\n🔍 Iniciando Lançamentos para: {prof['nome']}")
        navegador = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(navegador, 15)
        
        try:
            # LOGIN
            navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/")
            wait.until(EC.presence_of_element_located((By.ID, "codigoInstituicao"))).send_keys(prof['codigo'])
            navegador.find_element(By.XPATH, "//input[contains(@placeholder, 'login')]").send_keys(prof['login'])
            navegador.find_element(By.XPATH, "//input[@type='password']").send_keys(prof['senha'])
            navegador.find_element(By.XPATH, "//button[contains(text(), 'Entrar') or @data-cy='botao-login']").click()
            time.sleep(5)
            
            # Buscando todas as abas de registros do professor
            abas = planilha.worksheets()
            abas_registros = [aba for aba in abas if aba.title.startswith("registos_")]
            
            if not abas_registros:
                print(" -> Nenhuma aba de registros encontrada. Finalizando.")
                continue

            for aba in abas_registros:
                dados_aula = aba.get_all_records()
                linhas_pendentes = [i + 2 for i, row in enumerate(dados_aula) if str(row.get('Status_Falta', '')).strip().upper() == 'PENDENTE_NOVA']
                
                if not linhas_pendentes:
                    continue
                    
                nome_turma_bruto = aba.title.replace("registos_", "") # Pega o nome gerado pelo Scan
                print(f" -> Lançando faltas para a turma: {nome_turma_bruto}")
                
                # NAVEGAR ATÉ FREQUÊNCIA EM LOTE
                navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/frequencia_lote/")
                time.sleep(4)
                
                # 1. Seleciona a Etapa/Fase de nota com o ENTER
                print(f" -> Selecionando etapa: {etapa_atual}")
                # Ajuste o XPATH abaixo se o id do campo de Fase for diferente
                selecionar_dropdown(navegador, "//label[contains(text(), 'Fase') or contains(text(), 'Etapa')]/following-sibling::div//input", etapa_atual)
                
                # 2. Seleciona a Turma com o ENTER
                print(" -> Selecionando turma no menu...")
                # Ajuste o XPATH abaixo com o seletor exato do input da turma (onde fica piscando o cursor)
                sucesso_turma = selecionar_dropdown(navegador, "//label[contains(text(), 'Turma')]/following-sibling::div//input", nome_turma_bruto)
                
                if not sucesso_turma:
                    raise Exception(f"Não consegui selecionar a turma {nome_turma_bruto} no menu suspenso.")
                
                # Clica em Consultar
                navegador.find_element(By.XPATH, "//button[normalize-space(text())='CONSULTAR']").click()
                time.sleep(5)
                
                # =================================================================
                # (AQUI ENTRA A LÓGICA DE MARCAR AS FALTAS NA TABELA QUE VOCÊ JÁ TEM)
                # =================================================================
                
                # Após lançar tudo com sucesso, atualiza a planilha
                for linha in linhas_pendentes:
                    aba.update_cell(linha, 11, "CONCLUIDO") # 11 é a coluna K (Status_Falta)
                    
                avisar_telegram(prof['chat_id'], f"✅ **Faltas Lançadas!**\nTurma: {nome_turma_bruto}\nEtapa: {etapa_atual}")

        except Exception as e:
            try:
                navegador.save_screenshot("erro_diario.png")
                mandar_print_telegram(prof['chat_id'], "erro_diario.png", f"🚨 *Erro ao lançar diário*\n\nMotivo:\n`{str(e)[:150]}`")
            except: pass
        finally:
            navegador.quit()

if __name__ == "__main__":
    rodar_lancamentos()
