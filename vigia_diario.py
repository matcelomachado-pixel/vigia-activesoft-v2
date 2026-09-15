import os
import time
import re
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

def traduzir_nome_para_activesoft(nome_sujo):
    """Lê o nome sujo da aba e traduz para o formato humano (Ex: 9º ANO A)"""
    match = re.search(r'(\d)([A-Z])$', nome_sujo.upper())
    if match:
        numero = match.group(1)
        letra = match.group(2)
        if "FUNDAMENTAL" in nome_sujo.upper() or int(numero) > 5:
            return f"{numero}º ANO {letra}"
        else:
            return f"{numero}ª SÉRIE {letra}"
    return nome_sujo

def selecionar_dropdown_iframe(navegador, palavra_chave, texto_para_digitar):
    """Utiliza o JavaScript Executor (Trator) para forçar o clique na caixa e na lista"""
    wait = WebDriverWait(navegador, 15)
    
    def tentar_selecionar(driver):
        try:
            # 1. Localiza a caixa suspensa procurando pela label (Turma ou Fase)
            xpath_caixa = f"//label[contains(., '{palavra_chave}')]/following-sibling::div"
            caixa = wait.until(EC.presence_of_element_located((By.XPATH, xpath_caixa)))
            
            # Força o clique diretamente na caixa via JavaScript para abri-la
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", caixa)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", caixa)
            time.sleep(1.5)
            
            # 2. Digita o texto para filtrar a lista
            try:
                input_field = caixa.find_element(By.TAG_NAME, "input")
                input_field.send_keys(texto_para_digitar)
            except:
                ativo = driver.switch_to.active_element
                ativo.send_keys(texto_para_digitar)
                
            time.sleep(2) # Aguarda o Activesoft processar a busca e gerar o HTML flutuante
            
            # 3. Força o clique na opção exata via JavaScript
            # Procura por qualquer elemento (li, span, div) que contenha o texto
            xpath_opcao = f"//*[contains(text(), '{texto_para_digitar}') and not(contains(@class, 'input'))]"
            opcoes = driver.find_elements(By.XPATH, xpath_opcao)
            
            clicado = False
            for opcao in reversed(opcoes): # Lemos de trás pra frente caso haja sobreposição no HTML
                driver.execute_script("arguments[0].click();", opcao)
                clicado = True
                break
                    
            if not clicado:
                driver.switch_to.active_element.send_keys(Keys.ENTER)
                
            time.sleep(1.5)
            return True
        except:
            return False

    # Vasculha a página e os iframes procurando o campo
    navegador.switch_to.default_content()
    if tentar_selecionar(navegador): return True
    
    iframes = navegador.find_elements(By.TAG_NAME, "iframe") + navegador.find_elements(By.TAG_NAME, "frame")
    for iframe in iframes:
        navegador.switch_to.default_content()
        try:
            navegador.switch_to.frame(iframe)
            if tentar_selecionar(navegador): return True
        except: pass
        
    return False

def rodar_lancamentos():
    print("="*60)
    print(" 🚀 VIGIA DIÁRIO: LANÇADOR DE FALTAS E NOTAS")
    print("="*60)
    
    planilha = conectar_sheets()
    try:
        aba_config = planilha.worksheet("Configuracoes")
        etapa_atual = aba_config.acell('B1').value or "3ª Etapa"
    except:
        etapa_atual = "3ª Etapa"
        
    aba_usuarios = planilha.worksheet("Usuarios")
    dados_usuarios = aba_usuarios.get_all_values()
    
    professores_ativos = []
    for i, row in enumerate(dados_usuarios[1:]):
        if len(row) >= 6 and str(row[0]).strip():
            professores_ativos.append({"chat_id": str(row[0]).strip(), "nome": str(row[1]).strip(), "codigo": str(row[3]).strip(), "login": str(row[4]).strip(), "senha": str(row[5]).strip()})

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")

    for prof in professores_ativos:
        print(f"\n🔍 Iniciando Lançamentos para: {prof['nome']}")
        navegador = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(navegador, 15)
        
        try:
            navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/")
            wait.until(EC.presence_of_element_located((By.ID, "codigoInstituicao"))).send_keys(prof['codigo'])
            navegador.find_element(By.XPATH, "//input[contains(@placeholder, 'login')]").send_keys(prof['login'])
            navegador.find_element(By.XPATH, "//input[@type='password']").send_keys(prof['senha'])
            navegador.find_element(By.XPATH, "//button[contains(text(), 'Entrar') or @data-cy='botao-login']").click()
            time.sleep(5)
            
            abas = planilha.worksheets()
            abas_registros = [aba for aba in abas if aba.title.startswith("registos_")]
            
            for aba in abas_registros:
                dados_aula = aba.get_all_records()
                linhas_pendentes = [i + 2 for i, row in enumerate(dados_aula) if str(row.get('Status_Falta', '')).strip().upper() == 'PENDENTE_NOVA']
                
                if not linhas_pendentes: continue
                    
                nome_turma_bruto = aba.title.replace("registos_", "")
                nome_turma_bonito = traduzir_nome_para_activesoft(nome_turma_bruto)
                print(f" -> Turma bruta: {nome_turma_bruto} | Traduzida: {nome_turma_bonito}")
                
                print(" -> Acessando menu de Frequência...")
                try:
                    menu_freq = wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Frequência em lote')]")))
                    navegador.execute_script("arguments[0].click();", menu_freq)
                except:
                    navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/frequencia_lote/")
                
                wait_long = WebDriverWait(navegador, 20)
                time.sleep(5) 
                
                print(f" -> Selecionando etapa: {etapa_atual}")
                selecionar_dropdown_iframe(navegador, "Fase", etapa_atual)
                
                print(f" -> Selecionando turma no menu: {nome_turma_bonito}")
                sucesso = selecionar_dropdown_iframe(navegador, "Turma", nome_turma_bonito)
                
                if not sucesso:
                    raise Exception(f"Não consegui selecionar a turma {nome_turma_bonito} via JavaScript.")
                
                # Clica em Consultar
                navegador.switch_to.default_content() 
                for f in navegador.find_elements(By.TAG_NAME, "iframe") + navegador.find_elements(By.TAG_NAME, "frame"):
                    navegador.switch_to.default_content()
                    try:
                        navegador.switch_to.frame(f)
                        btn = wait.until(EC.presence_of_element_located((By.XPATH, "//button[normalize-space(text())='CONSULTAR']")))
                        navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.5)
                        navegador.execute_script("arguments[0].click();", btn)
                        break
                    except: pass
                
                print(" -> Botão CONSULTAR clicado. Aguardando a tabela...")
                time.sleep(5)
                
                # =================================================================
                # (AQUI ENTRA A LÓGICA DE MARCAR AS FALTAS NA TABELA QUE VOCÊ JÁ TEM)
                # =================================================================
                
                for linha in linhas_pendentes:
                    aba.update_cell(linha, 11, "CONCLUIDO")
                avisar_telegram(prof['chat_id'], f"✅ **Tela carregada com sucesso!**\nTurma: {nome_turma_bonito}")

        except Exception as e:
            try:
                navegador.save_screenshot("erro_diario.png")
                mandar_print_telegram(prof['chat_id'], "erro_diario.png", f"🚨 *Erro ao lançar diário*\n\n`{str(e)[:150]}`")
            except: pass
        finally:
            navegador.quit()

if __name__ == "__main__":
    rodar_lancamentos()
