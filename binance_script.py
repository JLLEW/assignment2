from binance.client import Client
import pandas as pd
import datetime
import asyncio
from typing import List, Dict
import aiohttp
import os

# Initialize Binance client (public, no API key needed for this)
client = Client()

async def fetch_binance_data_per_instrument(instrument_name: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch historical klines for a given instrument name and number of days to look back.
    """
    # Fetch daily klines for the instrument
    klines = client.get_historical_klines(instrument_name, Client.KLINE_INTERVAL_1DAY, start_date, end_date)

    # Convert to DataFrame
    columns = [
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base', 'taker_buy_quote', 'ignore'
    ]
    df = pd.DataFrame(klines, columns=columns)

    # Convert timestamp to datetime and set index
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.floor("S")
    df.set_index('timestamp', inplace=True)

    # Keep only the close price, cast to float
    df = df[['close']].astype(float)
    df.rename(columns={'close': f'{instrument_name.lower()}_close'}, inplace=True)
    df.index = df.index.date
    return df

async def fetch_all_binance_data(instruments_names: list, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch historical klines for all instruments and merge them into a single DataFrame.
    """
    tasks = []
    for instrument_name in instruments_names:
        tasks.append(fetch_binance_data_per_instrument(instrument_name, start_date, end_date))

    # Gather all dataframes
    results = await asyncio.gather(*tasks)

    # Merge all dataframes on the timestamp index
    merged_df = pd.concat(results, axis=1)

    return merged_df

async def process_df(df: pd.DataFrame, instrument_name: str, mapping: Dict) -> pd.DataFrame:
    """
    Process the DataFrame to convert timestamps to datetime and set the index.
    """
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df.drop_duplicates(subset="timestamp", keep="first")
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.floor("S")
    df.set_index('timestamp', inplace=True)
    df = df[["mark_price"]]
    df["mark_price"] = df["mark_price"] * mapping[instrument_name]
    df = df.rename(columns={"mark_price": f"kc_{instrument_name}"})
    df.index = df.index.date
    return df

async def fetch_all_deribit_settlements(instrument_name: str, days_to_look_back: int, mapping: Dict, testnet: bool = False) -> pd.DataFrame:
    """
    Fetch all settlements for a given instrument name and number of days to look back.
    """
    base_url = 'https://test.deribit.com' if testnet else 'https://www.deribit.com'
    url = f"{base_url}/api/v2/public/get_last_settlements_by_instrument"
    params = {
        "instrument_name": instrument_name,
        "type": "settlement",
        "count": 1000,
    }
    async with aiohttp.ClientSession() as session:
        all_data = []
        continuation = None
        number_of_settlments_fetched = 0
        all_fetched = False
        limit = days_to_look_back
        while not all_fetched:
            if continuation:
                params["continuation"] = continuation
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    result = data.get('result', [])
                    settlements = result.get("settlements", [])
                    number_of_settlments_fetched += len(settlements)
                    all_data.extend(settlements)
                    if limit is not None and number_of_settlments_fetched >= limit:
                        print(f"All {number_of_settlments_fetched} settlements fetched from Deribit...")
                        all_fetched = True

                    remaining_to_fetch = limit - len(settlements) 
                    params["count"] = remaining_to_fetch if remaining_to_fetch < 1000 else 1000
                    continuation = result.get("continuation")
                    if continuation == "none":
                        all_fetched = True
                else:
                    print(f"Error fetching settlements for {instrument_name}: {response.status}, {response.url}")
                    return pd.DataFrame()

    return await process_df(pd.DataFrame(all_data), instrument_name, mapping)
                
def calculate_days_difference(start_date: str, end_date: str) -> int:
    # Convert strings to datetime objects
    start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    
    # Calculate the difference in days
    return (end_date - start_date).days

def filter_df(df: pd.DataFrame) -> pd.DataFrame:
    # find best price alignment
    df['row_std'] = df.std(axis=1)
    df.sort_values(by='row_std', inplace=True)

    return df.head(10)

async def main_loop(start_date: str, end_date: str, instruments_names: List[str], mapping: Dict) -> pd.DataFrame:
    """
    Main loop to fetch and process data.
    """
    days_to_look_back = calculate_days_difference(start_date, end_date)
    print(f"days to look back: {days_to_look_back}")

    # Fetch all data
    binance_task = fetch_all_binance_data(instruments_names, start_date, end_date)
    deribit_task = fetch_all_deribit_settlements("ETH-PERPETUAL", days_to_look_back, mapping)

    df_binance, df_deribit = await asyncio.gather(binance_task, deribit_task)
    
    # convert prices to king cocunt prices in USDT
    for instrument_name in instruments_names:
        if instrument_name in mapping:
            df_binance[f'kc_{instrument_name}'] = (df_binance[f'{instrument_name.lower()}_close'] * mapping[instrument_name]).round(2)
            df_binance.drop(columns=[f'{instrument_name.lower()}_close'], inplace=True)
    

    df_deribit.to_csv("data_binance/deribit_data.csv")
    df_binance.to_csv("data_binance/binance_data.csv")

    df_merged = df_deribit.join(df_binance, how='inner')

    df_merged.to_csv("data_binance/merged_data.csv")

    filtered_df = filter_df(df_merged)
    filtered_df.to_csv("data_binance/filtered_data_by_std.csv")

    return df_binance

if __name__ == "__main__":

    folder_path = 'data_binance'

    # Check if the folder exists, if not, create it
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    # Define date range (adjust as needed)
    start_date = "2020-03-07" # First day solana was listed on Binance
    end_date = "2024-12-01"  # Right before Deribit listed PAXG
    instruments = ["PAXGUSDT", "BTCUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]

    mapping = {
        "ETH-PERPETUAL": 0.0013371,
        "BTCUSDT": 0.00005181,
        "SOLUSDT": 0.020196,
        "XRPUSDT": 7.2942,
        "ADAUSDT": 7.3376,
        "PAXGUSDT": 0.0015856
    }

    asyncio.run(main_loop(start_date, end_date, instruments, mapping))