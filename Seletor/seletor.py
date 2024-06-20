from queue import Queue
from time import perf_counter, sleep
from flask import Flask,jsonify, make_response,request
from datetime import time,datetime,timedelta
import requests as rq
import uuid
import threading
import random

app = Flask(__name__)
job_queue = Queue()


processing_thread = None

relogio_atual = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
validadores_cadastrados = []
ultimos_escolhidos = []

Fila_de_espera = []
validadores_que_sairam_da_fila = []
ids_validadores_selecionados = []
validadores_escolhidos = []

#################### Estrutura de dados do Seletor ############################

class Seletor():
    nome:str
    ip:str
    carteira_validador:float
    def __init__(self,nome,ip):
        self.nome=nome
        self.ip=ip
        self.carteira_validador = 0

class Validador():
    id:str
    saldo:str
    ip:str
    token:str
    vezes_expulso:int
    flag:int
    vezes_escolhido:int
    em_hold:bool
    foi_expulso_ultima_vez:bool
    def __init__(self,id,saldo,ip,token, foi_expulso_ultima_vez):
        self.id = id
        self.saldo = saldo
        self.ip = ip
        self.token = token
        self.vezes_expulso = 0
        self.flag = 0
        self.foi_expulso_ultima_vez = foi_expulso_ultima_vez

    def escolhidoCincoVezes(self):
        if self.vezes_escolhido==5 or self.em_hold:
            self.em_hold=True
            return True
        else:
            self.vezes_escolhido+=1
            return False

    def contatadorHold(self):
        if self.em_hold:
            self.vezes_escolhido-=1
        if self.vezes_escolhido==0:
            self.em_hold=False

    def zerarContador(self):
        if self.em_hold == False:
            self.vezes_escolhido=0

    def incrementarFlag(self):
        self.flag+=1
        if self.flag > 2:
            self.vezes_expulso += 1
            self.foi_expulso_ultima_vez = True

#################### Funções do Seletor ############################

# Função para processar jobs da fila
def process_jobs():
    global job_atual
    while True:
        job = job_queue.get()
        if job is None:
            break
        job_atual = job
        process_job(job)
        job_queue.task_done()
            
        
def process_job(job):
    print("Job recebido")
    validadores_validos = []

    # Request para obter o saldo do cliente
    while True:
        try:
            response = rq.get(f"http://127.0.0.1:5000/cliente/{job['remetente']}")  # Solicitação GET para obter o cliente
            if response.status_code == 200:
                cliente_data = response.json()
                saldo_cliente = cliente_data.get("qtdMoeda")
                job["saldo"] = saldo_cliente
                break 
            else:
                print("Falha ao obter o saldo do cliente. Código de status:", response.status_code)
        except Exception as e:
            print("Erro ao processar a solicitação:", e)
            time.sleep(1)

    for validador in Fila_de_espera:
        if validador.em_hold == False:
            validadores_validos.append(validador)
    
    if len(validadores_validos) < 3:
        print("Não existem validadores suficientes na fila para validar")
        segundos = 0
        while len(validadores_validos) < 3 and segundos != 60:
            for validador in Fila_de_espera:
                if validador not in validadores_validos:
                    validadores_validos.append(validador)
            time.sleep(1)
            segundos += 1
            print(f"Segundos restantes: {segundos}")
                    
        if len(validadores_validos) < 3 and segundos == 60:
            print("Tempo esgotado, não foi possível validar a job pois não existem validadores válidos suficientes para validar a job")
            #return "Job não validada"
            #fazer post com status job 0
            return
        

        verificar_fila(validadores_validos)   
        sincronismo_relogios(validadores_que_sairam_da_fila)
        validadores_escolhidos = selecionar_validadores(validadores_que_sairam_da_fila) # retorna json dos validadores escolhidos
        colocar_na_fila(validadores_que_sairam_da_fila,validadores_escolhidos)
        lista_consenso = enviar_job_validador(validadores_escolhidos,job)
        status_aprovacao =validar_consenso(lista_consenso)
        #
        #
        #
        #
    else:
        verificar_fila(validadores_validos)
        sincronismo_relogios(validadores_que_sairam_da_fila)
        validadores_escolhidos = selecionar_validadores(validadores_que_sairam_da_fila) # retorna json dos validadores escolhidos
        colocar_na_fila(validadores_que_sairam_da_fila,validadores_escolhidos)
        lista_consenso = enviar_job_validador(validadores_escolhidos,job)
        status_aprovacao =validar_consenso(lista_consenso)
        #
        #
        #
        #
        #

    while True:
        try:
            response = rq.post(f"http://127.0.0.1:5000/transacoes/{job['id']}/{status_aprovacao}")
            if response.status_code == 200:
                print("Modificação de transação enviada banco")
                break
        except rq.exceptions.RequestException as e:
            print(f"Erro ao mandar informação ao banco: {e}")

    if status_aprovacao == 1:
        # Tem que ser valor+taxas
        taxas = job["valor"] * 0.015
    
        quantia_rem = job["saldo"] - (taxas + job["valor"])
        response = rq.post(f"http://127.0.0.1:5000/cliente/{job['remetente']}/{quantia_rem}")
        
        response = rq.get(f"http://127.0.0.1:5000/cliente/{job['recebedor']}")
        cliente_data = response.json()
        quantia_dest = cliente_data.get("qtdMoeda")
        
        quantia_dest =  quantia_dest + (job["valor"])
        response = rq.post(f"http://127.0.0.1:5000/cliente/{job['recebedor']}/{quantia_dest}")

        #recompensas
        seletor_atual.carteira_validador += job["valor"] * 0.005

        for validor
        
        for validador in validadores_cadastrados:
            validador.contatadorHold()

        for validador in validadores_cadastrados:
            if validador.id in validadores_escolhidos:
                validador.saldo += job["valor"] * 0.0033333
                
                Fila_de_espera.append(validador)
                if validador in ultimos_escolhidos:
                    validador.escolhidoCincoVezes()

        ultimos_escolhidos.clear()
        for validador in validadores_cadastrados:
            if validador.id in validadores_escolhidos:
                ultimos_escolhidos.append(validador)

    return "Job validada"
        
        
