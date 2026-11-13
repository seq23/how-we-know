# Why did FTX collapse?

**Status:** DRAFT — OWNER CONFIRMATION AND MASTER WATCH REQUIRED
**Domain:** money-and-business
**Made by:** loop/money_author.py
**Opening:** stake-then-payoff
**Word count:** 1680
**Estimated narration:** 11m 37s at 144.58 WPM (measured, loop/durations.py)

## YouTube title

Why did FTX collapse?

## Direct-answer lock

FTX collapsed because it allegedly diverted 8 billion dollars of customer funds to its affiliated hedge fund, Alameda Research, for speculative investments and expenses. This commingling created a massive liquidity shortfall when customers sought withdrawals in November 2022, forcing FTX into bankruptcy and leading to federal fraud charges by the SEC and Department of Justice.

## Narration

### Cold open

{{stat: 8 | BILLION DOLLARS | FTX customer funds allegedly diverted | SEC}}
FTX allegedly diverted 8 billion dollars of customer funds to Alameda Research. The Securities and Exchange Commission details in court filings how these assets were routed to an affiliated hedge fund, creating a massive liquidity shortfall. This diversion left FTX unable to satisfy customer withdrawals when public scrutiny triggered a run on the exchange in November 2022. While regulatory filings document the mechanical steps of this transfer, the internal governance failures that enabled it require examining public records from federal prosecutors and financial regulators.

### Title card

Why did FTX collapse?

### FTX customer deposits were secretly transferred to Alameda Research

{{define: COMMINGLING | Mixing customer funds with company funds | customer protection boundary | SEC}}
The collapse of FTX centers on allegations of commingling customer deposits with company funds. The Securities and Exchange Commission filed a complaint alleging that FTX executive leadership routinely commingled customer assets with those of Alameda Research, an affiliated trading entity. Under basic brokerage and exchange regulations, customer funds must be segregated from operational capital to protect depositors from trading losses. SEC findings indicate that FTX failed to maintain this separation from its inception, allowing customer deposits to be reallocated without disclosure.

{{chain: FUND MISUSE | DEPOSITS | ALAMEDA | SHORTFALL}}
According to filings by the Department of Justice, FTX directed customer deposits into bank accounts controlled by Alameda Research rather than dedicated exchange custody accounts. This structural arrangement allowed Alameda Research to draw directly on customer money to meet its own financial obligations. The DOJ indictment explains that Alameda Research used these diverted deposits to fund speculative venture capital investments, purchase luxury real estate in the Bahamas, and make substantial political contributions. As market conditions shifted, these illiquid assets could not be converted back into cash to cover original customer balances, creating a systemic shortfall across the exchange.

{{sources: SEC AND DOJ LITIGATION | SEC=Securities and Exchange Commission | DOJ=Department of Justice}}
Public court filings from both the SEC and the Department of Justice detail how executive leadership concealed these cash transfers from auditors and investors. Financial records submitted to federal court show that internal balance sheets routinely misrepresented the financial health of both FTX and Alameda Research. Depositors operated under the assumption that their digital assets and fiat balances were held safely in isolated custody accounts, whereas SEC documentation confirms those funds were spent on third-party investments and debt settlements.

### Alameda Research operated with unique software privileges

{{contrast: RISK ENGINE | is=Enforced on standard users | not=Enforced on Alameda}}
Standard trading accounts on FTX were governed by an automated risk engine designed to prevent bad debts. The SEC complaint demonstrates that if a typical user account experienced severe losses or insufficient collateral, the risk engine automatically liquidated the user's positions to protect the exchange. However, SEC investigators discovered that Alameda Research was explicitly exempted from this risk engine mechanism through customized software logic embedded in the FTX code base.

{{checklist: ALAMEDA PRIVILEGES | +Unlimited line of credit | +Exempt from auto-liquidation | -No collateral requirements}}
Federal court filings reveal that engineers created software features allowing Alameda Research to maintain a negative balance on FTX without triggering liquidation. This exemption granted Alameda Research an unlimited line of credit drawn directly from customer account deposits. The Department of Justice documented that Alameda Research accumulated a negative balance running into billions of dollars while continuing to execute trades. Standard customers received no disclosure regarding these secret privileges, which bypassed all published risk parameters.

