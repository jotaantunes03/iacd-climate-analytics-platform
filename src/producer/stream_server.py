import socket
import time
import pandas as pd
import os
import sys
import threading  # <--- IMPORTANTE

# --- CONFIGURAÇÕES ---
HOST = '0.0.0.0'
PORT = 9999
TEMP_FILE = '/app/data/raw/global_temp.csv'
CO2_FILE = '/app/data/raw/co2_emissions.csv'
SEND_INTERVAL = 0.002
SEPARATOR = "|"
FINAL_COLUMNS = [
    'Year', 'Value', 'Area', 'Area Code (M49)', 'Element', 'Element Code', 'Unit', 'Flag',
    'Domain', 'Domain Code', 'Months', 'Months Code', 'Flag Description',
    'Item', 'Item Code', 'Source', 'Source Code'
]


def load_and_prepare_data():
    print(">>> A unificar datasets...")
    df_combined = pd.DataFrame()
    try:
        df_temp = pd.read_csv(TEMP_FILE)
        for col in FINAL_COLUMNS:
            if col not in df_temp.columns: df_temp[col] = "N/A"
    except:
        df_temp = pd.DataFrame()

    try:
        df_raw = pd.read_csv(CO2_FILE)
        id_vars = [c for c in df_raw.columns if not c.startswith('Y')]
        value_vars = [c for c in df_raw.columns if c.startswith('Y') and 'F' not in c and 'N' not in c]
        df_melted = df_raw.melt(id_vars=id_vars, value_vars=value_vars, var_name='Year_Raw', value_name='Value')
        df_melted['Year'] = df_melted['Year_Raw'].str.replace('Y', '')
        for col in FINAL_COLUMNS:
            if col not in df_melted.columns: df_melted[col] = "N/A"
        df_co2 = df_melted
    except:
        df_co2 = pd.DataFrame()

    if not df_temp.empty and not df_co2.empty:
        df_combined = pd.concat([df_temp, df_co2], ignore_index=True)
    elif not df_temp.empty:
        df_combined = df_temp
    elif not df_co2.empty:
        df_combined = df_co2

    if not df_combined.empty:
        df_combined = df_combined[FINAL_COLUMNS]
        for col in df_combined.columns:
            df_combined[col] = df_combined[col].astype(str).str.replace('\n', ' ').str.replace('|', '')
        df_combined = df_combined.sort_values(by='Year')

    print(f">>> DATASET CARREGADO: {len(df_combined)} linhas.")
    return df_combined


# Função que corre em paralelo para cada cliente
def handle_client(conn, addr, df):
    print(f"🟢 [Thread] Iniciando envio para {addr}")
    try:
        while True:  # Loop infinito de dados
            for _, row in df.iterrows():
                msg = SEPARATOR.join(row.values) + "\n"
                try:
                    conn.sendall(msg.encode('utf-8'))
                    time.sleep(SEND_INTERVAL)
                except (BrokenPipeError, ConnectionResetError):
                    print(f"🔴 Cliente {addr} desconectou.")
                    return  # Mata a thread se o cliente sair
    except Exception as e:
        print(f"⚠️ Erro na thread {addr}: {e}")
    finally:
        conn.close()


def start_server():
    print(f"--- SERVIDOR MULTI-THREAD ---")
    df = load_and_prepare_data()
    if df.empty: sys.exit(1)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        print(f">>> À escuta em {HOST}:{PORT}")
    except Exception as e:
        sys.exit(1)

    while True:
        try:
            # O servidor aceita a conexão e passa-a imediatamente para uma thread
            conn, addr = server_socket.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr, df))
            t.start()
        except Exception as e:
            print(f"Erro no accept: {e}")
            time.sleep(1)


if __name__ == "__main__":
    start_server()