###########################fim do processo de Jobs#####################################
# 
# 
# 
# 
##################################Funções dos jobs###################################

def selecionar_validadores(validadores_fila):
    id_validadores = []
    pesos_validadores = []
    for validador in validadores_fila:
        if validadores_fila.flag==0:
            id_validadores.append(validador.id)
            pesos_validadores.append(validador.saldo)     
        elif validadores_fila.flag==1:
            id_validadores.append(validador.id)
            pesos_validadores.append(validador.saldo*0.5)     
        else:
            id_validadores.append(validador.id)
            pesos_validadores.append(validador.saldo*0.25)     
            
    #maior saldo
    escolhidos = []
    for n in range(3):
        maior = 0
        for x in range(1,len(pesos_validadores)):
            if pesos_validadores[maior]<pesos_validadores[x]:
                maior = x

        pesos_validadores[x] = 20
        #distribuição comforme saldo
        total_pesos=0
        for x in range(0,len(pesos_validadores)):
            if x != maior:
                total_pesos+=pesos_validadores[x]
        for x in range(0,len(pesos_validadores)):
            if x != maior:
                pesos_validadores[x] = (pesos_validadores[x]/total_pesos)*100

        #Sorteio 3 validadores
        
        escolhido = random.choices(id_validadores,pesos_validadores)[0]
        escolhidos.append(escolhido)
        for x in range(0,len(id_validadores)):
            if id_validadores[x] == escolhido:
                break
        pesos_validadores.pop(x)
        id_validadores.pop(x)


    return escolhidos

def colocar_na_fila(validadores,ids_escolhidos):
    for validador in validadores:
        if validador.id not in ids_escolhidos:
            Fila_de_espera.append(validador)

def enviar_job_validador(id_validadores,job):
    lista_consenso = []
    for validador in validadores_cadastrados:
        if validador.id in id_validadores:
            url = "http://"+validador.ip+"/validador/validarJob"
            resposta = rq.post(url,json=job)
            lista_consenso.append(resposta)
         
    return lista_consenso


def validar_consenso(lista_consenso):
    sucessos = 0
    falhas = 0
    invalido = 0

    for verificacao in lista_consenso:
        for validador in validadores_cadastrados:
            if validador.id in verificacao['id_validor']:
                if verificacao["token"] == validador.token:
                    if verificacao['status']==1:
                        sucessos+=1
                    elif verificacao['status']==2:
                        falhas+=1
                    else:
                        invalido +=1
                else:
                    verificacao['status'] = 0
                    invalido += 1

    if sucessos>falhas and sucessos>invalido:
        for verificacao in lista_consenso:
            for validador in validadores_cadastrados:
                if validador.id in verificacao['id_validor']:
                    if verificacao["token"] == validador.token:
                        if verificacao['status']==2:
                            validador.incrementarFlag()
        return 1
    elif (falhas>sucessos and falhas>invalido) or sucessos==falhas:
        for verificacao in lista_consenso:
            for validador in validadores_cadastrados:
                if validador.id in verificacao['id_validor']:
                    if verificacao["token"] == validador.token:
                        if verificacao['status']==1:
                            validador.incrementarFlag()
        return 2
    elif invalido > sucessos and invalido > falhas and sucessos == 0 and falhas == 0:
        return 0