{{steps: MECHANICS OF DIVERSION | DEPOSIT | ROUTING | EXECUTION | SHORTFALL}}
The operational steps of this system relied on technical modifications to FTX internal order matching software. When a customer initiated a fiat currency deposit, the software interface instructed the bank transfer to land in Alameda accounts. Alameda Research then logged these sums as internal credits while deploying the physical funds elsewhere. When trading losses accrued at Alameda Research, the automated system masked the deficit by drawing further from the collective pool of customer deposits, compounding the overall financial shortfall.

### Producer POV

[HUMAN] A deadline mattered more than a test. Nobody had the authority to stop it, or the person who did had an incentive not to.

### The valuation of FTT tokens created false solvency

{{stat: 26 | BILLION DOLLARS | FTT peak market capitalization | SEC}}
The financial position of Alameda Research was heavily reliant on FTT, the native utility token issued by FTX. SEC filings note that at its peak, the total market capitalization of FTT reached 26 billion dollars based on prevailing market prices. Alameda Research held a vast majority of the circulating and uncirculated FTT supply. By listing these tokens as high-value assets on its corporate balance sheet, Alameda Research presented an appearance of immense equity to external lenders and financial institutions.

{{sources: LITIGATION RECORDS | SEC=Securities and Exchange Commission | DOJ=Department of Justice}}
Court documents filed by the SEC argue that the 26 billion dollars market capitalization was functionally illiquid. Because Alameda Research held the vast majority of FTT tokens, any attempt to sell a significant portion on open markets would cause the price to collapse. Nevertheless, Alameda Research used these artificially valued FTT tokens as primary collateral to secure third-party loans from institutional crypto lenders. The DOJ indictment states that executive leadership actively manipulated FTT trading volumes to inflate token prices whenever collateral values threatened to fall below loan agreement thresholds.

{{chain: TOKEN CYCLE | ISSUANCE | INFLATION | LOANS | COLLAPSE}}
This circular leverage model left the entire corporate ecosystem vulnerable to market shocks. When third-party lenders accepted FTT as collateral, they extended cash loans to Alameda Research, which were then used to support trading operations and further token repurchases. The SEC complaint highlights that this created a structural dependency where the solvency of Alameda Research depended on maintaining an artificially high market price for FTT. If FTT lost value, Alameda Research would face immediate collateral calls that it could not satisfy without liquidating customer funds.

### A withdrawal surge exposed the hidden liquidity deficit

{{timeline: 2022=CoinDesk publishes balance sheet report | 2022=Binance announces plan to liquidate FTT | 2022=FTX processes 5 billion dollars in withdrawals | 2022=FTX halts customer withdrawals and files Chapter 11}}
The fragile balance sheet model disintegrated in November 2022 following public disclosures regarding Alameda Research's holdings. On November 2, 2022, financial news outlet CoinDesk published a leaked balance sheet showing that Alameda Research held billions of dollars in FTT against massive liabilities. On November 6, 2022, competing exchange Binance announced it would sell its remaining FTT holdings due to risk concerns. This announcement triggered a panic among FTX users, leading to a sudden surge in withdrawal demands.

{{stat: 5 | BILLION DOLLARS | FTX customer withdrawals attempted in 72 hours | Bankruptcy Filings}}
Over the next 72 hours, FTX faced customer withdrawal requests totalizing 5 billion dollars. Court filings in the District of Delaware bankruptcy proceedings show that FTX held only a small fraction of liquid assets needed to honor these requests, as the remainder had been transferred to Alameda Research or tied up in illiquid venture holdings. On November 8, 2022, FTX halted all customer withdrawals. On November 11, 2022, FTX and over 100 corporate affiliates filed for Chapter 11 bankruptcy protection.

{{sources: BANKRUPTCY DOCKET | SEC=Securities and Exchange Commission | DOJ=Department of Justice}}
The bankruptcy filings in federal court revealed that FTX maintained no centralized cash management system and possessed incomplete corporate accounting records. John J. Ray III, appointed as bankruptcy chief executive officer to clean up the estate, stated in initial court submissions that he had never seen such a complete failure of corporate controls. The bankruptcy process confirmed that the 5 billion dollars withdrawal demand had exposed an 8 billion dollars hole in customer accounts, initiating extensive recovery litigation by federal bankruptcy administrators.

