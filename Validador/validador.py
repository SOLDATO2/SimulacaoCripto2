import socket
from flask import Flask,jsonify,request
from datetime import time,datetime,timedelta
import requests as rq

app = Flask(__name__)
PORTA = 5002
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
        self.qnt_transacoes_ultimo_min=1
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
            if self.qnt_transacoes_ultimo_min > 100:
                self.qnt_transacoes_ultimo_min=0
                self.restrito=True
                self.time_stamp=horario
                return self.restrito
        else:
            self.horario_inicio = horario
            self.qnt_transacoes_ultimo_min=0
        return self.restrito



dict_remetente = {}


def find_available_port(PORTA): # ACHA UMA PORTA DISPONÍVEL PARA O VALIDADOR
    port = PORTA
    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('127.0.0.1', port))
            return port
        except OSError:
            port += 1
        finally:
            sock.close() 

with app.app_context():
    PORTA = find_available_port(PORTA)
    TOKEM = ""
    while True:
        id = input("Digite o seu id, caso contrario não digite nada: ")
        saldo = float(input("Digite um saldo para depositar: "))
        ip = f"127.0.0.1:{PORTA}"
        response = rq.post("http://127.0.0.1:5001/seletor/cadastrarValidador", json={'id': id, 'saldo': saldo, 'ip': ip})
        
        if response.text == 'Saldo insuficiente':
            print("Você digitou um saldo insuficiente.")
        elif response.text == 'Validador foi banido permamentemente do banco':
            print("Você foi banido permamentemente do banco.")
        elif response.text == "Validador não existe no banco de dados do seletor":
            print("Seu id não foi encontrado no banco do seletor")
        else:
            mensagem = response.text
            split_da_mensagem = mensagem.split(sep=" ")
            TOKEM = split_da_mensagem[0]
            ID = split_da_mensagem[1]
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
    job = request.json
    remetente=job.get('remetente') # id remetente
    recebedor=job.get('recebedor') # id destinatario
    valor=job.get('valor')
    saldo=job.get('saldo')
    status=2
    horario=datetime.strptime(job.get('horario'),'%Y-%m-%d %H:%M:%S.%f')
    
    if remetente == "" or valor == "" or saldo == "" or horario == "":
        status = 0
        retornar_job = {"id_validor": ID,"token":TOKEM,"status":status}
        return jsonify(retornar_job)
    
    
    if remetente not in dict_remetente:#registra remetente caso ele nao exista no historico desse validador
        dict_remetente[remetente] = Remetente(horario)
        
    if dict_remetente[remetente].um_minuto(horario):                     #verifica se remetente pode ser removido da lista de restricao
        retornar_job = {"id_validor": ID,"token":TOKEM,"status":status}  #caso contrario retorna a job com status 2
        return jsonify(retornar_job)
        
    if dict_remetente[remetente].contCem(horario):                       #Verifica se remetente fez mais de 100 transacoes no ultimo min
        retornar_job = {"id_validor": ID,"token":TOKEM,"status":status}  #se passou de 100, retorna status 2
        return jsonify(retornar_job)
        
    if saldo >= valor*(1.015): #validar saldo + taxas
        if horario <= RELOGIO_SISTEMA:
            if HORARIO_ULTIMA_TRANSACAO == "" or HORARIO_ULTIMA_TRANSACAO < horario:
                if HORARIO_ULTIMA_TRANSACAO == "":
                    print("Não existe HORARIO_ULTIMA_TRANSACAO, portanto horario será aprovado")
                    HORARIO_ULTIMA_TRANSACAO = horario
                status=1
    
    retornar_job = {"id_validor": ID,"token":TOKEM,"status":status}
    return jsonify(retornar_job)

    

if __name__ == "__main__":
    
    app.run(host='127.0.0.1', port=PORTA)