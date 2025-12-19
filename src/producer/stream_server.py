"""
This module implements a multithreaded TCP server that streams climate data.

It loads and merges global temperature and CO2 emissions data from CSV files,
then listens for client connections on a specified port. For each client, it
spawns a dedicated thread to continuously stream the unified dataset, one
record at a time.
"""

import socket
import time
import pandas as pd
import os
import sys
import threading  # <-- IMPORTANT for handling multiple clients

# --- SETTINGS ---
HOST = '0.0.0.0'
PORT = 9999
TEMPERATURE_DATA_FILE = '/app/data/raw/global_temp.csv'
CO2_DATA_FILE = '/app/data/raw/co2_emissions.csv'
SEND_INTERVAL_SECONDS = 0.001
FIELD_SEPARATOR = "|"
FINAL_COLUMN_ORDER = [
    'Year', 'Value', 'Area', 'Area Code (M49)', 'Element', 'Element Code', 'Unit', 'Flag',
    'Domain', 'Domain Code', 'Months', 'Months Code', 'Flag Description',
    'Item', 'Item Code', 'Source', 'Source Code'
]


def load_and_prepare_data() -> pd.DataFrame:
    """
    Loads, cleans, and merges temperature and CO2 datasets.

    This function reads two separate CSV files for temperature and CO2 data,
    standardizes their columns, and merges them into a single DataFrame. The CO2
    data is unpivoted from a wide to a long format. The final DataFrame is
    sorted by year.

    Returns:
        pd.DataFrame: A unified DataFrame containing both temperature and CO2
                      data, or an empty DataFrame if loading fails.
    """
    print(">>> Unifying datasets...")
    combined_df = pd.DataFrame()

    # Load and standardize temperature data
    try:
        temp_df = pd.read_csv(TEMPERATURE_DATA_FILE)
        for col in FINAL_COLUMN_ORDER:
            if col not in temp_df.columns:
                temp_df[col] = "N/A"
    except Exception as e:
        print(f"⚠️ Error loading TEMPERATURE_DATA_FILE ({TEMPERATURE_DATA_FILE}): {e}")
        temp_df = pd.DataFrame()

    # Load, unpivot, and standardize CO2 data
    try:
        raw_co2_df = pd.read_csv(CO2_DATA_FILE)
        id_vars = [c for c in raw_co2_df.columns if not c.startswith('Y')]
        value_vars = [c for c in raw_co2_df.columns if c.startswith('Y') and 'F' not in c and 'N' not in c]
        
        melted_co2_df = raw_co2_df.melt(id_vars=id_vars, value_vars=value_vars, var_name='Year_Raw', value_name='Value')
        melted_co2_df['Year'] = melted_co2_df['Year_Raw'].str.replace('Y', '')
        
        for col in FINAL_COLUMN_ORDER:
            if col not in melted_co2_df.columns:
                melted_co2_df[col] = "N/A"
        co2_df = melted_co2_df
    except Exception as e:
        print(f"⚠️ Error loading CO2_DATA_FILE ({CO2_DATA_FILE}): {e}")
        co2_df = pd.DataFrame()

    # Combine datasets
    if not temp_df.empty and not co2_df.empty:
        combined_df = pd.concat([temp_df, co2_df], ignore_index=True)
    elif not temp_df.empty:
        combined_df = temp_df
    elif not co2_df.empty:
        combined_df = co2_df

    # Final cleaning and sorting
    if not combined_df.empty:
        combined_df = combined_df[FINAL_COLUMN_ORDER]
        for col in combined_df.columns:
            combined_df[col] = combined_df[col].astype(str).str.replace('\n', ' ').str.replace('|', '')
        combined_df = combined_df.sort_values(by='Year')

    print(f">>> DATASET LOADED: {len(combined_df)} rows.")
    return combined_df


def handle_client_connection(connection: socket.socket, address: tuple, data_df: pd.DataFrame):
    """
    Handles a single client connection, streaming data in a dedicated thread.

    This function continuously iterates through the provided DataFrame and sends
    each row to the client, formatted as a pipe-separated string. It runs in
    an infinite loop until the client disconnects.

    Args:
        connection (socket.socket): The client socket object.
        address (tuple): The client's address (host, port).
        data_df (pd.DataFrame): The DataFrame to stream.
    """
    print(f"🟢 [Thread] Starting data stream for {address}")
    try:
        while True:  # Infinite data loop to continuously stream
            for _, row in data_df.iterrows():
                message = FIELD_SEPARATOR.join(row.values) + "\n"
                try:
                    connection.sendall(message.encode('utf-8'))
                    time.sleep(SEND_INTERVAL_SECONDS)
                except (BrokenPipeError, ConnectionResetError):
                    print(f"🔴 Client {address} disconnected.")
                    return  # Kills the thread if the client disconnects
    except Exception as e:
        print(f"⚠️ Error in thread for {address}: {e}")
    finally:
        connection.close()


def start_server():
    """
    Initializes and starts the multi-threaded TCP server.

    This function prepares the data, sets up the server socket, and enters an
    infinite loop to accept new client connections. Each new connection is
    handed off to a new thread running the `handle_client_connection` function.
    """
    print("--- MULTI-THREADED SERVER ---")
    data_df = load_and_prepare_data()
    if data_df.empty:
        print("❌ No data loaded. Exiting.")
        sys.exit(1)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        print(f">>> Listening on {HOST}:{PORT}")
    except Exception as e:
        print(f"❌ Server could not bind to port {PORT}. Error: {e}")
        sys.exit(1)

    while True:
        try:
            # The server accepts the connection and immediately passes it to a thread
            connection, address = server_socket.accept()
            client_thread = threading.Thread(
                target=handle_client_connection,
                args=(connection, address, data_df)
            )
            client_thread.start()
        except Exception as e:
            print(f"Error on accept: {e}")
            time.sleep(1)


if __name__ == "__main__":
    start_server()