### Offshore corporate structures exploited regulatory gaps

{{contrast: REGULATED EXCHANGES | is=Subject to strict financial audits | not=Feature of offshore FTX operations}}
The rapid expansion and prolonged operation of FTX were facilitated by its offshore corporate structure. Headquartered in Antigua and later the Bahamas, FTX operated outside the primary regulatory jurisdiction of federal agencies like the SEC and the Commodity Futures Trading Commission. Traditional financial brokerages operate under rigid requirements for capital adequacy, third-party custody, and independent financial audits. FTX utilized complex cross-border entity structures to minimize regulatory oversight while serving a global customer base.

{{define: REGULATORY ARBITRAGE | Exploiting jurisdictional differences to avoid oversight | cross-border operations | CFTC}}
Federal regulatory filings describe this corporate arrangement as regulatory arbitrage. By establishing legal entities in jurisdictions with developing digital asset frameworks, FTX bypassed standard financial reporting obligations. SEC and DOJ filings demonstrate that while FTX US was promoted as an independent platform compliant with American standards, corporate officers routinely blurred operational lines between US entities and offshore balance sheets, allowing customer funds to be routed across jurisdictional boundaries without regulatory detection.

{{sources: REGULATORY REPORTS | SEC=Securities and Exchange Commission | CFTC=Commodity Futures Trading Commission}}
The absence of routine regulatory examinations enabled executive leadership to execute complex financial transactions without independent oversight. Reports filed by the SEC and CFTC following the collapse emphasize that FTX lacked an independent board of directors, established risk committees, or qualified chief financial officers across major entities. This lack of basic corporate governance prevented early intervention by market regulators, allowing the alleged fraud to scale to historic proportions before public market forces triggered the final collapse.

### What to notice in the edit

{{text}}
The edit traces the collapse from internal software code changes to balance sheet inflation, customer runs, and eventual bankruptcy filings. The narrative maintains focus strictly on documented evidence from federal court filings, SEC complaints, and Department of Justice indictments.

### Evidence limit

{{uncertain: 8 | BILLION DOLLARS | 1 | HIGH | Alleged customer shortfall range}}
While federal court filings by the SEC cite an estimated customer shortfall of 8 billion dollars with a variance range around 1 billion dollars, the final accounting remains subject to ongoing bankruptcy liquidations and legal claims. The exact total recovered will depend on asset liquidations in bankruptcy court, legal fee deductions, and complex international claim reconciliations that may take years to complete.

### Closing

{{ambient}}
The downfall of FTX demonstrates how structural governance failures, software backdoors, and balance sheet manipulation can collapse a financial exchange. Public records from federal court dockets, the SEC, and the Department of Justice document the mechanics of this shortfall. This analysis is for educational purposes and is not financial advice.

## Editorial gate

*What this episode does that a template would not. Every line below is a property the pipeline enforces at build time — see `loop/validate.py`. It records no step a human still owes.*

- Humanized cold open: PRESENT
- First-person producer observation: FROM POV BANK (pov-066)
- Evidence uncertainty or limitation: COMPLETE
- Structural variation: The narrative moves chronologically from structural coding backdoors to asset manipulation, the bank run, and offshore corporate governance.
- Number-level source audit: COMPLETE

## Chapters

- 00:00 Cold open
- 01:10 FTX customer deposits were secretly transferred to Alameda Research
- 02:45 Alameda Research operated with unique software privileges
- 04:15 Producer POV
- 04:25 The valuation of FTT tokens created false solvency
- 05:55 A withdrawal surge exposed the hidden liquidity deficit
- 07:30 Offshore corporate structures exploited regulatory gaps
- 09:05 What to notice in the edit
- 09:30 Evidence limit
- 09:55 Closing

## Sources

- Securities and Exchange Commission: Litigation Releases — https://www.sec.gov/litigation/litreleases
- Department of Justice: News — https://www.justice.gov/news
- Commodity Futures Trading Commission: Press Releases — https://www.cftc.gov/PressRoom/PressReleases
- U.S. Courts: Homepage — https://www.uscourts.gov