def verificar_fila(validadores_validos):

    print("Fila de espera validadores possui o minimo de validadores para validar!")
    x = len(validadores_validos)
    max = 0
    while(x > 0 and max < 6):
        validadores_que_sairam_da_fila.append(validadores_validos[0])
        validadores_validos.pop(0)
        x -=1
        max +=1
    print("Validadores que sairam da fila", validadores_que_sairam_da_fila)
    
    #apaga validadores escolhidos da fila de espera
    for validador in validadores_que_sairam_da_fila:
        if validador in Fila_de_espera:
            Fila_de_espera.remove(validador)
    
    if len(validadores_que_sairam_da_fila) >= 3:
        for validador in validadores_que_sairam_da_fila:
            #guarda ids para verificar se o id existe no banco ao receber a resposta da validacao 
            ids_validadores_selecionados.append(validador.id)
        


def enviarRelogio(validador_atual,relogio_final):
    tempo_1 = perf_counter()
    response = rq.post(f"http://{validador_atual.ip}/validador/receberRelogio",json={'relogio': relogio_final})
    if response.status_code == 200:
        tempo_2 = perf_counter()
        correcao_cristian = tempo_2 - tempo_1
        response = rq.post(f"http://{validador_atual.ip}/validador/receberAtraso",json={'atraso': correcao_cristian})
        

    
def pegarRelogioBanco():
    tempo_1 = perf_counter()
    response = rq.get("http://127.0.0.1:5000/hora")
    tempo_2 = perf_counter()
    correcao_cristian = tempo_2 - tempo_1
    relogio = response.json()
    relogio_final = datetime.strptime(relogio, '%Y-%m-%d %H:%M:%S.%f') + timedelta(seconds=correcao_cristian)
    print(relogio_final)
    #################
    #2024-06-11 00:19:45.906937
    ################
    return relogio_final

               

def sincronismo_relogios(lista_validadores): 
    lista_validadores
    global relogio_atual #SELETOR

    ###SINCRONIZAR
    relogio_atual = pegarRelogioBanco()
    for validador in lista_validadores:
        enviarRelogio(validador,relogio_atual)
    ####FIM DA SINCRONIZAÇÃO    
    ##print(f'Rotas coletadas da fila: {len(validadores)}')
       
    #log = f"Relogios dos seguintes validadores foram sincronizados usando o modelo de c: {lista_validadores}"
    #log = f"IDs foram distribuidos para os seguintes validadores: {lista_validadores}"
    #enviar_log_banco(log)   
                
                
                            
    
    
    
    """
    #adicionar +1 para vezes_escolhido_seguido e verifica se deve ser inserido no hold
    for validador in validadores_escolhidos:
        banco[validador["id_validador"]]["vezes_escolhido_seguido"] += 1
        if banco[validador["id_validador"]]["vezes_escolhido_seguido"] == 5:
            #adicionar validador em hold
            banco[validador["id_validador"]]["emHold"] = 5
    
    #resetar contador de escolhidos seguidos no banco e diminuir hold
    existe_in_lista = False
    for id_validador in banco: 
        
        for validador in validadores_escolhidos:
            if id_validador == validador["id_validador"]:
                existe_in_lista = True
                break
        
        if existe_in_lista == False:
            banco[id_validador]["vezes_escolhido_seguido"] = 0
    
        if banco[id_validador]["emHold"] > 0 and existe_in_lista == False:
            banco[id_validador]["emHold"] -=1
        
    
    
    
    
    
    log = f"Foram escolhidos os seguintes validadores para validar a job do remetente '{job["id_remetente"]}': {lista_validadores}"
    #enviar_log_banco(log)   
    print(validadores_escolhidos)
    #adicionando validadores que nao foram escolhidos no inicio da fila de espera
    for validador in lista_validadores:
        existe = any(dicionario.get("id_validador") == validador["id_validador"] for dicionario in validadores_escolhidos)
        if not existe:
            print(f"validador {validador['id_validador']} não foi escolhido, portanto irá ser inserido no início da fila novamente")
            Fila_de_espera.insert(0, validador)
    
    
    #mandar job para validadores escolhidos
    print("Validadores escolhidos que estão recebendo a job", validadores_escolhidos)
    for validador in validadores_escolhidos:
        while True:
            try:
                response = requests.post(validador["rota"] + '/validar_job', json=job)
                if response.status_code == 200:
                    print(f"Id enviado para {validador["rota"]}")
                    break 
            except requests.exceptions.RequestException as e:
                print(f"Erro ao conectar à rota {validador["rota"]}: {e}")
                print("Tentando novamente...")
    
    log = f"A job do remetente '{job["id_remetente"]}' foi enviada para os seguintes validadores: {lista_validadores}"
    #enviar_log_banco(log)

 """
     
