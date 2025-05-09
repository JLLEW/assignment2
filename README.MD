### How to run?

Create and activate virtual environment
```
python -m venv venv
source venv/bin/activate
```
install packages
```
pip install -r requirements.txt
```
if you do not plan to run binance_script.py, there is no need to install python-binance
```
pip install pandas aiohttp
```
run main script
```
python king_coconut.py
```

Binance script is only included to represent my thinking process (explained in next section)

run binance script
```
python binance_script.py
```

### Thinking process and encountered challenges

1. I started with identification of tokens  
   1. eth 0.0013371  
   2. btc 0.00005181  
   3. paxg 0.0015856  
   4. sol 0.020196  
   5. xrp 7.2942  
   6. ada 7.3376  
2. I started narrowing down the time horizon by checking which token has the latest release date, it is Solana that was launched in 2020\.  
3. Initial idea was to pull all settlement prices for all of those coins since solana was first offered on Deribit (Check when all of those coins were first listed on Deribit). Then to compute price ratios and browse through the history to find a moment where it matches.  
4. Second idea was to get the most volatile asset (SOL) and least volatile asset (PAXG) to check based on their ratios.  
5. It led to an idea of using least volatile assets (PAXG) to come up with the lower and upper bound. PAXG low since 2020 \= \~1500 USD, high \= 3520$. It gives us lower bound for king coconut **lower\_bound** \= 1500 \* 0.0015856 \= **2.3784 USD** and **upper\_bound** \= 3520 \* 0.0015856 \= **5.5813 USD**  
6. Based on those assumptions I could filter our data periods quickly to see per coin when a given coin amount was within this range.  
7. I checked which pairs are available for tokens (from the screenshot) at deribit:  
   1. ETH/USDC  
   2. BTC/USDC  
   3. PAXG/USDC  
   4. SOL/USDC  
   5. XRP/USDC  
   6. No spot for cardano only ADA\_USDC-PERPETUAL  
8. This led to a conclusion that if we need last day settlements then perpetuals have to be used.  
9. From the **2nd of December 2024** Deribit users can: Deposit PAXG into their Deribit account. **Not much data for PAXG**  
10. **Main challenge:** I pulled settlement data for all of those perpetuals up to a point when PAXG was listed on deribit and calculated the king coconut per settlement date per instrument based on those settlement prices . I noticed a big mispricing especially between XRP priced king coconut and other currencies. Since PAXG was listed, XRP has never fallen below \~1.8USD, so it breaches lower and upper bound assumptions. It made me think in 2 different ways:  
    1. Store that offers king coconuts accepts alternative payments but puts huge premium on highly volatile assets (eg. We accept payment in ripple but it will cost you) and I should price king coconut excluding those assets \-\> only focus on ETH, PAXG (since its gold backed) and BTC \-\> find best alignment based on Deribit (prod/test) \-\> based on the best price alignments decide where prod or test was used.  
    2. Only ETH price was calculated using Deribit last day settlement. To keep prices in different currencies somehow aligned it had to happen before PAXG was listed on Deribit. Example scenario: Store owner decided to sell king coconut for 5$, used Deribit ETH last settlement price to price it in ETH, used ETH price to price in different currencies based on the ETH/Currency pairs from a different exchange where all of those alternative assets were listed.  
11. I know that PAXG was listed on Binance in 2020, so I pulled data from Binance and used close prices of spot pairs.
12. Using Binance data made me realize that the best all price matching for that data was on 2024-11-10, I eventually came to the main conclusion that if PAXG was listed on prod on 2024-12-02 it does not imply that it had to be listed on testnet on the same date… **It had to be listed on testnet earlier. That is the point of the testnet.**  
13. With a lot of overhead work (Binance stuff) I decided to look at the problem in two ways:  
    1. Check converted prices alignment for testnet up to the date when PAXG was available for testnet.  
    2. Check prices alignment for prod excluding testnet, I assumed if PAXG was not available on prod, it might be beneficial to calculate crypto currency prices for all instruments from prod and use PAXG price from testnet for the date with best prices alignment.  
14. I computed best alignments by calculating standard deviations of all currency prices converted to USDC and chose dates with lowest standard deviations
15. I decided to still leave binance_script in the final solution, so you could check what I did there if that is interesting to you. I did not refactor binance script, I left it as it is once I understood that I do not need it.

### Code explanation and assumptions

#### Assumptions:
1. If King Coconut was priced using prod it had to happen before PAXG was listed on prod due to XRP price, that at the point PAXG was listed was already to high to find a correct pricing allignment.
2. If King Coconut was priced using prod, then PAXG was not available and PAXG price was based on testnet
3. If assumption 2 holds then maximal look up period for prod and testnet should not be longer than days from now when PAXG was listed on testnet.
4. PAXG low since 2020 \= \~1500 USD, high \= 3520$. It gives us lower bound for king coconut **lower\_bound** \= 1500 \* 0.0015856 \= **2.3784 USD** and **upper\_bound** \= 3520 \* 0.0015856 \= **5.5813 USD**  
5. If prod solution was used then King Coconut final price prediction will not include PAXG, since PAXG ammount was estimated using testnet at the last available settlment date.

##### Summarizing my script works as follows:
1. Determine how many days ago PAXG was listed on testnet, by fetching all settlments for PAXG
2. Fetch all settlment data for all tokens from the screenshot for prod and test asynchronously up to the date PAXG was listed on testnet
3. Data processing on the dataframes, prices convestion to USDC
4. Mask data based on the lower, upper bound assumption
5. Compute std of prices per settlment date to find the best allignment
6. Sort dataframes by std, get first rows for both prod and test
7. Compare prod and test stds, choose solution with lower std

#### Solution
Final price of King Coconut USDC: 4.21 based on prod date of used settlment: 2024-11-11 08:00:00

USDC tracks USD almost perfectly, so there is no need to convert directly to USD


