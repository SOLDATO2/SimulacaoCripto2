import os
from queue import Queue
import threading
from flask import Flask,jsonify, make_response,request
from datetime import time,datetime,timedelta
import requests as rq

app = Flask(__name__)
aviso_queue = Queue()
processing_thread = None
PORTA = os.getenv('PORTA_VALIDADOR', '5002')
nome = os.getenv('NOME_VALIDADOR', '?')

RELOGIO_SISTEMA = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
TOKEM = ""
ID = ""
HORARIO_ULTIMA_TRANSACAO = ""

class Remetente():
    qnt_transacoes_ultimo_min:int
    horario_inicio:datetime
    restrito:bool # marcar como restrito para recusar futuras transacoes
    time_stamp:datetime # horario em que ele foi adicionado a lista de restricao

    def __init__(self,horario):
        self.qnt_transacoes_ultimo_min=0
        self.horario_inicio=horario
        self.restrito =  False

    def um_minuto(self,horario):
        if self.restrito:
            if (horario - self.time_stamp).total_seconds() > 60:
                self.horario_inicio=horario
                self.restrito=False
        return self.restrito


    def contCem(self,horario):
        if (horario - self.horario_inicio).total_seconds() <= 60:
            self.qnt_transacoes_ultimo_min+=1
            print(f"QNT DE VEZES QUE REMETENTE PASSOU POR ESSE VALIDADOR ---> {self.qnt_transacoes_ultimo_min}")
            if self.qnt_transacoes_ultimo_min > 100:
                self.qnt_transacoes_ultimo_min=0
                self.restrito=True
                self.time_stamp=horario
                return self.restrito
        else:
            self.horario_inicio = horario
            self.qnt_transacoes_ultimo_min=1
        return self.restrito



dict_remetente = {}

def process_avisos():
    while True:
        aviso = aviso_queue.get()
        if aviso is None:
            break
        process_aviso(aviso)
        aviso_queue.task_done()
        
def process_aviso(aviso):
    global TOKEM
    global ID
    global nome
    global PORTA
    if aviso.get('aviso') == "Voce foi expulso por ma conduta.":
        while True:
            print("Você foi expulso por ter muitas flags")
            
            id = input("Digite o seu id, caso contrario não digite nada: ")
            saldo = float(input("Digite um saldo para depositar: "))
            ip = f"{nome}:{PORTA}"

            #####
            conectado = False
            tentativas = 0
            while True:
                try:
                    response = rq.post("http://seletor_container:5001/seletor/cadastrarValidador", json={'id': id, 'saldo': saldo, 'ip': ip})
                    
                    if response.text == 'Saldo insuficiente':
                        print("Você digitou um saldo insuficiente.")
                    elif response.text == 'Validador foi banido permamentemente do banco':
                        print("Você foi banido permamentemente do banco.")
                    elif response.text == "Validador nao existe no banco de dados do seletor":
                        print("Seu id não foi encontrado no banco do seletor")
                    elif response.text == "Validador ja esta na Fila":
                        print("Validador ja esta na Fila")
                    else:
                        mensagem = response.text
                        split_da_mensagem = mensagem.split(sep=" ")
                        TOKEM = split_da_mensagem[0]
                        ID = split_da_mensagem[1]
                        print("TOKEN RECEBIDO - >", TOKEM)
                        print("ID RECEBIDO - >", ID)
                        conectado = True
                    break
                except:
                    tentativas+=1
                    print(f"Não foi possivel enviar dados para o seletor. Timeout em Timeout em {tentativas}/3")
                    if tentativas >= 3:
                        break
            if conectado == True:
                break
    

with app.app_context():

    TOKEM = ""
    while True:
        id = input("Digite o seu id, caso contrario não digite nada: ")
        saldo = float(input("Digite um saldo para depositar: "))
        ip = f"{nome}:{PORTA}"

        #####
        conectado = False
        tentativas = 0
        while True:
            try:
                response = rq.post("http://seletor_container:5001/seletor/cadastrarValidador", json={'id': id, 'saldo': saldo, 'ip': ip})
                
                if response.text == 'Saldo insuficiente':
                    print("Você digitou um saldo insuficiente.")
                elif response.text == 'Validador foi banido permamentemente do banco':
                    print("Você foi banido permamentemente do banco.")
                elif response.text == "Validador nao existe no banco de dados do seletor":
                    print("Seu id não foi encontrado no banco do seletor")
                elif response.text == "Validador ja esta na Fila":
                    print("Validador ja esta na Fila")
                else:
                    mensagem = response.text
                    split_da_mensagem = mensagem.split(sep=" ")
                    TOKEM = split_da_mensagem[0]
                    ID = split_da_mensagem[1]
                    print("TOKEN RECEBIDO - >", TOKEM)
                    print("ID RECEBIDO - >", ID)
                    conectado = True
                break
            except:
                tentativas+=1
                print(f"Não foi possivel enviar dados para o seletor. Timeout em Timeout em {tentativas}/3")
                if tentativas >= 3:
                    break
        if conectado == True:
            break
    
