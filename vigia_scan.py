import os
import time
import re
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import urllib3
import ssl
import requests
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try: ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError: pass

SPREADSHEET_ID = '17XZfEUKiiryGJgj_nXdQ7gXzdByEwsZ7ecax44ZeJmc'
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def limpar_nome_aba(texto):
    t = str(texto).upper().replace("ANO", "").replace("SÉRIE", "").replace("SERIE", "")
    return re.sub(r'[^A-Z0-9]', '', t)

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

def achar_e_clicar(navegador, xpath_alvo, tempo_espera=3):
    navegador.switch_to.default_content()
    try:
        btn = WebDriverWait(navegador, tempo_espera).until(EC.presence_of_element_located((By.XPATH, xpath_alvo)))
        navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
        time.sleep(0.5); navegador.execute_script("arguments[0].click();", btn)
        return True
    except: pass
        
    for f in navegador.find_elements(By.TAG_NAME, "iframe") + navegador.find_elements(By.TAG_NAME, "frame"):
        navegador.switch_to.default_content()
        try:
            navegador.switch_to.frame(f)
            btn = WebDriverWait(navegador, tempo_espera).until(EC.presence_of_element_located((By.XPATH, xpath_alvo)))
            navegador.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            time.sleep(0.5); navegador.execute_script("arguments[0].click();", btn)
            return True
        except: pass
    return False

def buscar_linhas_tabela(navegador):
    navegador.switch_to.default_content()
    linhas = navegador.find_elements(By.XPATH, "//tbody/tr")
    if len(linhas) > 1: return linhas
    
    for f in navegador.find_elements(By.TAG_NAME, "iframe") + navegador.find_elements(By.TAG_NAME, "frame"):
        navegador.switch_to.default_content()
        try:
            navegador.switch_to.frame(f)
            linhas = navegador.find_elements(By.XPATH, "//tbody/tr")
            if len(linhas) > 1: return linhas
        except: pass
    return []

