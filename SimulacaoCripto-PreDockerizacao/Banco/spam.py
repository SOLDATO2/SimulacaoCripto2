import requests

def send_post_request():
    url = 'http://127.0.0.1:5000/transacoes/1/2/1'
    for _ in range (0,101):
        requests.post(url)


send_post_request()