@app.route('/validador/receberRelogio', methods=["POST"])
def receberRelogio():
    global RELOGIO_SISTEMA
    response = request.json
    RELOGIO_SISTEMA = datetime.strptime(response.get('relogio'), '%Y-%m-%d %H:%M:%S.%f')
    
    return "Done"

@app.route('/validador/receberAtraso', methods=["POST"])
def receberAtraso():
    global RELOGIO_SISTEMA
    response = request.json
    atraso = response.get('atraso')
    
    #relogio_sistema_dt = datetime.strptime(RELOGIO_SISTEMA, '%Y-%m-%d %H:%M:%S.%f')
    #relogio_sistema_dt += timedelta(seconds=atraso)
    #RELOGIO_SISTEMA = relogio_sistema_dt.strftime('%Y-%m-%d %H:%M:%S.%f')
    
    RELOGIO_SISTEMA = RELOGIO_SISTEMA + timedelta(seconds=atraso)
    print("RELOGIO ATUAL + ATRASO - > ", RELOGIO_SISTEMA)
    #RELOGIO ATUAL + ATRASO - >  2024-06-11 00:19:46.419236

    return "Done"

@app.route('/validador/validarJob', methods=["POST"])
def validarJob():
    global HORARIO_ULTIMA_TRANSACAO, ID, TOKEM, RELOGIO_SISTEMA
    job = request.json
    remetente=job.get('remetente') # id remetente
    recebedor=job.get('recebedor') # id destinatario
    valor=job.get('valor')
    saldo=job.get('saldo')
    HORARIO_ULTIMA_TRANSACAO = job.get('horario_ultima_transacao')
    if HORARIO_ULTIMA_TRANSACAO != "":
        HORARIO_ULTIMA_TRANSACAO = datetime.strptime(HORARIO_ULTIMA_TRANSACAO,'%Y-%m-%d %H:%M:%S.%f')
    status=2
    split_horario = job.get('horario').split(sep='T')
    horario = split_horario[0]+" "+split_horario[1]
    horario=datetime.strptime(horario,'%Y-%m-%d %H:%M:%S.%f')
    
    if remetente == "" or valor == "" or saldo == "" or horario == "":
        status = 0
        print("Algum parametro está incompleto, retornando status 0")
        retornar_job = {"id_validador": ID,"token":TOKEM,"status":status}
        print(f"STATUS TRANSACAO ---> {status}")
        return jsonify(retornar_job)
    
    
    if remetente not in dict_remetente:#registra remetente caso ele nao exista no historico desse validador
        dict_remetente[remetente] = Remetente(horario)
        
    if dict_remetente[remetente].um_minuto(horario):                     #verifica se remetente pode ser removido da lista de restricao
        print("REMETENTE AINDA ESTÁ RESTRITO")
        retornar_job = {"id_validador": ID,"token":TOKEM,"status":status}  #caso contrario retorna a job com status 2
        print(f"STATUS TRANSACAO ---> {status}")
        return jsonify(retornar_job)
        
    if dict_remetente[remetente].contCem(horario):                       #Verifica se remetente fez mais de 100 transacoes no ultimo min
        print("REMETENTE FOI ADICIONADO A LISTA DE RESTRICAO POR 1 MIN")
        retornar_job = {"id_validador": ID,"token":TOKEM,"status":status}  #se passou de 100, retorna status 2
        print(f"STATUS TRANSACAO ---> {status}")
        return jsonify(retornar_job)
    #verificações de regras    
    if saldo >= valor*(1.015): #validar saldo + taxas
        if horario <= RELOGIO_SISTEMA:
            if HORARIO_ULTIMA_TRANSACAO == "" or HORARIO_ULTIMA_TRANSACAO < horario:
                if HORARIO_ULTIMA_TRANSACAO == "":
                    print("Não existe HORARIO_ULTIMA_TRANSACAO, portanto horario será aprovado")
                    HORARIO_ULTIMA_TRANSACAO = horario
                status=1
            else:
                print("Não foi possivel validar horario transacao...horario transacao atual não é > HORARIO_ULTIMA_TRANSACAO")
                print(f"Horario transacao atual: {horario}")
                print(f"Horario ultima transacao atual: {HORARIO_ULTIMA_TRANSACAO}")
        else:
            print("Não foi possivel validar horario transacao...horario transacao não é <= RELOGIO_SISTEMA")
            print(f"Horario transacao atual: {horario}")
            print(f"Horario transacao atual: {RELOGIO_SISTEMA}")
    else:
        print("Não foi possivel validar saldo... saldo + taxas insuficiente")
        print(f"Saldo remetente: {saldo}")
        print(f"Valor + taxas: {valor*(1.015)}")
    
    retornar_job = {"id_validador": ID,"token":TOKEM,"status":status}
    print(retornar_job)
    print(f"STATUS TRANSACAO ---> {status}")
    return jsonify(retornar_job)

@app.route('/validador/avisos', methods=["POST"])
def avisos():
    aviso = request.json
    aviso_queue.put(aviso)
    
    return "Recebi um aviso"
    

if __name__ == "__main__":
    
    processing_thread = threading.Thread(target=process_avisos)
    processing_thread.daemon = True
    processing_thread.start()
    
    app.run(host='0.0.0.0', port=PORTA,use_reloader=False)