def construir_banco_de_dados():
    print("="*60)
    print(" 🛠️ VIGIA SCAN: CONSTRUTOR DE BANCO DE DADOS (ONBOARDING)")
    print("="*60)
    
    planilha = conectar_sheets()
    aba_usuarios = planilha.worksheet("Usuarios")
    dados_usuarios = aba_usuarios.get_all_values()
    
    professores_pendentes = []
    for i, row in enumerate(dados_usuarios[1:]):
        linha_sheets = i + 2
        if len(row) >= 8 and str(row[7]).strip() == "PENDENTE":
            professores_pendentes.append({
                "linha": linha_sheets, "chat_id": str(row[0]).strip(),
                "nome": str(row[1]).strip(), "codigo": str(row[3]).strip(),
                "login": str(row[4]).strip(), "senha": str(row[5]).strip()
            })

    if not professores_pendentes:
        print("🟢 Nenhum professor na fila de Onboarding.")
        return

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    for prof in professores_pendentes:
        print(f"\n🔍 Iniciando Scan para: {prof['nome']}")
        navegador = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(navegador, 15)
        
        try:
            navegador.get("https://siga02.activesoft.com.br/portal_eb_professor/")
            wait.until(EC.presence_of_element_located((By.ID, "codigoInstituicao"))).send_keys(prof['codigo'])
            navegador.find_element(By.XPATH, "//input[contains(@placeholder, 'login')]").send_keys(prof['login'])
            navegador.find_element(By.XPATH, "//input[@type='password']").send_keys(prof['senha'])
            navegador.find_element(By.XPATH, "//button[contains(text(), 'Entrar') or @data-cy='botao-login']").click()
            time.sleep(5)
            
            try: WebDriverWait(navegador, 3).until(EC.element_to_be_clickable((By.XPATH, "//img[@alt='Activesoft Logo']"))).click(); time.sleep(2)
            except: pass 
            
            print(" -> Acessando tela de Ocorrências...")
            if not achar_e_clicar(navegador, "//*[@id='ocorrencias_de_alunos'] | //*[contains(text(), 'Ocorrências de alunos')]", 5):
                raise Exception("Falha ao clicar no menu 'Ocorrências de alunos'.")
            time.sleep(3)
            
            if not achar_e_clicar(navegador, "//*[contains(text(), 'Registrar ocorrência')] | //a[@href='/gerar_ocorrencias_lote/']", 5):
                raise Exception("Falha ao clicar no submenu 'Registrar ocorrência'.")
            time.sleep(3)
            
            if not achar_e_clicar(navegador, "//button[normalize-space(text())='Pesquisar']", 5):
                raise Exception("Falha ao achar o botão de 'Pesquisar'.")
            
            print(" -> Aguardando o carregamento inicial dos alunos...")
            time.sleep(12) 
            
            turmas_coletadas = {} 
            limite_scrolls = 0 
            tentativas_sem_novos_alunos = 0
            total_alunos_anterior = 0
            
            while limite_scrolls < 50: # Trava de no máximo 50 rolagens
                limite_scrolls += 1
                linhas = buscar_linhas_tabela(navegador)
                
                if not linhas:
                    time.sleep(5)
                    linhas = buscar_linhas_tabela(navegador)
                
                for linha in linhas:
                    try:
                        tds = linha.find_elements(By.TAG_NAME, "td")
                        texto_turma = ""
                        numero = ""
                        nome_aluno = ""
                        
                        for td in tds:
                            txt = td.text.strip()
                            if not txt: continue
                            
                            if "ANO" in txt.upper() or "SÉRIE" in txt.upper() or "SERIE" in txt.upper():
                                texto_turma = txt.upper()
                            elif txt.isdigit() and not numero:
                                numero = txt
                            elif len(txt) > 4 and not txt.isdigit() and "SÉRIE" not in txt.upper() and not nome_aluno:
                                nome_aluno = txt.title()
                                
                        if texto_turma and nome_aluno:
                            if texto_turma not in turmas_coletadas:
                                turmas_coletadas[texto_turma] = []
                            # Adiciona só se o aluno ainda não existir na turma
                            if not any(a['nome'] == nome_aluno for a in turmas_coletadas[texto_turma]):
                                turmas_coletadas[texto_turma].append({"n": numero, "nome": nome_aluno})
                    except: pass
                
                total_atual = sum(len(alunos) for alunos in turmas_coletadas.values())
                
                # Verifica se a rolagem trouxe alunos novos
                if total_atual == total_alunos_anterior and total_atual > 0:
                    tentativas_sem_novos_alunos += 1
                    if tentativas_sem_novos_alunos >= 3:
                        print(" -> Fim da lista atingido (nenhum aluno novo após 3 rolagens).")
                        break
                else:
                    tentativas_sem_novos_alunos = 0
                    total_alunos_anterior = total_atual
                
                # Executa a rolagem (Scroll) para o final da tabela!
                try:
                    if linhas:
                        print(f" -> Rolando a página para baixo... (Lidos até agora: {total_atual})")
                        navegador.execute_script("arguments[0].scrollIntoView({block: 'end'});", linhas[-1])
                        time.sleep(4) # Espera 4 segs para o Activesoft processar o carregamento
                except: 
                    time.sleep(3)

            total_turmas = len(turmas_coletadas)
            print(f" ✅ Scan Finalizado: {total_turmas} Turmas e {total_atual} Alunos!")

            if total_turmas == 0:
                raise Exception("Tabela carregou vazia (0 alunos).")

            print(" -> Criando Banco de Dados no Google Sheets...")
            for turma_nome, alunos in turmas_coletadas.items():
                turma_limpa = limpar_nome_aba(turma_nome)
                
                nome_aba_alunos = f"alunos_{turma_limpa}"
                df_alunos = pd.DataFrame(alunos).rename(columns={"n": "Nº", "nome": "Nome"})
                df_alunos['Nº'] = pd.to_numeric(df_alunos['Nº'], errors='coerce')
                df_alunos = df_alunos.sort_values(by='Nº').fillna("")
                
                try: ws_al = planilha.worksheet(nome_aba_alunos); ws_al.clear()
                except: ws_al = planilha.add_worksheet(title=nome_aba_alunos, rows="100", cols="5")
                ws_al.update([df_alunos.columns.values.tolist()] + df_alunos.values.tolist())
                
                nome_aba_reg = f"registos_{turma_limpa}"
                colunas_reg = ["Data", "Resumo", "Para Casa", "Faltas", "Nao_Fez", "Tarefa_Nao_Feita", "Advertencias", "Destaques", "Status_Diario", "Status_Ocorrencia", "Status_Falta", "ID_Professor"]
                try: planilha.worksheet(nome_aba_reg)
                except:
                    ws_reg = planilha.add_worksheet(title=nome_aba_reg, rows="100", cols="15")
                    ws_reg.update([colunas_reg])

                nome_aba_notas = f"Notas_{turma_limpa}"
                try: planilha.worksheet(nome_aba_notas)
                except:
                    ws_not = planilha.add_worksheet(title=nome_aba_notas, rows="100", cols="15")
                    matriz_base = [["Nº", "Nome da Avaliação"], ["-", "-"], ["-", "-"], ["-", "-"], ["-", "-"]]
                    for _, r_aluno in df_alunos.iterrows(): matriz_base.append([str(r_aluno['Nº'])[:-2] if str(r_aluno['Nº']).endswith(".0") else str(r_aluno['Nº']), str(r_aluno['Nome'])])
                    ws_not.update(matriz_base)

            aba_usuarios.update_cell(prof['linha'], 8, "CONCLUIDO")
            
            msg_final = f"✅ **Banco de Dados Construído!**\n\nEu entrei no seu Activesoft e mapeei:\n🏫 **{total_turmas} Turmas**\n👥 **{total_atual} Alunos**\n\nTodas as abas foram criadas com o nome oficial."
            avisar_telegram(prof['chat_id'], msg_final)

        except Exception as e:
            try:
                navegador.save_screenshot("erro_scan.png")
                mandar_print_telegram(prof['chat_id'], "erro_scan.png", f"🚨 *Erro no Robô Scan*\n\nTravei no meio do caminho. Motivo:\n`{str(e)[:150]}`\n\nVeja a foto da tela exata onde eu parei:")
            except: pass
            aba_usuarios.update_cell(prof['linha'], 8, "") 
        finally:
            navegador.quit()

if __name__ == "__main__":
    construir_banco_de_dados()
