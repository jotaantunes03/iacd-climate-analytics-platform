import socket
import time
import pandas as pd
import os
import sys

# Configurações
HOST = '0.0.0.0'
PORT = 9999
DATA_FILE = '/app/data/raw/global_temp.csv'
SEND_INTERVAL = 1.0  # 1 segundo entre envios (Mais lento para visualização)


def start_server():
    print(f"--- INICIANDO SERVIDOR DE STREAMING ROBUSTO ---")
    print(f"Host: {HOST} | Porta: {PORT}")

    # Configuração de Rede Segura
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
    except Exception as e:
        print(f"ERRO CRÍTICO ao abrir a porta: {e}")
        sys.exit(1)

    # Carregamento de Dados
    if os.path.exists(DATA_FILE):
        print(f"A carregar ficheiro: {DATA_FILE}...")
        try:
            # Carrega apenas colunas necessárias para poupar memória
            df = pd.read_csv(DATA_FILE, usecols=['Year', 'Value', 'Area'])
            print(f"SUCESSO: {len(df)} linhas carregadas em memória.")
        except Exception as e:
            print(f"ERRO ao ler CSV: {e}")
            sys.exit(1)
    else:
        print(f"ERRO: Ficheiro não encontrado no caminho: {DATA_FILE}")
        sys.exit(1)

    print(">>> SERVIDOR PRONTO. À espera de conexões...")

    # Loop Principal (Nunca morre)
    while True:
        try:
            conn, addr = server_socket.accept()
            print(f"\n🟢 NOVA CONEXÃO RECEBIDA DE: {addr}")

            try:
                # Loop de Envio de Dados
                while True:
                    print(f"--> A iniciar envio do dataset para {addr}...")

                    for index, row in df.iterrows():
                        # Formato CSV simples: Ano,Temperatura,País
                        msg = f"{row['Year']},{row['Value']},{row['Area']}\n"

                        conn.sendall(msg.encode('utf-8'))

                        # Delay para simular tempo real (ajustável)
                        time.sleep(SEND_INTERVAL)

                    print("--> Fim do dataset. Reiniciando o envio (Loop Infinito)...")
                    time.sleep(2)  # Pausa pequena entre loops do dataset

            except (BrokenPipeError, ConnectionResetError):
                print(f"🔴 Cliente {addr} desconectou-se.")
            except Exception as e:
                print(f"⚠️ Erro durante o envio: {e}")
            finally:
                conn.close()
                print(">>> Conexão fechada. À espera do próximo cliente...")

        except Exception as e:
            print(f"❌ Erro genérico no servidor: {e}")
            time.sleep(1)  # Espera 1s antes de recuperar de um erro grave


if __name__ == "__main__":
    start_server()