#############################################################################################
#############################################################################################     
        
def cadastrar_seletor_banco(seletor_atual):
    while True: 
        try:
            response = rq.post(f"http://127.0.0.1:5000/seletor/{seletor_atual.nome}/{seletor_atual.ip}")
            if response.status_code == 200:
                print(f"Seletor cadastrado no banco")
                break
        except rq.exceptions.RequestException as e:
            print(f"Erro ao se cadastrar Seletor no banco: {e}")


#################### Rotas Flask do Seletor ############################    

@app.route('/seletor/cadastrarValidador', methods=["POST"])
def cadastrarValidador():
    dados_receber = request.json
    id = dados_receber.get('id')
    saldo = dados_receber.get('saldo')
    ip = dados_receber.get('ip')

    if id == "":
        if saldo < 50:
            resposta = make_response("Saldo insuficiente")
            resposta.headers['Content-type'] = 'text/plain'
            return resposta
        else:
            #criando o objeto validador
            id  = len(validadores_cadastrados) + 1
            if len(validadores_cadastrados) > 0:
                token_igual = False
                while token_igual:
                    token = str(uuid.uuid1())
                    for validador in validadores_cadastrados:
                        if validador.token == token:
                            token_igual = True
                print(token)
            else:
                token = str(uuid.uuid1())
            validador = Validador(id=id, saldo=saldo, ip=ip, token=token)
            validadores_cadastrados.append(validador)
            Fila_de_espera.append(validador)
            resposta = make_response(validador.token+" "+validador.id)
            resposta.headers['Content-type'] = 'text/plain'
            return resposta
    else:
        #verifica se validador existe no banco, caso contrario, avisar validador que id nao existe no banco
        validador_existe = False
        #verifica se validador no banco
        for validador in validadores_cadastrados:
            if validador.id == id:
                validador_existe = True
                validador_encontrado = validador
                break
        #se o validador existir no banco e tiver flags, verificar se o saldo que ele digitou compensa pelas vezes que foi expulso  
        #if validador_existe == True and validador_encontrado.vezes_expulso <= 2:
        if validador_existe == True:
            if validador_encontrado.vezes_expulso <= 2 and validador_encontrado.vezes_expulso > 0:
                if validador_encontrado.foi_expulso_ultima_vez == True:       # se foi expulso, verificar se novo saldo
                    if validador_encontrado.vezes_expulso == 1:
                        if not (saldo > 100 ):
                            resposta = make_response("Saldo insuficiente")
                            resposta.headers['Content-type'] = 'text/plain'
                            return resposta
                    elif validador_encontrado.vezes_expulso == 2:
                        if not (saldo > 200):
                            resposta = make_response("Saldo insuficiente")
                            resposta.headers['Content-type'] = 'text/plain'
                            return resposta        
            elif validador_encontrado.vezes_expulso > 2:
                resposta = make_response("Validador foi banido permamentemente do banco")
                resposta.headers['Content-type'] = 'text/plain'
                return resposta
            #se estiver tudo ok, ele cadastra na fila de espera
            Fila_de_espera.append(validador_encontrado)
            resposta = make_response(validador_encontrado.token+" "+validador_encontrado.id)
            resposta.headers['Content-type'] = 'text/plain'
            return resposta
        else:
            resposta = make_response("Validador não existe no banco de dados do seletor")
            resposta.headers['Content-type'] = 'text/plain'
            return resposta
    
@app.route('/seletor/transacoes', methods=["POST"])
def transacoes():
    
    job = request.json
    job_queue.put(job)
    
    return "Recebi uma transacao"


with app.app_context():
    nome = input("Digite o seu nome para cadastrar no banco: ")
    ip = f"127.0.0.1:{5001}"
    seletor_atual = Seletor(nome=nome, ip=ip)
    cadastrar_seletor_banco(seletor_atual)
    pegarRelogioBanco()


if __name__ == "__main__":
    
    #processing_thread = threading.Thread(target=process_jobs)
    #processing_thread.daemon = True
    #processing_thread.start()
    
    app.run(host='127.0.0.1', port=5001)