import socket
from flask import Flask,jsonify,request
from datetime import time,datetime,timedelta
import requests as rq

app = Flask(__name__)
PORTA = 5002
RELOGIO_SISTEMA = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')


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
    while True:
        id = input("Digite o seu id, caso contrario não digite nada: ")
        saldo = float(input("Digite um saldo para depositar: "))
        ip = f"127.0.0.1:{PORTA}"
        response = rq.post("http://127.0.0.1:5001/seletor/cadastrarValidador", json={'id': id, 'saldo': saldo, 'ip': ip})
        
        if response.text == 'Saldo insuficiente':
            print("Você digitou um saldo insuficiente.")
        else:
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



if __name__ == "__main__":
    
    app.run(host='127.0.0.1', port=PORTA)