import pandas as pd
import aiohttp
import asyncio
import os

PROD_MAPPING = {
        "ETH-PERPETUAL": 0.0013371,
        "BTC-PERPETUAL": 0.00005181,
        "SOL_USDC-PERPETUAL": 0.020196,
        "XRP_USDC-PERPETUAL": 7.2942,
        "ADA_USDC-PERPETUAL": 7.3376,
    }

TESTNET_MAPPING = PROD_MAPPING.copy()
TESTNET_MAPPING["PAXG_USDC-PERPETUAL"] = 0.0015856
PROD_INSTRUMENTS = list(PROD_MAPPING.keys())
TESTNET_INSTRUMENTS = list(TESTNET_MAPPING.keys())

async def determine_how_many_days_to_look_back(session:aiohttp.ClientSession):
    """
    Knowing that PAXG was listed on Deribit on 02-12-2024
    and XRP price has not been lower than ~1.8USD since then
    transaction screenshot was taken before the date that PAXG was listed on the exchange.

    To determine how many days to look back, we have to understand when PAXG
    was first listed on testnet. It can be done by getting all possible settlments for PAXG
    from testnet. Then counting how many of those there is.
    """

    instrument_name = "PAXG_USDC-PERPETUAL"
    # since PAXG was listed in dec 2024, it was listed on testnet probalby couple of months back
    # using count = 1000 is enough for the api call
    count = 1000
    settlments = await fetch_all_settlements(session, instrument_name, count, True)
    return len(settlments)


async def process_df(df: pd.DataFrame, instrument_name: str, testnet: bool) -> pd.DataFrame:
    """
    Process the DataFrame to convert timestamps to datetime and set the index.
    """

    if testnet:
        mapping = TESTNET_MAPPING
    else:
        mapping = PROD_MAPPING
    
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df.drop_duplicates(subset="timestamp", keep="first")
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms').dt.floor("S")
    df.set_index('timestamp', inplace=True)
    df = df[["mark_price"]]
    df["mark_price"] = df["mark_price"] * mapping[instrument_name]
    df = df.rename(columns={"mark_price": f"kc_{instrument_name}"})
    return df

async def fetch_all_settlements(session:aiohttp.ClientSession, instrument_name: str, days_to_look_back: int, testnet: bool = False) -> pd.DataFrame:
    """
    Fetch all settlements for a given instrument name and number of days to look back.
    """
    base_url = 'https://test.deribit.com' if testnet else 'https://www.deribit.com'
    url = f"{base_url}/api/v2/public/get_last_settlements_by_instrument"
    params = {
        "instrument_name": instrument_name,
        "type": "settlement",
        "count": days_to_look_back,
    }

    async with session.get(url, params=params) as response:
        if response.status == 200:
            data = await response.json()
            result = data.get('result', [])
            settlements = result.get("settlements", [])
            return await process_df(pd.DataFrame(settlements), instrument_name, testnet)
        else:
            print(f"Error fetching settlements for {instrument_name}: {response.status}")
            return pd.DataFrame()

async def fetch_all_data(testnet: bool = False) -> pd.DataFrame:

    if testnet:
        instruments = TESTNET_INSTRUMENTS
    else:
        instruments = PROD_INSTRUMENTS

    async with aiohttp.ClientSession() as session:
        days_to_look_back = await determine_how_many_days_to_look_back(session)

        # Create async tasks
        tasks = []
        for instrument in instruments:
            tasks.append(fetch_all_settlements(session, instrument, days_to_look_back, testnet))

        results = await asyncio.gather(*tasks)

        # Merge all dataframes by timestamp
        merged_df = None
        for result in results:
            if not result.empty:
                if merged_df is None:
                    merged_df = result
                else:
                    merged_df = merged_df.join(result, how='inner')
            else:
                print("No data fetched for any instrument.")
                return pd.DataFrame()
        
        env = "prod" if not testnet else "testnet"
        merged_df.to_csv(f"king_coconut_data/data_{env}.csv")

        return merged_df
    
async def mask_dataframe_based_on_bounds(df: pd.DataFrame) -> pd.DataFrame:
    # Sanity check based on the price of gold since SOL was launched
    upper_bound = 5.5813
    lower_bound = 2.3784

    # Create a mask where all columns are within [min_val, max_val]
    mask = (df >= lower_bound) & (df <= upper_bound)

    # Keep only rows where all values are within the range
    df = df[mask.all(axis=1)]

    return df

def get_best_price_matching(df: pd.DataFrame) -> pd.DataFrame:
    # Gets row with the lowest standard deviation of king coconut prices
    # expressed in USDC after convertion based on the mapping
    df['row_std'] = df.std(axis=1)
    df.sort_values(by='row_std', inplace=True)

    price = df.iloc[0, :-1].mean().round(2)
    date = df.index[0]
    std = df.iloc[0]['row_std']

    return price, date, std
            
async def main():
    """
    Main function to fetch and process data.
    """

    df_prod_task = fetch_all_data(testnet=False)
    df_testnet_task = fetch_all_data(testnet=True)
    df_prod, df_testnet = await asyncio.gather(df_prod_task, df_testnet_task)

    df_prod_mask_task = mask_dataframe_based_on_bounds(df_prod)
    df_testnet_mask_task = mask_dataframe_based_on_bounds(df_testnet)
    df_prod, df_testnet = await asyncio.gather(df_prod_mask_task, df_testnet_mask_task)

    kc_price_prod, prod_date, prod_std = None, None, None
    kc_price_testnet, testnet_date, testnet_std = None, None, None
    if not df_prod.empty:
        kc_price_prod, prod_date, prod_std = get_best_price_matching(df_prod)
        print(f"King Coconut USDC price based on prod: {kc_price_prod}, {prod_date}")
    if not df_testnet.empty:
        kc_price_testnet, testnet_date, testnet_std = get_best_price_matching(df_testnet)
        print(f"King Coconut USDC price based on testnet: {kc_price_testnet}, {testnet_date}")

    if prod_std < testnet_std:
        final_price = kc_price_prod
        date = prod_date
        msg = "prod"
    else:
        final_price = kc_price_testnet
        date = testnet_date
        msg = "testnet"

    print(f"Final price of King Coconut USDC: {final_price} based on {msg} date of used settlment: {date}")


if __name__ == "__main__":
    folder_path = 'king_coconut_data'
    # Check if the folder exists, if not, create it
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    print("Fetching data...")   
    asyncio.run(main())
