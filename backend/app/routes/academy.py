"""Market Academy — zero-jargon beginner course.

Every topic follows the same five-part card:
  1. simple meaning in friendly English + Hinglish,
  2. an everyday Indian analogy (dukaan, rent, insurance, token money),
  3. the formula in plain words,
  4. a 3-line worked example using round ₹100 / ₹1,000 numbers, and
  5. a quick thumb rule: when it is good vs when to be careful.

Everything here is educational arithmetic on illustrative numbers, not a
recommendation.
"""
import datetime as dt
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.models import AcademyTopic
from app.services.ai_engine.llmFailoverRouter import complete, extract_json

router = APIRouter(prefix="/academy", tags=["academy"])

ASOF = "3 Nov 2026"


def lesson(id, title, en, hi, analogy, formula, plain, example_title, lines,
           good, careful, link):
    """Build one five-part card while keeping the old wire fields intact."""
    lines = [str(x) for x in lines][:3]
    return {
        "id": id,
        "title": title,
        "one_liner": en,
        "hinglish": hi,
        "simple": {"en": en, "hi": hi},
        "analogy": analogy,
        "formula": {
            "expression": formula,
            "plain": plain,
            "variables": [],
            "note": "Use the company's own reported numbers, not a guess.",
        },
        "example": {
            "title": example_title,
            "lines": lines,
            "calculation": lines[1] if len(lines) > 1 else "",
            "result": lines[-1],
            "asof": ASOF,
        },
        "thumb_rule": {"good": list(good), "careful": list(careful)},
        "body": f"{en} {analogy}",
        "pitfall": (list(careful) or ["Numbers change; always check the date."])[0],
        "link": link,
    }


TRACKS = {
    # ------------------------------------------------------------------ 1
    "universal-fundamentals": {
        "title": "Market Basics — Start Here",
        "level": "Beginner",
        "summary": "What a share is, how a trade happens, what return and risk mean, and how much money to put in one idea.",
        "asset": "Universal",
        "lessons": [
            lesson(
                "what-is-a-share", "What is a share?",
                "A share is a small ownership piece of a real business — its cash, its shop, its profits.",
                "Share matlab company ka ek chhota hissa — uske paisa, dukaan aur munafa sab me barabar ka hissa.",
                "Think of a local tea shop split into 1,000 equal tokens. Buy 100 tokens and you own 10% of the shop, including its tea machine and its daily earnings.",
                "Your ownership % = your shares ÷ all shares × 100",
                "Apne shares ko total shares se divide karo, phir 100 se multiply karo.",
                "A ₹1,000 tea-shop example",
                ["The shop has 1,000 shares and you buy 100.",
                 "100 ÷ 1,000 × 100 = 10% ownership.",
                 "If the shop earns ₹1,000, your 10% slice is ₹100."],
                ["You want to own a real business for many years.",
                 "You understand what the company actually sells."],
                ["A low share price does not mean the company is cheap.",
                 "One small share gives you no control over the shop."],
                {"label": "Open the Reliance desk", "href": "/stocks/RELIANCE"},
            ),
            lesson(
                "order-book", "Market order vs limit order",
                "A market order buys right now at whatever price is available; a limit order waits for your price.",
                "Market order turant chalne wale rate par buy karta hai; limit order aapke rate par intezaar karta hai.",
                "In a mandi, a market order is saying “pack the mangoes, whatever today's rate”. A limit order is saying “I will pay ₹100 a kilo, call me if it comes”.",
                "Spread = lowest selling price − highest buying price",
                "Seller ka sabse kam rate minus buyer ka sabse zyada rate.",
                "Why a quiet stock costs more to trade",
                ["Buyer is ready at ₹99 and seller at ₹101.",
                 "Spread = ₹101 − ₹99 = ₹2 on a ₹100 share.",
                 "You lose about 2% the moment you buy and immediately sell."],
                ["Use a limit order when the stock trades thinly.",
                 "Check both prices before pressing buy."],
                ["A market order can fill far from the screen price.",
                 "Do not chase a fast-moving price with a market order."],
                {"label": "See an index desk", "href": "/indices/nifty-50"},
            ),
            lesson(
                "cagr", "CAGR — the honest yearly growth rate",
                "CAGR turns a multi-year journey into one steady yearly growth number.",
                "CAGR batata hai ki paisa har saal average kitne percent badha — seedha total return nahi.",
                "Your shop's rent goes up 10% every year. ₹1,000 rent becomes ₹1,100, then ₹1,210. CAGR is that 10% yearly step.",
                "CAGR = (ending value ÷ starting value) ^ (1 ÷ years) − 1",
                "End value ko start value se divide karo, power 1/years lagao, phir 1 minus karo.",
                "₹1,000 growing to ₹1,210",
                ["Start with ₹1,000 and end at ₹1,210 after 2 years.",
                 "(1,210 ÷ 1,000) ^ (1 ÷ 2) − 1 = 10%.",
                 "So the money grew about 10% every year."],
                ["You are comparing investments held for different years.",
                 "You want one clean number for a long goal."],
                ["CAGR hides the bad years in the middle.",
                 "It is not the return you actually got every year."],
                {"label": "See index returns", "href": "/indices"},
            ),
            lesson(
                "volatility", "Volatility — how bumpy the ride is",
                "Volatility measures how much the price shakes day to day. It does not say whether it will go up or down.",
                "Volatility batati hai price kitna hilta hai; yeh nahi batati ki upar jayega ya neeche.",
                "Two autos reach the same market. One takes a smooth highway, the other a bumpy village road. Same destination, very different shaking.",
                "Daily swing ≈ yearly volatility ÷ 16",
                "Saal ki volatility ko 16 se divide karo to roz ka typical swing milta hai.",
                "A ₹1,000 share with 16% yearly volatility",
                ["Yearly volatility is about 16%.",
                 "Daily swing ≈ 16 ÷ 16 = 1%, which is ₹10 on ₹1,000.",
                 "Most days move roughly ₹10 up or down, not ₹100."],
                ["You reduce position size when volatility is high.",
                 "You compare volatility with your own sleep level."],
                ["Low volatility does not mean “safe”.",
                 "A calm price can still fall slowly for years."],
                {"label": "See risk stats", "href": "/stocks/RELIANCE"},
            ),
            lesson(
                "position-sizing", "Position size — your real risk dial",
                "First decide the maximum rupee loss you can accept, then work out how many shares to buy.",
                "Pehle tay karo kitna nuksan bardasht kar sakte ho, phir quantity nikalo.",
                "Do not carry all vegetables in one leaking bag. Decide how much you can afford to drop before you pick the bag.",
                "Quantity = (money you can lose ÷ stop-loss %) ÷ share price",
                "Jo paisa loss kar sakte ho, usko stop-loss percent se divide karo, phir share price se divide karo.",
                "Sizing a ₹100 share trade",
                ["You can lose ₹1,000 and your stop-loss is 10%.",
                 "₹1,000 ÷ 10% = ₹10,000 of position size.",
                 "₹10,000 ÷ ₹100 = 100 shares."],
                ["Your maximum loss is fixed before you buy.",
                 "The stop level comes from the chart, not from hope."],
                ["A gap-down can lose more than the planned stop.",
                 "Never size a trade from “how much I can make”."],
                {"label": "Practise in the sandbox", "href": "/sandbox"},
            ),
            lesson(
                "real-return", "Real return — after inflation",
                "Real return is what your money actually buys after prices rise.",
                "Real return batata hai inflation ke baad aapki buying power kitni badhi.",
                "Your salary rose 10%, but shop prices rose 6%. Your real rise is only about 4% — the extra notes buy less than they look.",
                "Real return ≈ nominal return − inflation",
                "Jo return mila, usme se inflation minus kar do.",
                "₹1,000 in a fixed deposit",
                ["Fixed deposit pays 7% and inflation is 6%.",
                 "Real return ≈ 7% − 6% = 1%.",
                 "₹1,000 becomes ₹1,070, but it buys only about ₹1,010 of old goods."],
                ["You are planning a goal many years away.",
                 "You compare FD, gold and equity on the same footing."],
                ["Tax makes the real return even smaller.",
                 "A high headline return can still lose buying power."],
                {"label": "Learn mutual funds", "href": "/learn/mutual-funds"},
            ),
        ],
    },
    # ------------------------------------------------------------------ 2
    "equities": {
        "title": "Equities — Read a Company in Plain Words",
        "level": "Beginner",
        "summary": "The six numbers that tell you whether a business is cheap, profitable and honest with cash.",
        "asset": "Equities",
        "lessons": [
            lesson(
                "pe", "P/E — price for every ₹1 of profit",
                "P/E tells you how many rupees you pay for ₹1 of the company's yearly profit.",
                "P/E batata hai company ke ₹1 saal ke munafa ke liye aap kitne rupee de rahe ho.",
                "Buying a shop for ₹10 lakh that earns ₹1 lakh a year means 10 years to earn back the price. That is a P/E of 10.",
                "P/E = share price ÷ earnings per share (EPS)",
                "Share ka price divide karo uske per-share profit se.",
                "TCS at ₹1,000 with ₹50 EPS",
                ["Share price is ₹1,000 and yearly EPS is ₹50.",
                 "P/E = 1,000 ÷ 50 = 20.",
                 "You pay ₹20 for every ₹1 of yearly profit."],
                ["Compare P/E with other companies in the same industry.",
                 "A high P/E can be fair if profit is growing fast."],
                ["A one-time profit makes P/E look artificially low.",
                 "A high P/E needs strong future growth to justify it."],
                {"label": "Open TCS", "href": "/stocks/TCS"},
            ),
            lesson(
                "pb", "P/B — price versus net worth",
                "P/B compares the market price with the accounting net value of the company.",
                "P/B market price ko company ki accounting net worth se compare karta hai.",
                "A flat is priced at ₹1 crore, but its papers say it is worth ₹50 lakh. You are paying 2× the paper value.",
                "P/B = share price ÷ book value per share",
                "Share price divide karo book value per share se.",
                "A bank share at ₹1,000",
                ["Price is ₹1,000 and book value per share is ₹500.",
                 "P/B = 1,000 ÷ 500 = 2.",
                 "You pay ₹2 for every ₹1 of accounting net assets."],
                ["Useful for banks and asset-heavy businesses.",
                 "A low P/B can be interesting if the assets are real."],
                ["Old or unpaid loans can make book value look fake.",
                 "A cheap P/B can be cheap for a good reason."],
                {"label": "Open HDFC Bank", "href": "/stocks/HDFCBANK"},
            ),
            lesson(
                "dividend-yield", "Dividend yield — cash returned each year",
                "Dividend yield is the yearly cash dividend as a percentage of the share price.",
                "Dividend yield batata hai share price ke hisaab se saal me kitna cash dividend mila.",
                "A shop gives you ₹20 cash every year for every ₹1,000 you invested. That is a 2% cash return while you still own the shop.",
                "Dividend yield = yearly dividend per share ÷ price × 100",
                "Saal ka dividend divide karo share price se, phir 100 se multiply karo.",
                "₹20 dividend on a ₹1,000 share",
                ["Yearly dividend is ₹20 and price is ₹1,000.",
                 "₹20 ÷ ₹1,000 × 100 = 2%.",
                 "On a ₹500 price the same ₹20 would be a 4% yield."],
                ["The company earns steady cash and pays regularly.",
                 "You want some cash without selling shares."],
                ["A very high yield may mean the price has crashed.",
                 "One special dividend is not a regular income."],
                {"label": "Open ITC", "href": "/stocks/ITC"},
            ),
            lesson(
                "roe-roce", "ROE and ROCE — quality of each rupee",
                "ROE shows profit on shareholders' money; ROCE also counts borrowed money.",
                "ROE shareholder ke paise par profit batata hai; ROCE borrowed paisa bhi count karta hai.",
                "Your shop earns ₹200 on your own ₹1,000 — 20% on owner money. If you also borrowed ₹1,000, ROCE checks profit on the whole ₹2,000.",
                "ROE = net profit ÷ shareholder equity × 100",
                "Net profit ko shareholder equity se divide karo, phir 100 se multiply karo. ROCE me equity plus debt hota hai.",
                "₹100 profit on ₹1,000 equity",
                ["Net profit is ₹100 and equity is ₹1,000.",
                 "ROE = 100 ÷ 1,000 × 100 = 10%.",
                 "With ₹1,000 debt and ₹150 operating profit, ROCE = 150 ÷ 2,000 × 100 = 7.5%."],
                ["ROE above roughly 15% for many years is healthy.",
                 "High ROCE with low debt is a strong sign."],
                ["Heavy borrowing can make ROE look better than it is.",
                 "One good year is not a track record."],
                {"label": "Open Infosys", "href": "/stocks/INFY"},
            ),
            lesson(
                "dupont", "DuPont — where ROE comes from",
                "DuPont splits ROE into three levers: profit margin, sales speed and borrowing.",
                "DuPont ROE ko teen hisso me todta hai: margin, asset turnover aur leverage.",
                "A shop can earn more in three ways: keep more profit per sale, sell faster, or use more borrowed money. DuPont shows which lever is doing the work.",
                "ROE = net margin × asset turnover × leverage",
                "Margin ko asset turnover se multiply karo, phir leverage se.",
                "Three levers in one number",
                ["Margin is 10%, asset turnover is 1.5 and leverage is 2.",
                 "10% × 1.5 × 2 = 30% ROE.",
                 "Without the 2× leverage, ROE would be only 15%."],
                ["High ROE comes from margin or speed.",
                 "You can see whether borrowing is flattering the number."],
                ["High ROE only from leverage can be fragile.",
                 "Banks need a different reading of these levers."],
                {"label": "Open Bajaj Finance", "href": "/stocks/BAJFINANCE"},
            ),
            lesson(
                "cash-conversion", "Cash conversion — does profit become cash?",
                "Cash conversion checks whether reported profit actually arrives in the bank.",
                "Cash conversion batata hai ki paper profit bank me cash ban kar aaya ya nahi.",
                "A shopkeeper sells ₹1,000 of goods on udhaar. The profit looks good on paper, but the drawer is empty until customers pay.",
                "Cash conversion = operating cash flow ÷ net profit",
                "Operating cash flow ko net profit se divide karo.",
                "₹100 profit, only ₹60 collected",
                ["Net profit is ₹100 for the year.",
                 "Operating cash flow is only ₹60.",
                 "60 ÷ 100 = 0.6, so ₹40 is stuck in stock or unpaid bills."],
                ["A ratio above 1 for several years is a good sign.",
                 "You check receivables and inventory alongside it."],
                ["One bad year can be a temporary working-capital swing.",
                 "Profit without cash for years is a warning."],
                {"label": "Open Reliance", "href": "/stocks/RELIANCE"},
            ),
        ],
    },
    # ------------------------------------------------------------------ 3
    "derivatives": {
        "title": "F&O — Futures and Options Without the Fog",
        "level": "Beginner",
        "summary": "Token money, insurance and time decay: the everyday ideas behind derivatives.",
        "asset": "F&O",
        "lessons": [
            lesson(
                "futures", "Futures — a promise by both sides",
                "A futures contract locks a price today for a deal that finishes later, and both sides must complete it.",
                "Futures aaj price lock karta hai, par deal baad me hoti hai — dono parties ko nibhana padta hai.",
                "You pay token money to book a flat at ₹50 lakh today, with the final deal next month. If flat prices rise, you gain; if they fall, you still must complete.",
                "Futures price ≈ spot price + interest − dividends",
                "Spot price me interest add karo aur dividend minus karo.",
                "A one-year index future",
                ["Spot is ₹1,000, one-year interest is 10% and dividend is 2%.",
                 "Fair future ≈ 1,000 + (10% − 2%) of 1,000 = ₹1,080.",
                 "You are not paying extra; the gap is the cost of waiting."],
                ["Useful to lock a price or hedge a holding.",
                 "Small margin controls a large position."],
                ["Leverage cuts both ways and losses can exceed margin.",
                 "Futures expire; you cannot simply wait forever."],
                {"label": "Open the NIFTY desk", "href": "/indices/nifty-50"},
            ),
            lesson(
                "options", "Options — insurance, not a promise",
                "An option buyer pays a premium for the right, but not the duty, to buy or sell later.",
                "Option buyer premium dekar right kharidta hai, obligation nahi.",
                "Car insurance: you pay a small premium. If there is an accident you can claim; if not, you only lose the premium.",
                "Option buyer's maximum loss = premium paid",
                "Premium hi aapka maximum loss hai. Seller ki risk badi hoti hai.",
                "A NIFTY call option",
                ["NIFTY is at 23,000 and you buy a 23,500 call for ₹100.",
                 "At expiry NIFTY is 23,800, so the option is worth ₹300.",
                 "Profit = ₹300 − ₹100 = ₹200 per unit before costs."],
                ["A defined small loss for the buyer.",
                 "Useful as insurance around events."],
                ["Most short-dated options expire worthless.",
                 "Option sellers can lose far more than the premium."],
                {"label": "Try the F&O tab", "href": "/stocks/RELIANCE"},
            ),
            lesson(
                "pcr", "PCR — put/call open interest",
                "PCR compares how many put contracts are open against call contracts.",
                "PCR batata hai kitne put contracts khule hain compared to call contracts.",
                "At a bike showroom, if bookings for rain covers (puts) are much higher than for fancy mirrors (calls), people are cautious. PCR is that queue ratio.",
                "PCR = total put open interest ÷ total call open interest",
                "Put open interest ko call open interest se divide karo.",
                "A PCR of about 1.67",
                ["Puts open: 16,680 lots; calls open: 10,000 lots.",
                 "PCR = 16,680 ÷ 10,000 = 1.67.",
                 "More puts can mean caution — but extremes often reverse."],
                ["Use PCR with price and volatility, not alone.",
                 "Watch how it changes near expiry."],
                ["One number can mislead; expiry distorts open interest.",
                 "Heavy put writing can also mean support, not fear."],
                {"label": "Open the F&O tab", "href": "/indices/nifty-50"},
            ),
            lesson(
                "theta", "Theta — the melting ice cube",
                "Theta is the money an option loses each day simply because time is passing.",
                "Theta batata hai time nikalne se option ki value roz kitni kam hoti hai.",
                "An ice cube melts in the sun even if nobody touches it. An option's time value melts every day even if the price does not move.",
                "Theta = rupees lost per day from time passing",
                "Jitne din bache hain, utni jaldi time value girti hai.",
                "₹100 premium with 5 days left",
                ["The option has ₹100 of time value with 5 days left.",
                 "Roughly ₹20 of value melts each quiet day.",
                 "After 2 flat days only about ₹60 may remain."],
                ["Option buyers need a fast move to beat theta.",
                 "Sellers collect theta when the market stays calm."],
                ["Buying very short-dated options is a race against the clock.",
                 "Theta speeds up in the last week."],
                {"label": "Replay theta in F&O", "href": "/stocks/RELIANCE"},
            ),
            lesson(
                "delta", "Delta — the option's gear",
                "Delta tells you how much the option price moves when the underlying moves ₹1.",
                "Delta batata hai underlying ₹1 hile to option kitna hilega.",
                "A car in first gear moves a little when you press the accelerator; in third gear the same press moves it much more. Delta is that gear ratio.",
                "Delta ≈ change in option price ÷ change in underlying price",
                "Option ke price change ko underlying ke price change se divide karo.",
                "Delta 0.5 on a NIFTY call",
                ["Delta is 0.5 and NIFTY rises ₹100.",
                 "The option should rise about ₹50.",
                 "One lot of 50 units gives about ₹2,500 gain."],
                ["Useful for sizing a hedge.",
                 "Calls have positive delta; puts have negative delta."],
                ["Delta changes as the price and expiry move.",
                 "It is not a fixed gear ratio."],
                {"label": "See Greeks live", "href": "/indices/nifty-50"},
            ),
            lesson(
                "iv", "Implied volatility — the price of uncertainty",
                "Implied volatility is the size of future move that option prices are assuming.",
                "Implied volatility batati hai option price kitna bada move maan raha hai.",
                "Umbrella prices rise before monsoon even if rain may not come. When the market fears a big move, options become expensive.",
                "Higher implied volatility = more expensive options",
                "IV badhne se option premium badhta hai, chahe price same ho.",
                "Two option prices, same strike",
                ["An option costs ₹100 with 30 days left.",
                 "At 20% IV the market assumes a normal swing.",
                 "At 40% IV the same option costs much more because a big move is feared."],
                ["High IV can be an opportunity for defined-risk sellers.",
                 "Check IV before buying an event-day option."],
                ["High IV can go even higher in a panic.",
                 "Cheap IV does not guarantee a calm market."],
                {"label": "Open INDIA VIX", "href": "/indices/india-vix"},
            ),
        ],
    },
    # ------------------------------------------------------------------ 4
    "mutual-funds": {
        "title": "Mutual Funds — Invest Without the Jargon",
        "level": "Beginner",
        "summary": "NAV, direct vs regular, SIP, fees and tax — the five things that decide your actual return.",
        "asset": "Mutual Funds",
        "lessons": [
            lesson(
                "nav", "NAV — price of one unit of the basket",
                "NAV is the price of one unit of a mutual fund's pooled basket of shares and bonds.",
                "NAV mutual fund ke pooled basket ke ek unit ka price hai.",
                "A family orders one large thali and splits it into 100 equal plates. NAV is the price of one plate after adding up everything in the thali.",
                "NAV = (fund assets − liabilities) ÷ total units",
                "Fund ka total paisa minus udhaar, phir total units se divide.",
                "A ₹1,00,000 fund with 1,000 units",
                ["The fund holds ₹1,00,000 of shares and has 1,000 units.",
                 "NAV = 1,00,000 ÷ 1,000 = ₹100 per unit.",
                 "Invest ₹1,000 and you get 10 units."],
                ["You check the portfolio and expense ratio, not just NAV.",
                 "A low NAV is not automatically a bargain."],
                ["Two funds with ₹10 and ₹100 NAV can be equally good.",
                 "NAV alone tells you nothing about future returns."],
                {"label": "Open mutual funds", "href": "/mutual-funds"},
            ),
            lesson(
                "direct-regular", "Direct vs Regular — same movie, two tickets",
                "Direct and regular plans hold the same portfolio; regular pays a distributor commission.",
                "Direct aur regular plan ka portfolio same hota hai; regular me distributor commission hota hai.",
                "The same movie ticket costs more at the agent's counter than at the theatre window. The movie is identical; the extra is the commission.",
                "Extra yearly cost = regular expense ratio − direct expense ratio",
                "Regular ka expense ratio minus direct ka expense ratio.",
                "₹1,00,000 in the same fund",
                ["Regular plan charges 1.5% and direct charges 0.7%.",
                 "Extra cost = 1.5% − 0.7% = 0.8% a year.",
                 "On ₹1,00,000 that is ₹800 every year, more over time."],
                ["Direct plans suit investors who can choose funds themselves.",
                 "The gap compounds over many years."],
                ["Direct is not automatically better if you need advice.",
                 "Check the total expense ratio, not just the plan label."],
                {"label": "Compare funds", "href": "/mutual-funds"},
            ),
            lesson(
                "sip", "SIP — buying a little every month",
                "A SIP invests a fixed amount every month, so you buy more units when prices are low and fewer when high.",
                "SIP har mahine fixed paisa lagata hai, isliye sasta ho to zyada units aur mehenga ho to kam units milte hain.",
                "Instead of buying a year's groceries in one trip, you buy a little every week. You average out the price and avoid one bad day.",
                "Money invested = monthly amount × number of months",
                "Simple invested amount nikalne ke liye monthly amount ko months se multiply karo.",
                "₹1,000 every month for a year",
                ["You invest ₹1,000 a month for 12 months.",
                 "Total invested = 1,000 × 12 = ₹12,000.",
                 "At about 12% yearly growth it may be roughly ₹12,800 — market returns vary."],
                ["You have regular income and a long horizon.",
                 "It removes the stress of timing the market."],
                ["A SIP does not guarantee a profit.",
                 "Stop or switch if the fund's quality genuinely deteriorates."],
                {"label": "Run a SIP calculator", "href": "/mutual-funds"},
            ),
            lesson(
                "expense-drag", "Expense ratio — the small leak that compounds",
                "The expense ratio is the yearly fee taken from the fund; even 1% becomes large over decades.",
                "Expense ratio fund ki saalana fees hai; 1% bhi lambi avadhi me bada ho jata hai.",
                "A small leak in a water tank looks harmless, but it empties a large tank over a day. A 1% fee leaks your corpus every year.",
                "Money lost ≈ corpus × extra expense % each year",
                "Corpus ko extra expense percent se multiply karo, har saal.",
                "₹1,00,000 growing for 20 years",
                ["At 12% a year, ₹1,00,000 becomes about ₹9.6 lakh in 20 years.",
                 "At 11% after a 1% fee, it becomes about ₹8.1 lakh.",
                 "The 1% fee quietly costs about ₹1.5 lakh."],
                ["Low-cost index funds keep more of the return.",
                 "Check the expense ratio before investing."],
                ["Do not choose the cheapest fund with a bad portfolio.",
                 "A low fee does not fix poor fund management."],
                {"label": "See fund costs", "href": "/mutual-funds"},
            ),
            lesson(
                "tax", "Exit load and capital-gains tax",
                "Exit load is a fee for leaving a fund too early; capital-gains tax is tax on the profit when you sell.",
                "Exit load jaldi nikalne ki fees hai; capital-gains tax profit par lagta hai jab aap bechte ho.",
                "A building society charges a penalty if you leave before the lock-in. The government charges tax on the profit when you finally sell.",
                "Exit load = redemption amount × load %",
                "Jitna paisa nikala, usko exit-load percent se multiply karo.",
                "₹1,00,000 redeemed early",
                ["You redeem ₹1,00,000 within one year at a 1% exit load.",
                 "Exit load = ₹1,00,000 × 1% = ₹1,000.",
                 "Equity long-term gains above ₹1.25 lakh are taxed at 12.5% (current rules)."],
                ["Holding longer can avoid exit load and reduce tax.",
                 "Check the latest tax rules before selling."],
                ["Tax rules change; old articles may be wrong.",
                 "Short-term gains are taxed at a higher rate."],
                {"label": "Open the tax-aware desk", "href": "/mutual-funds"},
            ),
        ],
    },
    # ------------------------------------------------------------------ 5
    "etfs": {
        "title": "ETFs — the Index in a Tradable Wrapper",
        "level": "Beginner",
        "summary": "How an ETF stays close to its index, what it really costs, and when an index fund is simpler.",
        "asset": "ETF",
        "lessons": [
            lesson(
                "creation", "Creation and redemption — the anchor",
                "Market price can drift from the ETF's real value, but large dealers can swap the basket for units and pull it back.",
                "ETF ka market price real value se hat sakta hai, par bade dealers basket badal kar use wapas paas laate hain.",
                "A recharge coupon is worth ₹100. If someone sells it for ₹105, a dealer buys coupons and swaps them for new ones until the price returns near ₹100.",
                "Premium/discount = (ETF price − iNAV) ÷ iNAV × 100",
                "ETF price minus iNAV, divide by iNAV, multiply by 100.",
                "An ETF at ₹100 with ₹99 iNAV",
                ["ETF trades at ₹100 and the real basket value (iNAV) is ₹99.",
                 "Premium = (100 − 99) ÷ 99 × 100 ≈ 1.01%.",
                 "You are paying about 1% more than the basket is worth."],
                ["Compare the ETF price with iNAV before buying.",
                 "Creation units keep a healthy ETF close to fair value."],
                ["A thinly traded ETF can stay at a premium or discount.",
                 "Do not buy blindly at the screen price."],
                {"label": "Open ETFs", "href": "/etfs"},
            ),
            lesson(
                "ter-tracking", "TER and tracking error",
                "TER is the ETF's yearly fee; tracking error is how far its return drifts from the index.",
                "TER ETF ki saalana fees hai; tracking error batata hai return index se kitna aage-peeche gaya.",
                "A photocopy of a document is never perfect. TER is the cost of making the copy; tracking error is how blurry the copy turns out.",
                "Tracking error = typical yearly gap from the index",
                "ETF ke return aur index ke return ka typical gap.",
                "Index 12%, ETF 11.5%",
                ["The index returned 12% and the ETF returned 11.5%.",
                 "Gap = 0.5% and the TER is only 0.2%.",
                 "The extra 0.3% is tracking error and trading costs."],
                ["Low TER plus low tracking error is the real win.",
                 "Read both numbers together."],
                ["A low TER with a large tracking error is not cheap.",
                 "Small ETFs can drift more."],
                {"label": "Compare ETFs", "href": "/etfs"},
            ),
            lesson(
                "liquidity", "Liquidity — the hidden cost",
                "Liquidity is how easily you can buy or sell without moving the price.",
                "Liquidity batati hai ki bina price hilaaye aap kitni aasani se buy ya sell kar sakte ho.",
                "Selling a second-hand scooter in a small town takes longer and needs a bigger discount. A popular model sells in minutes at a fair price.",
                "Impact cost ≈ (ask − bid) ÷ mid price × 100",
                "Seller ka rate minus buyer ka rate, divide by middle price, multiply by 100.",
                "A ₹100 ETF with a ₹2 spread",
                ["Best bid is ₹99 and best ask is ₹101, mid is ₹100.",
                 "Impact cost ≈ (101 − 99) ÷ 100 × 100 = 2%.",
                 "On a ₹1,00,000 order that is about ₹2,000."],
                ["Choose ETFs with healthy daily volume.",
                 "Use limit orders for large quantities."],
                ["A big order in a small ETF can move the price.",
                 "The screen price is not the price for your full order."],
                {"label": "See ETF volumes", "href": "/etfs"},
            ),
            lesson(
                "etf-vs-indexfund", "ETF vs index fund",
                "Both track an index; an ETF trades on the exchange while an index fund is bought from the fund house.",
                "Dono index track karte hain; ETF exchange par milta hai, index fund fund house se.",
                "Loose milk from a nearby booth versus a monthly milk subscription. Same milk, but one needs you to go and buy, the other arrives automatically.",
                "Total cost = TER + brokerage + spread + tracking error",
                "Saari costs ko jodo, sirf TER nahi.",
                "₹1,00,000 invested for a year",
                ["ETF TER is 0.2% but brokerage and spread add about 0.2%.",
                 "Index fund TER is 0.5% with no brokerage.",
                 "For a small monthly SIP, the index fund can be simpler and cheaper."],
                ["ETFs suit large, long holdings and live pricing.",
                 "Index funds suit small automatic SIPs."],
                ["An ETF needs a demat account and real-time orders.",
                 "Do not ignore spread and brokerage in the comparison."],
                {"label": "Compare both desks", "href": "/etfs"},
            ),
            lesson(
                "gold-etf", "Gold ETFs — paper gold",
                "A gold ETF holds physical gold and lets you buy it like a share.",
                "Gold ETF physical gold rakhta hai aur aap use share ki tarah kharid sakte ho.",
                "Digital gold in a locker: you do not carry the coins, but the value should follow the gold market minus storage and fees.",
                "Tracking gap = gold ETF return − physical gold return",
                "Gold ETF ke return se physical gold ka return minus karo.",
                "Gold rises 10%, ETF rises 9.5%",
                ["Physical gold rose 10% over the year.",
                 "The gold ETF rose 9.5%.",
                 "Gap = 0.5%; on ₹1,00,000 that is about ₹500 of costs."],
                ["Low-cost way to add gold to a portfolio.",
                 "Easy to buy and sell on the exchange."],
                ["Premium or discount can distort the price.",
                 "Gold itself can stay flat for many years."],
                {"label": "Open gold and silver", "href": "/gold-silver"},
            ),
        ],
    },
    # ------------------------------------------------------------------ 6
    "bonds": {
        "title": "Bonds — Price, Yield and Duration",
        "level": "Beginner",
        "summary": "Why bond prices fall when interest rates rise, and how to read yield without a finance degree.",
        "asset": "Bonds",
        "lessons": [
            lesson(
                "price-yield", "Bond price and yield — the see-saw",
                "When market interest rates rise, older bond prices fall; when rates fall, bond prices rise.",
                "Jab market interest rate badhta hai, purane bond ka price girta hai; rate girne par price badhta hai.",
                "You hold a fixed-rent shop agreement at ₹10,000 a month. A new shop next door rents for ₹12,000. Nobody will pay full price for your old agreement now.",
                "Price change ≈ −duration × change in yield",
                "Duration ko yield change se multiply karo, minus lagao.",
                "Duration 5, yield rises 1%",
                ["A bond has duration 5 and its yield rises by 1%.",
                 "Price change ≈ −5 × 1% = −5%.",
                 "A ₹1,000 bond falls to about ₹950."],
                ["Locking a high yield for a long time can be useful.",
                 "Short-duration bonds shake less."],
                ["Long-duration bonds can fall hard when rates rise.",
                 "The see-saw works in both directions."],
                {"label": "Open the bond desk", "href": "/bonds"},
            ),
            lesson(
                "ytm", "YTM — the full yearly return",
                "Yield to maturity is the single yearly return you get if you hold the bond until it matures.",
                "YTM wo yearly return hai jo bond ko maturity tak hold karne par milta hai.",
                "Your shop earns monthly rent and you also sell the shop at a profit after five years. YTM combines both the rent and the final sale gain.",
                "YTM = the yearly rate that makes all future payments equal today's price",
                "Aisa rate jo saare future coupon aur final payment ko aaj ke price ke barabar kare.",
                "A ₹1,000 bond at ₹950",
                ["The bond pays a 7% coupon, or ₹70 a year, and matures in 5 years.",
                 "You buy it for ₹950, so you also gain ₹50 at maturity.",
                 "The combined YTM is roughly 8.2% a year."],
                ["Use YTM to compare bonds with different prices.",
                 "It includes both coupon and price gain."],
                ["YTM assumes you hold to maturity.",
                 "It assumes coupons are reinvested at the same rate."],
                {"label": "Try the YTM calculator", "href": "/bonds"},
            ),
            lesson(
                "duration", "Duration — the see-saw length",
                "Duration measures how sensitive a bond's price is to interest-rate changes.",
                "Duration batati hai bond ka price interest-rate change par kitna hilega.",
                "A longer see-saw moves much more at the far end for the same push. A longer-duration bond moves more for the same rate change.",
                "% price change ≈ −duration × % change in yield",
                "Duration ko yield ke percent change se multiply karo, minus lagao.",
                "Duration 7, yield rises 0.5%",
                ["A bond has duration 7 years and yield rises 0.5%.",
                 "Price change ≈ −7 × 0.5% = −3.5%.",
                 "₹1,000 becomes about ₹965."],
                ["Match duration to when you need the money.",
                 "Short duration for near-term goals."],
                ["Duration changes as time passes and rates move.",
                 "Long duration is not automatically higher return."],
                {"label": "See duration maths", "href": "/bonds"},
            ),
            lesson(
                "credit-spread", "Credit spread — the price of default risk",
                "Credit spread is the extra yield a company bond pays over a government bond.",
                "Credit spread company bond aur government bond ke yield ka extra gap hai.",
                "A loan to a small shop with weak papers needs a higher interest rate than a loan to a government office. The extra rate is the credit spread.",
                "Credit spread = company bond yield − government bond yield",
                "Company bond ka yield minus government bond ka yield.",
                "Company 9%, government 7%",
                ["The company bond yields 9% and the G-Sec yields 7%.",
                 "Credit spread = 9% − 7% = 2%.",
                 "On ₹1,000 that is ₹20 of extra yearly interest for taking risk."],
                ["A wide spread can pay well if the company is strong.",
                 "Compare the spread with its own history."],
                ["A very wide spread may signal real default risk.",
                 "Higher interest is not free money."],
                {"label": "Open corporate bonds", "href": "/bonds"},
            ),
            lesson(
                "tbill", "T-bills — buying at a discount",
                "A T-bill is a short-term government bill bought below face value and repaid at face value.",
                "T-bill sarkari short-term bill hai jo face value se kam par milta hai aur maturity par poora milta hai.",
                "You buy a ₹100 gift coupon for ₹98 today and the shop accepts it for ₹100 after three months. The ₹2 gap is your earning.",
                "T-bill price = face value ÷ (1 + yield × days ÷ 365)",
                "Face value ko 1 plus yield into days/365 se divide karo.",
                "₹100 face value, 91 days, 7%",
                ["Face value is ₹100, days are 91 and the yield is 7%.",
                 "Price ≈ 100 ÷ (1 + 0.07 × 91 ÷ 365) = ₹98.28.",
                 "You gain about ₹1.72 over 91 days."],
                ["Very safe place for short-term money.",
                 "Easy to understand and liquid."],
                ["The absolute gain is small.",
                 "Reinvesting at the same rate is not guaranteed."],
                {"label": "Open T-bills", "href": "/bonds"},
            ),
        ],
    },
    # ------------------------------------------------------------------ 7
    "commodities-reits": {
        "title": "Gold, Silver, SGBs & REITs",
        "level": "Beginner",
        "summary": "Why gold follows import parity, what the gold/silver ratio means, and how rent reaches you as a REIT unit.",
        "asset": "Commodities & Trusts",
        "lessons": [
            lesson(
                "gold-parity", "Gold price — import parity",
                "India's rupee gold price mostly follows the international price, the dollar-rupee rate and import duty.",
                "India me gold ka rupee price international price, dollar-rupee rate aur import duty se banta hai.",
                "Imported chocolate costs foreign price plus shipping plus customs. Gold works the same way: world price plus duty plus local charges.",
                "Rupee gold price ≈ world price × USD/INR + duty + local premium",
                "World price ko dollar-rupee rate se multiply karo, phir duty aur local premium add karo.",
                "A $2,000 per ounce world price",
                ["World gold is $2,000 an ounce and USD/INR is ₹85.",
                 "2,000 × 85 = ₹1,70,000 per ounce.",
                 "Add 10% import duty and the landed cost is about ₹1,87,000."],
                ["Track duty changes and the rupee before buying.",
                 "Compare 24K and 22K carefully."],
                ["Jewellery adds making charges and wastage.",
                 "Local shop premiums can be large in a festival rush."],
                {"label": "Open gold and silver", "href": "/gold-silver"},
            ),
            lesson(
                "gold-silver-ratio", "Gold/silver ratio",
                "The gold/silver ratio says how many units of silver buy one unit of gold.",
                "Gold/silver ratio batata hai ek gold ke liye kitni silver chahiye.",
                "It is like an exchange rate between two metals: how many silver coins buy one gold coin today.",
                "Gold/silver ratio = gold price ÷ silver price",
                "Gold ka price divide karo silver ke price se.",
                "Gold ₹1,00,000 and silver ₹1,000",
                ["Gold is ₹1,00,000 per 10 grams.",
                 "Silver is ₹1,000 per 10 grams.",
                 "Ratio = 1,00,000 ÷ 1,000 = 100."],
                ["Useful for comparing relative value.",
                 "A very high ratio has sometimes meant silver is cheap."],
                ["The ratio can stay extreme for years.",
                 "It is not a timing signal on its own."],
                {"label": "Live gold and silver", "href": "/gold-silver"},
            ),
            lesson(
                "sgb", "Sovereign Gold Bond — gold plus interest",
                "An SGB follows the gold price and also pays 2.5% interest every year.",
                "SGB gold price ko follow karta hai aur saal ka 2.5% interest bhi deta hai.",
                "It is like a fixed deposit made of gold: the gold value moves, and you also get a small rent on top, with no locker cost.",
                "SGB maturity = gold value at maturity + interest received",
                "Maturity par gold ka value plus saal bhar ka interest milta hai.",
                "₹1,00,000 invested at ₹5,000 per gram",
                ["You buy 20 grams at ₹5,000 per gram.",
                 "After 8 years gold is ₹8,000 per gram, so the gold value is ₹1,60,000.",
                 "You also received 2.5% interest every six months along the way."],
                ["Long-term gold exposure with extra interest.",
                 "Maturity redemption is tax-efficient for many investors."],
                ["Money is locked for 8 years.",
                 "Gold price can fall over your holding period."],
                {"label": "Open SGB details", "href": "/bonds"},
            ),
            lesson(
                "reit-yield", "REIT — rent in unit form",
                "A REIT owns income-producing property and distributes the rent to unit holders.",
                "REIT income wali property rakhta hai aur rent unit holders ko distribute karta hai.",
                "You buy a shop that pays rent every quarter, but instead of owning the shop alone you own units of a trust that owns many shops.",
                "Distribution yield = yearly distribution per unit ÷ unit price × 100",
                "Saal ka distribution per unit divide karo unit price se, phir 100 se multiply karo.",
                "A ₹100 REIT unit",
                ["The unit price is ₹100 and the trust distributes ₹7 a year.",
                 "Distribution yield = 7 ÷ 100 × 100 = 7%.",
                 "Occupancy is 90% and average lease length is 8 years."],
                ["Regular cash distribution from real estate.",
                 "You can start with a small amount."],
                ["A high yield can hide falling occupancy.",
                 "Debt refinancing at higher rates can cut distributions."],
                {"label": "Open REITs", "href": "/reits"},
            ),
            lesson(
                "invit", "InvIT — toll roads as units",
                "An InvIT owns operating infrastructure and distributes the cash it collects.",
                "InvIT chal rahi infrastructure rakhta hai aur uska cash distribute karta hai.",
                "You buy a share of a toll plaza that collects cash every day, but only for a fixed number of years before the concession ends.",
                "InvIT yield = yearly distribution per unit ÷ unit price × 100",
                "Saal ka distribution divide karo unit price se, phir 100 se multiply karo.",
                "A ₹100 InvIT unit",
                ["The unit price is ₹100 and the trust distributes ₹11 a year.",
                 "Yield = 11 ÷ 100 × 100 = 11%.",
                 "The toll-road concession ends in 15 years, so the asset is not forever."],
                ["High cash yield from real infrastructure.",
                 "Long contracts can give visible cash flow."],
                ["Part of the distribution may be capital repayment, not income.",
                 "Traffic and regulatory risk can cut cash flow."],
                {"label": "Open InvITs", "href": "/reits"},
            ),
        ],
    },
}


_GLOSSARY = [
    dict(id="pat-to-book", title="PAT to book value — profit on every rupee of net worth",
         en="PAT to book divides yearly profit by shareholders' net worth, so you see how hard the owners' money is working.",
         hi="PAT to book matlab saal ka munafa ÷ owners ka net worth — kitna kaam paisa kar raha hai.",
         analogy="You put ₹1,000 into a dukaan and it earns ₹150 a year; PAT to book is that 15%.",
         formula="PAT to book = Profit after tax ÷ Net worth × 100",
         plain="Munafa ko net worth se divide karo, phir 100 se multiply karo.",
         ex=["Net worth ₹1,000 and PAT ₹150.", "150 ÷ 1,000 × 100 = 15%.", "That is a healthy 15% PAT-to-book."],
         good=["Above 15% usually means a high-quality business.", "Compare only with the same industry."],
         careful=["A small net worth can make the ratio look huge.", "One bad year can distort it."]),
    dict(id="price-to-book-value", title="Price to book (P/B) — what you pay for net worth",
         en="P/B compares the share price with the company's book value per share.",
         hi="P/B batata hai aap net worth ke har ₹1 ke liye kitna pay kar rahe ho.",
         analogy="A shop's assets are worth ₹100 per share but the market asks ₹250; P/B is 2.5×.",
         formula="P/B = Share price ÷ Book value per share",
         plain="Price ko book value per share se divide karo.",
         ex=["Book value ₹100 per share.", "Price ₹250.", "250 ÷ 100 = 2.5× P/B."],
         good=["Below 1 can be cheap if assets are real.", "Compare with ROE: high P/B needs high ROE."],
         careful=["Old plant and machinery may be worth less than book value.", "Banks need P/B, asset-light firms do not."]),
    dict(id="enterprise-value", title="Enterprise value — the real price of the business",
         en="Enterprise value is market cap plus debt minus cash: what a buyer would really pay for the whole business.",
         hi="Enterprise value = market cap + debt − cash; poora business kharidne ka asli price.",
         analogy="You buy a shop for ₹1,000, take over its ₹300 loan and get ₹100 cash in the drawer; your real cost is ₹1,200.",
         formula="EV = Market cap + Total debt − Cash",
         plain="Market cap mein debt jodo aur cash ghatao.",
         ex=["Market cap ₹1,000, debt ₹300, cash ₹100.", "EV = 1,000 + 300 − 100.", "EV = ₹1,200."],
         good=["Use EV for debt-heavy companies.", "EV/EBITDA compares firms with different capital structures."],
         careful=["Cash locked overseas may not be usable.", "Lease liabilities can hide inside debt."]),
    dict(id="ev-ebitda", title="EV/EBITDA — valuation before financing noise",
         en="EV/EBITDA compares the whole-business price with operating profit, ignoring interest and tax.",
         hi="EV/EBITDA operating profit ke muqable business ka price batata hai.",
         analogy="Two shops earn ₹100 operating profit; one sells for ₹800, the other for ₹1,200. The first is 8×, the second 12×.",
         formula="EV/EBITDA = Enterprise value ÷ EBITDA",
         plain="Enterprise value ko EBITDA se divide karo.",
         ex=["EV ₹1,200 and EBITDA ₹150.", "1,200 ÷ 150 = 8×.", "A lower multiple is cheaper, if growth is similar."],
         good=["Useful for capital-intensive sectors.", "Works across different debt levels."],
         careful=["EBITDA ignores real cash costs like interest and capex.", "Not meaningful for banks."]),
    dict(id="ebitda-margin", title="EBITDA margin — operating profit in every ₹100 of sales",
         en="EBITDA margin shows how much operating profit remains from each ₹100 of revenue.",
         hi="EBITDA margin batata hai har ₹100 sales mein operating profit kitna bacha.",
         analogy="A dukaan sells ₹100 of goods and keeps ₹18 before rent, interest and tax; the margin is 18%.",
         formula="EBITDA margin = EBITDA ÷ Revenue × 100",
         plain="EBITDA ko revenue se divide karo aur 100 se multiply karo.",
         ex=["Revenue ₹1,000 and EBITDA ₹180.", "180 ÷ 1,000 × 100 = 18%.", "A rising margin means pricing power or cost control."],
         good=["Rising margins with flat sales can mean efficiency.", "Compare with peers, not across industries."],
         careful=["Cost cuts can lift margin while growth stalls.", "EBITDA still ignores capex and interest."]),
    dict(id="upper-circuit", title="Upper circuit — the price is locked at the top",
         en="An upper circuit is the maximum price the exchange allows for the day; buying stops because no one will sell there.",
         hi="Upper circuit din ka maximum allowed price hai; wahan koi bechna nahi chahta, isliye buy orders pending reh jaate hain.",
         analogy="A theatre sells only 100 tickets; once sold out, the queue cannot buy more at any price.",
         formula="Circuit limit = Previous close ± exchange-defined %",
         plain="Kal ke close se fixed % upar ya neeche, us se aage price nahi ja sakta.",
         ex=["Previous close ₹100 and a 5% band.", "Upper circuit = ₹105.", "If locked, your buy order may not execute."],
         good=["A lock with huge volume can signal strong demand.", "Check the circuit band before placing a market order."],
         careful=["You may buy at the peak and get trapped.", "Circuit filters change for volatile stocks."]),
    dict(id="pledged-shares", title="Pledged shares — promoter borrowings against your company",
         en="Pledging means promoters have pledged their shares as collateral for a loan.",
         hi="Pledged shares matlab promoters ne apne shares bank loan ke against girvi rakhe hain.",
         analogy="You keep your gold with a pawnbroker to borrow cash; if you cannot repay, the gold can be sold.",
         formula="Pledge % = Pledged promoter shares ÷ Total promoter shares × 100",
         plain="Girvi shares ko total promoter shares se divide karo.",
         ex=["Promoter holds 1,000 shares.", "400 are pledged.", "Pledge = 40% — a risk flag."],
         good=["Zero or very low pledge is comfortable.", "Falling pledge over time is a positive."],
         careful=["A margin call can force share sales.", "High pledge plus falling price is dangerous."]),
    dict(id="free-float", title="Free float — shares actually available to trade",
         en="Free float is the part of the company not held by promoters or locked-in investors.",
         hi="Free float woh shares hain jo promoters ke paas nahi hain aur market mein freely trade kar sakte hain.",
         analogy="A housing society has 100 flats but 70 are owner-occupied forever; only 30 can be bought.",
         formula="Free float % = (Total shares − Promoter/locked shares) ÷ Total shares × 100",
         plain="Promoter aur locked shares hatao, baaki total ka percentage.",
         ex=["Total 1,000 shares, promoters hold 700.", "Free float = 300 shares.", "That is 30% free float."],
         good=["Higher free float means easier buying and selling.", "Index inclusion often needs a minimum float."],
         careful=["Low float can make the price jump on small trades.", "Do not confuse free float with market cap."]),
    dict(id="xirr", title="XIRR — the return when cash flows are irregular",
         en="XIRR is the annual return for investments made on different dates, like SIPs or multiple purchases.",
         hi="XIRR alag-alag dates ke cash flows ka annual return batata hai, jaise SIP ya baar-baar kharidna.",
         analogy="You put ₹1,000 in January and ₹2,000 in July; a simple CAGR cannot handle that, XIRR can.",
         formula="XIRR solves: Σ cash flow ÷ (1 + r)^(days ÷ 365) = 0",
         plain="Har cash flow ko uske din ke hisaab se discount karke ek annual rate dhoondo.",
         ex=["Invest ₹1,000 today and ₹1,000 after one year.", "Value after two years is ₹2,400.", "XIRR is about 14.4%, not the simple 20%."],
         good=["Use XIRR for SIPs and staggered entries.", "It respects the timing of every rupee."],
         careful=["XIRR assumes reinvestment at the same rate.", "Short periods can show misleadingly large numbers."]),
    dict(id="rolling-return", title="Rolling return — return from every possible entry date",
         en="A rolling return checks what you would have earned if you had started on each day, then shows the range.",
         hi="Rolling return har possible entry date ka return nikaalta hai, taaki luck ka asar dikhe.",
         analogy="Instead of checking one train's delay, you check every train for a month.",
         formula="Rolling return = CAGR over a fixed window, repeated for every start date",
         plain="Same duration ke returns ko har shuruaati din se calculate karo.",
         ex=["Three-year rolling returns might range from 8% to 22%.", "The average is 14%.", "The range matters more than one number."],
         good=["Shows consistency, not one lucky period.", "Useful before choosing a fund."],
         careful=["Past ranges do not guarantee the future.", "Very short windows are noisy."]),
    dict(id="gmp", title="GMP — the grey-market premium",
         en="GMP is the unofficial premium at which unlisted IPO shares trade before listing.",
         hi="GMP woh unofficial premium hai jo IPO shares listing se pehle grey market mein le rahe hain.",
         analogy="A concert ticket with face value ₹1,000 sells for ₹1,250 outside the gate; the ₹250 is GMP.",
         formula="Estimated listing price = IPO price + GMP",
         plain="IPO price mein GMP jodo; expected listing price mil jaayega.",
         ex=["IPO price ₹100 and GMP ₹20.", "Expected listing = ₹120.", "That is a 20% implied gain."],
         good=["A rising GMP with strong subscription shows demand.", "Use it as sentiment, not valuation."],
         careful=["GMP is unregulated and can vanish on listing day.", "Never borrow to chase a GMP."]),
    dict(id="ofs", title="OFS — offer for sale",
         en="In an OFS, existing shareholders sell their shares; the company does not receive that money.",
         hi="OFS mein purane shareholders apne shares bechte hain; woh paisa company ko nahi milta.",
         analogy="The shop owner sells his own old furniture at the shop's opening; the shop's cash box stays untouched.",
         formula="Issue size = Fresh issue + OFS",
         plain="Fresh issue company ke liye, OFS sellers ke liye.",
         ex=["Issue ₹1,000 crore: ₹400 fresh and ₹600 OFS.", "Only ₹400 reaches the company.", "The rest goes to selling shareholders."],
         good=["OFS gives early investors an exit.", "Read who is selling and why."],
         careful=["100% OFS means no growth capital.", "Private-equity exits can create overhang."]),
    dict(id="drhp", title="DRHP — the draft red herring prospectus",
         en="The DRHP is the first public IPO document filed with SEBI; it explains the business, risks and use of money.",
         hi="DRHP IPO ka pehla public document hai jo SEBI ke paas jaata hai; business, risk aur paise ka use batata hai.",
         analogy="It is the shop's full inspection report before you invest in the shop.",
         formula="DRHP → RHP → final prospectus",
         plain="Pehle draft, phir revised, phir final offer document.",
         ex=["Read the risk factors first.", "Check objects of the issue.", "Check promoter and related-party transactions."],
         good=["The risk section is written by lawyers, not marketing.", "Compare DRHP promises with later RHP changes."],
         careful=["Long documents hide important related-party deals.", "Do not rely only on GMP."]),
    dict(id="lot-size", title="Lot size — the minimum IPO application",
         en="Lot size is the smallest number of shares you can apply for in an IPO.",
         hi="Lot size IPO mein sabse kam shares ki application hai.",
         analogy="A wholesaler sells only full boxes of 12 pens, not single pens.",
         formula="Minimum investment = Lot size × Upper price band",
         plain="Lot ko price se multiply karo.",
         ex=["Lot 12 shares and price ₹100.", "Minimum = ₹1,200.", "You can apply in multiples of 12."],
         good=["Know your slab before applying.", "Retail is up to ₹2 lakh."],
         careful=["Over-applying in many accounts is not allowed.", "The lot can change with the price band."]),
    dict(id="cut-off-price", title="Cut-off price — bidding without naming a price",
         en="At cut-off, you agree to pay whatever price is discovered in the book, within the band.",
         hi="Cut-off price matlab aap band ke andar jo final price nikle, woh dene ko ready ho.",
         analogy="You tell the shop, 'give me the best final price', instead of fixing your own price.",
         formula="Cut-off bid = bid at the upper end of the price band",
         plain="Price likhne ki jagah cut-off option chuno.",
         ex=["Band ₹95–₹100.", "A cut-off bid is treated as ₹100.", "You pay the discovered price, up to ₹100."],
         good=["Simplest option for retail investors.", "Useful when demand is strong."],
         careful=["You may pay the top of the band.", "A limit bid lets you control the price."]),
    dict(id="stt", title="STT — securities transaction tax",
         en="STT is a small tax charged on every buy and sell of listed shares.",
         hi="STT har listed share ke buy aur sell par lagne wala chhota tax hai.",
         analogy="A tiny toll on every trip, whether you profit or not.",
         formula="STT = Trade value × applicable rate",
         plain="Trade value par fixed rate lagta hai.",
         ex=["Buy ₹1,00,000 of shares.", "Delivery STT is 0.1% on each side.", "That is ₹100 on the buy."],
         good=["It is already built into your contract note.", "Intraday rates differ from delivery."],
         careful=["Frequent trading makes STT add up.", "STT is not your only cost; brokerage and GST apply too."]),
    dict(id="ltcg", title="LTCG — long-term capital gains tax",
         en="LTCG is tax on profit from assets held longer than the threshold; listed equity above ₹1.25 lakh a year is taxed at 12.5%.",
         hi="LTCG lambi holding ke profit par tax hai; listed equity mein saal ke ₹1.25 lakh se upar 12.5%.",
         analogy="A slow-cooked dish is taxed at a lower rate than a quick flip.",
         formula="LTCG tax = (Sale value − Cost) × 12.5%, above the exemption",
         plain="Profit nikaalo, exemption hatao, phir 12.5% lagao.",
         ex=["Bought for ₹1,00,000, sold for ₹3,00,000.", "Gain ₹2,00,000; exemption ₹1,25,000.", "Tax = 12.5% of ₹75,000 = ₹9,375."],
         good=["Hold longer than 12 months for listed equity.", "Use the annual exemption across the family."],
         careful=["The exemption is per financial year, not per trade.", "Debt and gold have different rules."]),
    dict(id="stcg", title="STCG — short-term capital gains tax",
         en="STCG is tax on profit from listed equity held for 12 months or less; the rate is 20%.",
         hi="STCG 12 mahine se kam holding ke profit par 20% tax hai.",
         analogy="A quick flip is taxed at a higher rate than a long hold.",
         formula="STCG tax = Profit × 20%",
         plain="Profit par 20% seedha tax.",
         ex=["Buy at ₹1,000 and sell at ₹1,200.", "Profit ₹200.", "STCG tax = ₹40."],
         good=["Harvest losses to offset gains.", "Know the 12-month boundary."],
         careful=["Frequent trading can eat returns.", "Intraday and F&O are taxed differently."]),
    dict(id="idcw", title="IDCW — income distribution cum capital withdrawal",
         en="IDCW is the mutual-fund option that pays out income instead of reinvesting it.",
         hi="IDCW mutual fund ka payout option hai; income aapko milti hai, fund mein dobara invest nahi hoti.",
         analogy="Instead of letting the rent accumulate in the shop account, you withdraw it every month.",
         formula="IDCW payout = Units × IDCW per unit",
         plain="Units ko per-unit payout se multiply karo.",
         ex=["1,000 units and ₹2 IDCW per unit.", "Payout = ₹2,000.", "The NAV falls by about the payout."],
         good=["Useful when you need regular cash.", "Choose growth if you are accumulating."],
         careful=["Payout is not extra return; NAV drops.", "IDCW is taxable at your slab."]),
    dict(id="inav", title="iNAV — the fair value of an ETF right now",
         en="iNAV is the estimated per-unit value of an ETF's holdings, updated during the session.",
         hi="iNAV ETF ke holdings ki live estimated value hai, session ke dauraan update hoti hai.",
         analogy="The weighing scale shows the real weight, while the price tag may lag.",
         formula="iNAV = (Value of holdings + cash − liabilities) ÷ Units",
         plain="Holdings ki value ko units se divide karo.",
         ex=["Holdings worth ₹1,00,000 and 1,000 units.", "iNAV = ₹100.", "If the ETF trades at ₹102, it is at a premium."],
         good=["Compare market price with iNAV before trading.", "Large premiums often mean thin liquidity."],
         careful=["iNAV can be stale in illiquid ETFs.", "A premium can collapse when market makers return."]),
    dict(id="tracking-error", title="Tracking error — how far a fund drifts from its index",
         en="Tracking error measures the ups and downs of a fund's return versus its benchmark.",
         hi="Tracking error batata hai fund apne index se kitna aage-peeche hota hai.",
         analogy="A train should reach each station on time; the average delay is tracking error.",
         formula="Tracking error = Standard deviation of (Fund return − Index return)",
         plain="Fund aur index ke daily difference ka volatility.",
         ex=["Index returns 10% and fund 9.8%.", "The gap is 0.2% a year.", "Lower, steadier gaps mean lower tracking error."],
         good=["Index funds should have low tracking error.", "Check it over 3–5 years."],
         careful=["A low error can still hide high costs.", "Different indices are not comparable."]),
    dict(id="modified-duration", title="Modified duration — bond price sensitivity",
         en="Modified duration estimates how much a bond's price moves for a 1% change in yield.",
         hi="Modified duration batata hai yield 1% badle to bond price kitna badlega.",
         analogy="A longer see-saw moves more at the far end for the same push.",
         formula="Price change ≈ −Modified duration × Yield change",
         plain="Duration jitna zyada, yield change se price utna zyada hilta hai.",
         ex=["Duration 6 and yield rises 1%.", "Price falls about 6%.", "On ₹1,000, that is roughly ₹60."],
         good=["Use it to compare interest-rate risk.", "Short-duration funds are steadier."],
         careful=["It is an approximation for small yield moves.", "Credit risk can hurt independently."]),
    dict(id="g-sec", title="G-Sec — sovereign government bond",
         en="A G-Sec is a bond issued by the Government of India; it carries sovereign default risk only.",
         hi="G-Sec Government of India ka bond hai; ismein sirf sovereign risk hota hai.",
         analogy="The safest borrower in the country is the government itself.",
         formula="G-Sec yield = Coupon adjusted for price and maturity",
         plain="Government bond ka return; price girne par yield badhta hai.",
         ex=["Face value ₹100 and coupon 7%.", "Buy at ₹100, get ₹7 a year.", "At ₹95, the yield is higher than 7%."],
         good=["Lowest credit risk in rupee bonds.", "Useful for parking long-term money."],
         careful=["Prices still fall when yields rise.", "Long G-Secs can be volatile."]),
    dict(id="sdl", title="SDL — state development loan",
         en="An SDL is a bond issued by a state government, usually yielding a little more than a G-Sec.",
         hi="SDL state government ka bond hai, G-Sec se thoda zyada yield deta hai.",
         analogy="A state's promise is strong, but the Centre's is the strongest.",
         formula="SDL yield = G-Sec yield + state spread",
         plain="G-Sec yield mein state ka extra spread jodo.",
         ex=["G-Sec 7.0% and state spread 0.4%.", "SDL yield about 7.4%.", "The extra 0.4% pays for state credit risk."],
         good=["Higher yield with strong credit quality.", "Useful for long-duration allocation."],
         careful=["State finances differ; check the spread.", "Liquidity is thinner than G-Secs."]),
    dict(id="wale", title="WALE — weighted average lease expiry",
         en="WALE is the average time left on a REIT's leases, weighted by rent.",
         hi="WALE batata hai REIT ke leases average kitne saal aur chalenge, rent ke hisaab se.",
         analogy="A shop with tenants signed for 8 more years has a safer rent stream than one with 1-year contracts.",
         formula="WALE = Σ (Lease years × Rent) ÷ Total rent",
         plain="Har lease ke saal ko rent se weight karke average nikaalo.",
         ex=["Half the rent runs 10 years, half 2 years.", "WALE = 6 years.", "Longer WALE means steadier cash flow."],
         good=["Long WALE with strong tenants is defensive.", "Check lease expiries clustered in one year."],
         careful=["Long leases can still be renegotiated.", "WALE ignores tenant credit quality."]),
    dict(id="ndcf", title="NDCF — net distributable cash flow",
         en="NDCF is the cash a REIT or InvIT can distribute after expenses, interest and reserves.",
         hi="NDCF woh cash hai jo REIT/InvIT kharche, interest aur reserve ke baad baant sakta hai.",
         analogy="From the shop's rent, pay repairs and the loan EMI; what remains is yours to take home.",
         formula="NDCF = Net cash from operations − Capex − Interest − Reserves",
         plain="Operating cash se zaroori kharche hatao; baaki distribution.",
         ex=["Rent ₹1,000, expenses ₹200, interest ₹150.", "NDCF = ₹650.", "At 1,000 units, ₹0.65 per unit."],
         good=["SEBI requires at least 90% of NDCF to be distributed.", "Rising NDCF per unit is a good sign."],
         careful=["Capex can be lumpy.", "Distribution is not the same as profit."]),
    dict(id="cap-rate", title="Cap rate — the yield on a property",
         en="Cap rate is a property's annual net operating income divided by its value.",
         hi="Cap rate property ki annual net income ko uski value se divide karta hai.",
         analogy="A shop worth ₹1 crore earns ₹6 lakh rent after costs; the cap rate is 6%.",
         formula="Cap rate = Net operating income ÷ Property value × 100",
         plain="Saal ki net income ko property value se divide karo.",
         ex=["NOI ₹6,00,000 and value ₹1,00,00,000.", "6,00,000 ÷ 1,00,00,000 = 6%.", "A lower cap rate means a richer valuation."],
         good=["Compare cap rates within the same city and asset type.", "Rising cap rates can signal cheaper valuations."],
         careful=["It ignores future capex and vacancy.", "A high cap rate may be a warning, not a bargain."]),
    dict(id="asm-gsm", title="ASM / GSM — exchange surveillance flags",
         en="ASM and GSM are exchange lists of stocks with unusual price moves or governance concerns; trading gets extra checks.",
         hi="ASM aur GSM exchange ke surveillance lists hain; aise stocks mein extra margin ya checks lagte hain.",
         analogy="A shop put on a watchlist gets extra security checks before every sale.",
         formula="No formula — check the exchange list before trading",
         plain="Exchange ki list dekho; flag laga ho to extra margin lag sakta hai.",
         ex=["A stock enters ASM Stage 1.", "Brokers may demand 100% margin.", "Price can still move, but liquidity tightens."],
         good=["A flag is a warning, not proof of fraud.", "Read the exchange circular for the stage."],
         careful=["Extra margin can force selling.", "GSM flags often persist for months."]),
    dict(id="fii-dii", title="FII / DII — who is buying and selling",
         en="FIIs are foreign institutional investors; DIIs are domestic institutions like mutual funds and insurers.",
         hi="FII videshi institutional investors hain; DII ghar ke mutual funds aur insurance companies.",
         analogy="Two big families buy in the same vegetable market; their daily purchases move prices.",
         formula="Net flow = FII net + DII net",
         plain="FII aur DII ke net buy/sell ko jodo.",
         ex=["FIIs buy ₹2,000 crore.", "DIIs sell ₹500 crore.", "Net institutional flow is +₹1,500 crore."],
         good=["Persistent DII buying can cushion FII selling.", "Use flows with valuations, not alone."],
         careful=["One day's flow is noise.", "FII data can be revised."]),
    dict(id="circuit-filter", title="Circuit filter — the daily price band",
         en="A circuit filter is the exchange's daily limit on how far a stock can move.",
         hi="Circuit filter exchange ka daily price band hai; stock us se zyada nahi hil sakta.",
         analogy="A lift has a top and bottom floor; it cannot go beyond them in one trip.",
         formula="Band = Previous close ± permitted %",
         plain="Kal ke close se fixed % upar/neeche.",
         ex=["Previous close ₹100 and 10% band.", "Range ₹90–₹110.", "A 5% band would be ₹95–₹105."],
         good=["Wide bands suit liquid large caps.", "Narrow bands protect against spikes."],
         careful=["A locked band can trap you.", "Bands can change after surveillance action."]),
    dict(id="promoter-holding", title="Promoter holding — skin in the game",
         en="Promoter holding is the percentage of the company owned by its founders or controlling group.",
         hi="Promoter holding batata hai company ka kitna hissa founders/control group ke paas hai.",
         analogy="The shop owner keeping 60% of his own shop signals he believes in it.",
         formula="Promoter % = Promoter shares ÷ Total shares × 100",
         plain="Promoter shares ko total shares se divide karo.",
         ex=["Promoters hold 6,000 of 10,000 shares.", "Holding = 60%.", "A steady or rising stake is a positive."],
         good=["High, stable promoter holding is reassuring.", "Check incremental buying."],
         careful=["High holding can also mean low free float.", "Pledging can weaken the signal."]),
    dict(id="debt-equity", title="Debt to equity — how much borrowed money",
         en="Debt-to-equity compares total borrowings with shareholders' funds.",
         hi="Debt-to-equity total karz ko owners ke paise se compare karta hai.",
         analogy="If you put ₹1,000 and borrow ₹500 for a shop, debt/equity is 0.5×.",
         formula="D/E = Total debt ÷ Shareholders' equity",
         plain="Karz ko equity se divide karo.",
         ex=["Debt ₹500 and equity ₹1,000.", "D/E = 0.5×.", "Debt ₹2,000 would be 2× — much riskier."],
         good=["Below 1× is comfortable for most manufacturers.", "Compare within the industry."],
         careful=["Banks run high D/E by design.", "Hidden leases can add debt."]),
    dict(id="interest-coverage", title="Interest coverage — can profit pay the interest?",
         en="Interest coverage divides operating profit by interest cost.",
         hi="Interest coverage batata hai operating profit se interest kitni baar cover hota hai.",
         analogy="Your salary covers the home-loan EMI 4 times over; that is comfortable.",
         formula="Interest coverage = EBIT ÷ Interest expense",
         plain="Operating profit ko interest se divide karo.",
         ex=["EBIT ₹400 and interest ₹100.", "Coverage = 4×.", "Below 1.5× is a warning."],
         good=["Above 3× is generally comfortable.", "Rising coverage means deleveraging."],
         careful=["EBIT is not cash.", "Falling revenue can crush coverage quickly."]),
    dict(id="free-cash-flow", title="Free cash flow — the cash left after capex",
         en="Free cash flow is operating cash minus the capital spent to keep the business running.",
         hi="Free cash flow operating cash hai minus business chalane ke liye ki gayi capex.",
         analogy="From your salary, pay rent and bills; what is left is free cash.",
         formula="FCF = Operating cash flow − Capital expenditure",
         plain="Operating cash se capex ghatao.",
         ex=["Operating cash ₹500 and capex ₹200.", "FCF = ₹300.", "Positive FCF can fund dividends or buybacks."],
         good=["Consistent positive FCF is high quality.", "FCF yield compares FCF with market cap."],
         careful=["One big capex year can turn FCF negative.", "Working-capital swings distort it."]),
    dict(id="working-capital", title="Working capital — money stuck in the daily cycle",
         en="Working capital is current assets minus current liabilities: cash tied up in stock and receivables.",
         hi="Working capital current assets minus current liabilities; stock aur udhaar mein phansa paisa.",
         analogy="You buy vegetables on Monday, sell them on Friday, and get paid next Monday; that gap needs cash.",
         formula="Working capital = Current assets − Current liabilities",
         plain="Current assets se current liabilities ghatao.",
         ex=["Stock ₹300, receivables ₹200, payables ₹150.", "Working capital = ₹350.", "Faster collection frees cash."],
         good=["Negative working capital can be a moat (advance-paid businesses).", "Watch the cash-conversion cycle."],
         careful=["Too much stock can hide obsolescence.", "Stretched payables can hurt suppliers."]),
    dict(id="operating-leverage", title="Operating leverage — fixed costs magnify profit",
         en="Operating leverage measures how much profit changes when sales change, because fixed costs stay put.",
         hi="Operating leverage batata hai sales badalne par profit kitna zyada badalta hai, kyunki fixed cost same rehta hai.",
         analogy="A cinema hall with fixed rent earns a lot more when seats fill up.",
         formula="Operating leverage = Contribution ÷ EBIT",
         plain="Sales ka contribution operating profit se compare karo.",
         ex=["Sales rise 10%, EBIT rises 25%.", "Operating leverage is 2.5×.", "The same works in reverse when sales fall."],
         good=["High leverage is great in a growing cycle.", "Check it before forecasting."],
         careful=["It cuts both ways.", "Fixed costs can become stranded."]),
    dict(id="open-interest", title="Open interest — contracts still alive",
         en="Open interest is the number of futures or options contracts currently open, not yet squared off.",
         hi="Open interest kitne futures/options contracts abhi open hain, close nahi hue.",
         analogy="The number of tokens currently inside an amusement park, not the total visitors all day.",
         formula="Open interest = Long contracts = Short contracts",
         plain="Abhi kitne contracts chal rahe hain.",
         ex=["10,000 contracts open yesterday.", "12,000 today.", "OI rose 20% with price."],
         good=["Rising OI with rising price suggests fresh longs.", "Falling OI means positions are closing."],
         careful=["OI alone does not tell direction.", "Expiry week distorts the number."]),
    dict(id="rollover", title="Rollover — carrying a futures position to the next expiry",
         en="Rollover is closing the near-month futures contract and opening the next month's.",
         hi="Rollover matlab near-month futures band karke next month kholna.",
         analogy="You renew your monthly gym membership before it expires.",
         formula="Rollover % = Next-month OI ÷ (Near-month OI + Next-month OI) × 100",
         plain="Next month ke open interest ka share nikaalo.",
         ex=["Near month OI 8,000 and next month 2,000.", "Rollover = 20%.", "High rollover shows positions are staying."],
         good=["High rollover with premium suggests bullish carry.", "Compare with the 3-month average."],
         careful=["Rollover costs depend on the basis.", "Low rollover can mean positions are being closed."]),
    dict(id="vix", title="VIX — the market's fear gauge",
         en="VIX measures expected 30-day volatility from option prices; higher means more fear.",
         hi="VIX option prices se agle 30 din ki expected volatility batata hai; zyada matlab zyada darr.",
         analogy="Insurance premiums rise when a storm is expected; VIX is that premium for the market.",
         formula="VIX is derived from a basket of index option prices",
         plain="Options se 30-day expected volatility nikaali jaati hai.",
         ex=["VIX 11 means calm.", "VIX 22 means nervous.", "VIX above 30 often comes with sharp falls."],
         good=["High VIX can create long-term buying chances.", "Low VIX means cheap hedges."],
         careful=["VIX is not a direction forecast.", "It can spike and fall quickly."]),
    dict(id="repo-rate", title="Repo rate — RBI's policy rate",
         en="The repo rate is the rate at which banks borrow short-term money from the RBI.",
         hi="Repo rate woh rate hai jis par banks RBI se short-term paisa udhaar lete hain.",
         analogy="The wholesale price of money; retail loan rates follow it.",
         formula="Loan rate ≈ Repo rate + bank spread",
         plain="RBI ka rate plus bank ka margin.",
         ex=["Repo 6.5% and spread 2.5%.", "Home loan about 9%.", "A repo cut can lower EMIs with a lag."],
         good=["Falling repo supports borrowing and equities.", "Watch the stance, not just the level."],
         careful=["Transmission to your loan is not instant.", "Inflation can force a reversal."]),
    dict(id="crr", title="CRR — cash reserve ratio",
         en="CRR is the share of deposits banks must keep with the RBI as cash.",
         hi="CRR deposits ka woh hissa hai jo banks ko RBI ke paas cash mein rakhna padta hai.",
         analogy="A shop must keep some cash in the drawer and cannot lend all of it.",
         formula="CRR = Cash kept with RBI ÷ Net demand and time liabilities",
         plain="Deposits ka fixed % RBI ke paas.",
         ex=["Deposits ₹1,000 crore and CRR 4%.", "₹40 crore is locked with RBI.", "A CRR cut frees money to lend."],
         good=["A CRR cut is mildly expansionary.", "It is a blunt liquidity tool."],
         careful=["It does not directly set loan rates.", "Changes are infrequent."]),
    dict(id="cpi", title="CPI — consumer inflation",
         en="CPI tracks the price of a basket of goods and services that households buy.",
         hi="CPI ghar ke roz ke saman aur services ke price basket ko track karta hai.",
         analogy="Your monthly grocery bill, measured against last year's bill.",
         formula="CPI inflation = (Current basket cost ÷ Base basket cost − 1) × 100",
         plain="Aaj ke basket ko purane basket se compare karo.",
         ex=["Basket ₹10,000 last year.", "₹10,600 this year.", "CPI inflation = 6%."],
         good=["RBI targets 4% CPI.", "Falling CPI can allow rate cuts."],
         careful=["Food prices are volatile.", "Your personal basket may differ."]),
    dict(id="bulk-deal", title="Bulk deal — a large single-day trade",
         en="A bulk deal is a single trade of more than 0.5% of a company's listed shares.",
         hi="Bulk deal ek din mein 0.5% se zyada listed shares ka single trade hai.",
         analogy="One buyer clearing a whole shelf in one visit.",
         formula="Bulk deal threshold = 0.5% of listed shares",
         plain="Listed shares ka 0.5% se zyada ek trade.",
         ex=["Company has 1 crore shares.", "Threshold is 50,000 shares.", "The exchange publishes the buyer and seller."],
         good=["Large institutional buying can be a signal.", "Check the price versus the market."],
         careful=["One deal does not make a trend.", "It can be a block placement at a discount."]),
    dict(id="block-deal", title="Block deal — a pre-arranged large trade",
         en="A block deal is a large trade negotiated privately and executed in a separate window.",
         hi="Block deal ek bada trade hai jo private mein tay ho kar alag window mein hota hai.",
         analogy="A wholesale deal agreed before the shop opens.",
         formula="Block deal = pre-agreed price × large quantity",
         plain="Pehle price tay, phir ek saath bada trade.",
         ex=["10 lakh shares at ₹100.", "That is ₹10 crore.", "Often done at a small discount."],
         good=["Can absorb large selling without crashing the price.", "Watch who bought."],
         careful=["Discount can signal weak demand.", "Lock-in may apply."]),
    dict(id="buyback", title="Buyback — the company buys its own shares",
         en="A buyback returns cash to shareholders by purchasing shares, usually at a premium.",
         hi="Buyback mein company apne shares kharid kar cash shareholders ko lautati hai, aksar premium par.",
         analogy="A shop buys back its own partnership tokens from partners.",
         formula="Buyback premium = (Buyback price ÷ Market price − 1) × 100",
         plain="Buyback price ko market price se compare karo.",
         ex=["Market price ₹100 and buyback ₹120.", "Premium = 20%.", "Accepted shares get the higher price."],
         good=["A premium buyback can reward holders.", "Check the acceptance ratio."],
         careful=["Not all your shares may be accepted.", "Debt-funded buybacks can hurt."]),
    dict(id="bonus-issue", title="Bonus issue — free shares, same value",
         en="A bonus issue gives existing shareholders extra shares without any payment.",
         hi="Bonus issue mein existing shareholders ko bina paise diye extra shares milte hain.",
         analogy="Cutting one roti into two does not give you more food.",
         formula="Post-bonus shares = Old shares × (1 + Bonus ratio)",
         plain="Purane shares mein bonus ratio jodo.",
         ex=["100 shares and a 1:1 bonus.", "You get 100 more.", "Price roughly halves."],
         good=["Improves liquidity and retail participation.", "Signals confidence sometimes."],
         careful=["Total value does not change on day one.", "Tax rules for bonus shares differ."]),
    dict(id="rights-issue", title="Rights issue — first refusal to existing holders",
         en="A rights issue lets existing shareholders buy new shares, usually at a discount.",
         hi="Rights issue mein existing shareholders ko discount par naye shares kharidne ka pehla haq milta hai.",
         analogy="Society members get first chance to buy the new flats at a lower price.",
         formula="Rights entitlement = Shares held × Rights ratio",
         plain="Aapke shares ke hisaab se kitne naye shares milte hain.",
         ex=["100 shares and a 1:4 rights issue.", "You can buy 25 new shares.", "Price is usually below market."],
         good=["Cheaper than market if you believe in the story.", "Renounceable rights have value."],
         careful=["Dilution if you skip it.", "Rights money is real cash."]),
    dict(id="demerger", title="Demerger — one company splits into two",
         en="A demerger separates a business into a new listed company and gives shares to existing holders.",
         hi="Demerger mein business alag company ban jaata hai aur existing holders ko uske shares milte hain.",
         analogy="A shop splits into a grocery and a bakery; you own a piece of both.",
         formula="Cost allocation = Original cost × Fair value share",
         plain="Purani cost ko dono businesses ke fair value mein baanto.",
         ex=["Original cost ₹1,000.", "60% stays, 40% demerges.", "Cost split ₹600 and ₹400."],
         good=["Can unlock value if the parts are worth more separately.", "Read the scheme carefully."],
         careful=["New shares can be illiquid at first.", "Cost allocation affects tax."]),
    dict(id="swp", title="SWP — systematic withdrawal plan",
         en="An SWP withdraws a fixed amount from a mutual fund at regular intervals.",
         hi="SWP mutual fund se fixed amount regular intervals par nikaalta hai.",
         analogy="A monthly pension from your own saved corpus.",
         formula="Corpus after withdrawal = Previous corpus × (1 + return) − Withdrawal",
         plain="Return lagao, phir withdrawal ghatao.",
         ex=["Corpus ₹10,00,000 at 8%.", "Withdraw ₹10,000 a month.", "Check how long the corpus lasts."],
         good=["Useful for retirement income.", "More tax-efficient than some alternatives."],
         careful=["A high withdrawal rate can exhaust the corpus.", "Returns are not guaranteed."]),
    dict(id="tds", title="TDS — tax deducted at source",
         en="TDS is tax the payer deducts before paying you, such as 10% on large dividends.",
         hi="TDS woh tax hai jo dene wala aapko paise dene se pehle kaat leta hai, jaise bade dividend par 10%.",
         analogy="Your employer keeps a slice of salary for tax and pays the rest.",
         formula="TDS = Payment × TDS rate",
         plain="Payment par fixed rate kaat lo.",
         ex=["Dividend ₹10,000.", "10% TDS = ₹1,000.", "You receive ₹9,000; TDS is adjusted in your return."],
         good=["TDS is a credit, not an extra tax.", "Check Form 26AS."],
         careful=["TDS may be lower than your final slab.", "No TDS does not mean no tax."]),
    dict(id="t2t", title="T2T — trade-to-trade segment",
         en="T2T stocks must be bought and sold only with full delivery; no intraday netting.",
         hi="T2T stocks sirf full delivery ke saath kharide-beche ja sakte hain; intraday nahi.",
         analogy="You must take the goods home before selling them again.",
         formula="No formula — delivery is compulsory",
         plain="Har trade mein delivery lena zaroori hai.",
         ex=["Buy 100 shares today.", "You must take delivery.", "Sell only after they are in your demat."],
         good=["Reduces speculative churn.", "Often used for surveillance stocks."],
         careful=["No intraday exit.", "Liquidity can be thin."]),
]

TRACKS["market-jargon"] = {
    "title": "Market Jargon — 45 Terms in Plain Words",
    "level": "Beginner",
    "summary": "The ratios, circuit limits, IPO words, bond terms and REIT metrics that Indian screens throw at you — each explained with a dukaan analogy and a ₹1,000 example.",
    "asset": "Universal",
    "lessons": [
        lesson(g["id"], g["title"], g["en"], g["hi"], g["analogy"], g["formula"],
               g["plain"], "A ₹1,000 example", g["ex"], g["good"], g["careful"],
               f"/learn/market-jargon?topic={g['id']}")
        for g in _GLOSSARY
    ],
}


# Every synonym a reader might type, mapped to the lesson that explains it.
ALIASES = {
    "profit to book value": "pat-to-book", "pat to book": "pat-to-book",
    "profit to book": "pat-to-book", "return on net worth": "pat-to-book",
    "price to book value": "price-to-book-value", "price to book": "price-to-book-value",
    "p/b": "price-to-book-value", "pb": "price-to-book-value",
    "p/b ratio": "price-to-book-value", "book value": "price-to-book-value",
    "enterprise value": "enterprise-value", "ev": "enterprise-value",
    "ev/ebitda": "ev-ebitda", "ev to ebitda": "ev-ebitda",
    "ebitda margin": "ebitda-margin", "operating margin": "ebitda-margin",
    "upper circuit": "upper-circuit", "lower circuit": "upper-circuit",
    "circuit": "circuit-filter", "circuit filter": "circuit-filter",
    "price band": "circuit-filter",
    "pledged shares": "pledged-shares", "pledging": "pledged-shares",
    "pledge": "pledged-shares", "promoter pledge": "pledged-shares",
    "free float": "free-float", "free-float": "free-float",
    "xirr": "xirr", "rolling return": "rolling-return",
    "rolling returns": "rolling-return", "gmp": "gmp",
    "grey market premium": "gmp", "gray market premium": "gmp",
    "ofs": "ofs", "offer for sale": "ofs", "drhp": "drhp",
    "rhp": "drhp", "red herring prospectus": "drhp",
    "lot size": "lot-size", "lot": "lot-size",
    "cut-off price": "cut-off-price", "cut off price": "cut-off-price",
    "cutoff": "cut-off-price", "stt": "stt",
    "securities transaction tax": "stt", "ltcg": "ltcg",
    "long term capital gain": "ltcg", "long-term capital gains": "ltcg",
    "stcg": "stcg", "short term capital gain": "stcg",
    "short-term capital gains": "stcg", "expense ratio": "expense-drag",
    "expense drag": "expense-drag", "exit load": "tax",
    "idcw": "idcw", "dividend payout": "idcw",
    "inav": "inav", "i-nav": "inav", "tracking error": "tracking-error",
    "ytm": "ytm", "yield to maturity": "ytm",
    "modified duration": "modified-duration", "duration": "duration",
    "g-sec": "g-sec", "gsec": "g-sec", "government bond": "g-sec",
    "sdl": "sdl", "state development loan": "sdl",
    "sgb": "sgb", "sovereign gold bond": "sgb",
    "wale": "wale", "ndcf": "ndcf", "cap rate": "cap-rate",
    "capitalisation rate": "cap-rate", "asm": "asm-gsm", "gsm": "asm-gsm",
    "asm/gsm": "asm-gsm", "fii": "fii-dii", "dii": "fii-dii",
    "fii/dii": "fii-dii", "fii dii": "fii-dii",
    "promoter holding": "promoter-holding", "promoter": "promoter-holding",
    "debt to equity": "debt-equity", "debt/equity": "debt-equity",
    "d/e": "debt-equity", "interest coverage": "interest-coverage",
    "free cash flow": "free-cash-flow", "fcf": "free-cash-flow",
    "working capital": "working-capital", "operating leverage": "operating-leverage",
    "open interest": "open-interest", "oi": "open-interest",
    "rollover": "rollover", "vix": "vix", "india vix": "vix",
    "repo": "repo-rate", "repo rate": "repo-rate", "crr": "crr",
    "cpi": "cpi", "inflation": "cpi", "bulk deal": "bulk-deal",
    "block deal": "block-deal", "buyback": "buyback",
    "bonus": "bonus-issue", "bonus issue": "bonus-issue",
    "rights": "rights-issue", "rights issue": "rights-issue",
    "demerger": "demerger", "swp": "swp", "tds": "tds",
    "t2t": "t2t", "trade to trade": "t2t",
    # Existing lessons, so the short forms land too.
    "pe": "pe", "p/e": "pe", "price to earnings": "pe",
    "roe": "roe-roce", "return on equity": "roe-roce",
    "roce": "roe-roce", "return on capital employed": "roe-roce",
    "cagr": "cagr", "sip": "sip", "nav": "nav", "aum": "nav",
    "dividend yield": "dividend-yield", "dividend": "dividend-yield",
    "volatility": "volatility", "vix volatility": "vix",
}


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("/", " ").replace("-", " ")
                    .replace("_", " ").split())


def _all_lessons():
    for tid, track in TRACKS.items():
        for item in track["lessons"]:
            yield tid, track, item


def _alias_hits(q: str) -> list[dict]:
    needle = _norm(q)
    if not needle:
        return []
    hits = []
    for alias, lesson_id in ALIASES.items():
        a = _norm(alias)
        if a == needle or (len(needle) >= 3 and (a.startswith(needle) or needle in a)):
            for tid, track, item in _all_lessons():
                if item["id"] == lesson_id:
                    hits.append({
                        "id": item["id"], "title": item["title"],
                        "one_liner": item["one_liner"], "track_id": tid,
                        "track_title": track["title"], "asset": track["asset"],
                        "href": f"/learn/{tid}?topic={item['id']}",
                        "match_reason": f"alias: {alias}",
                    })
                    break
    # De-duplicate while preserving the alias order.
    seen, out = set(), []
    for h in hits:
        if h["id"] not in seen:
            seen.add(h["id"])
            out.append(h)
    return out


@router.get("")
def index_page():
    return {
        "asof": ASOF,
        "tracks": [{"id": tid, "title": t["title"], "level": t["level"],
                    "summary": t["summary"], "asset": t["asset"],
                    "lesson_count": len(t["lessons"])}
                   for tid, t in TRACKS.items()],
        "total_lessons": sum(len(t["lessons"]) for t in TRACKS.values()),
        "note": ("Every topic is one small card: simple meaning, everyday analogy, "
                 "plain-words formula, a 3-line ₹100/₹1,000 example and a quick "
                 "thumb rule. Educational only — not investment advice."),
    }


@router.get("/search")
def search_lessons(q: str = Query("", min_length=1), db: Session = Depends(get_db)):
    """Two-layer beginner search: synonym index first, then AI generation.

    Layer 1 merges the alias index (``p/b`` → price-to-book) with a plain
    substring scan over every lesson. If nothing matches, the response asks the
    UI to show — and optionally auto-trigger — the AI lesson generator.
    """
    needle = _norm(q)
    raw = q.strip().lower()
    hits: list[dict] = []
    seen: set[str] = set()

    for h in _alias_hits(q):
        if h["id"] not in seen:
            seen.add(h["id"])
            hits.append(h)

    for tid, track in TRACKS.items():
        for lesson_ in track["lessons"]:
            if lesson_["id"] in seen:
                continue
            hay = _norm(" ".join(str(lesson_.get(k) or "") for k in
                                 ("title", "one_liner", "hinglish", "analogy",
                                  "formula", "body", "pitfall")))
            hay_raw = " ".join(str(lesson_.get(k) or "") for k in
                               ("title", "one_liner", "hinglish", "analogy",
                                "body", "pitfall")).lower()
            if (needle and needle in hay) or (raw and raw in hay_raw):
                seen.add(lesson_["id"])
                hits.append({
                    "id": lesson_["id"],
                    "title": lesson_["title"],
                    "one_liner": lesson_["one_liner"],
                    "track_id": tid,
                    "track_title": track["title"],
                    "asset": track["asset"],
                    "href": f"/learn/{tid}?topic={lesson_['id']}",
                    "match_reason": "text match",
                })

    cached = _cached_topic(db, q)
    top = None
    if hits:
        for _tid, _track, item in _all_lessons():
            if item["id"] == hits[0]["id"]:
                top = item
                break
    return {
        "query": q,
        "count": len(hits),
        "lessons": hits[:30],
        "top_lesson": top,
        "ai_suggest": {
            "label": f'✨ Generate Simple Lesson for "{q}" with AI',
            "endpoint": "/api/v1/academy/ask-topic",
            "auto_generate": len(hits) == 0,
            "cached": bool(cached),
        },
        "cached_topic": _topic_wire(cached) if cached else None,
    }


# ------------------------------------------------------- live AI topic cards
def _topic_slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s or "topic")[:150]


def _topic_wire(row) -> dict:
    payload = dict(row.payload or {})
    payload.setdefault("id", row.slug)
    payload.setdefault("title", row.title)
    payload["query"] = row.query
    payload["ai_generated"] = True
    payload["provider"] = row.provider
    payload["model"] = row.model
    payload["cached"] = True
    return payload


def _cached_topic(db: Session, q: str):
    slug = _topic_slug(q)
    row = db.get(AcademyTopic, slug)
    if row is None:
        return None
    try:
        row.hits = (row.hits or 0) + 1
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    return row


SYSTEM_PROMPT = (
    "You are a friendly Indian markets teacher. Explain one financial term for a "
    "complete beginner in India. Use simple English and natural Hinglish. Never "
    "give investment advice. Reply with JSON only."
)

PROMPT = """Explain the financial term "{q}" as one beginner lesson.

Return strict JSON with exactly these keys:
{{
  "title": "short title with a plain-English hint",
  "en": "1-2 super simple English sentences",
  "hi": "the same meaning in natural Hinglish",
  "analogy": "one everyday Indian analogy (dukaan, rent, chai, ticket, daily life)",
  "formula": "the formula in plain words, or 'No formula' if not applicable",
  "plain": "one line explaining the formula in Hinglish",
  "example_title": "short title for a round-number example",
  "lines": ["line 1", "line 2", "line 3"],
  "good": ["when this is good / healthy", "one more positive signal"],
  "careful": ["when to be careful", "one more risk"]
}}

The three example lines must use round ₹100 / ₹1,000 numbers and show the maths.
If "{q}" is not a financial term, still explain the closest market concept and
say so in the first sentence. Keep every string short enough for a card.
"""


def _generic_card(q: str, reason: str) -> dict:
    """Honest fallback so the UI never shows an empty card."""
    title = q.strip().title() or "Market term"
    return {
        "id": _topic_slug(q), "title": title, "one_liner": "",
        "hinglish": "", "simple": {"en": "", "hi": ""}, "analogy": "",
        "formula": {"expression": "", "plain": "", "variables": [], "note": ""},
        "example": {"title": "", "lines": [], "calculation": "", "result": "",
                    "asof": ASOF},
        "thumb_rule": {"good": [], "careful": []}, "body": "", "pitfall": "",
        "link": {"label": "Browse all lessons", "href": "/learn"},
        "ai_generated": False, "provider": None, "model": None,
        "cached": False, "error": reason,
    }


def _normalise_card(q: str, data: dict, provider: str, model: str) -> dict:
    lines = [str(x) for x in (data.get("lines") or [])][:3]
    while len(lines) < 3:
        lines.append("")
    good = [str(x) for x in (data.get("good") or [])][:4]
    careful = [str(x) for x in (data.get("careful") or [])][:4]
    en = str(data.get("en") or "")
    hi = str(data.get("hi") or "")
    analogy = str(data.get("analogy") or "")
    card = {
        "id": _topic_slug(q),
        "title": str(data.get("title") or q.strip().title()),
        "one_liner": en,
        "hinglish": hi,
        "simple": {"en": en, "hi": hi},
        "analogy": analogy,
        "formula": {
            "expression": str(data.get("formula") or "No formula"),
            "plain": str(data.get("plain") or ""),
            "variables": [],
            "note": "Generated for learning only; verify with the company's filing.",
        },
        "example": {
            "title": str(data.get("example_title") or "A ₹1,000 example"),
            "lines": lines,
            "calculation": lines[1] if len(lines) > 1 else "",
            "result": lines[-1] if lines else "",
            "asof": ASOF,
        },
        "thumb_rule": {"good": good, "careful": careful},
        "body": f"{en} {analogy}".strip(),
        "pitfall": (careful or ["Numbers change; always check the date."])[0],
        "link": {"label": "Browse all lessons", "href": "/learn"},
        "ai_generated": True,
        "provider": provider,
        "model": model,
        "cached": False,
    }
    return card


class AskTopicRequest(BaseModel):
    query: str
    force: bool = False


@router.post("/ask-topic")
def ask_topic(req: AskTopicRequest, db: Session = Depends(get_db)):
    """Generate a five-card beginner lesson for any term, cached in SQLite.

    Gemini → Groq → OpenRouter via the shared failover router. The first call
    pays the latency; later identical searches read the cached row.
    """
    q = (req.query or "").strip()
    if not q:
        raise HTTPException(400, "Ask for a topic, e.g. 'profit to book value'.")
    if not req.force:
        row = _cached_topic(db, q)
        if row is not None:
            return {"query": q, "source": "cache", "latency_ms": 0,
                    "lesson": _topic_wire(row)}
    t0 = time.time()
    try:
        result = complete(PROMPT.format(q=q), system=SYSTEM_PROMPT,
                          max_tokens=1200, json_mode=True, route="academy")
        data = extract_json(result.text)
        if not data:
            raise ValueError("model did not return JSON")
        card = _normalise_card(q, data, result.provider, result.model)
    except Exception as e:  # noqa: BLE001
        card = _generic_card(q, f"AI unavailable: {type(e).__name__}")
        return {"query": q, "source": "unavailable",
                "latency_ms": int((time.time() - t0) * 1000), "lesson": card}

    slug = _topic_slug(q)
    row = db.get(AcademyTopic, slug)
    if row is None:
        row = AcademyTopic(slug=slug, query=q, title=card["title"],
                           payload=card, provider=card["provider"],
                           model=card["model"], hits=1)
        db.add(row)
    else:
        row.query, row.title, row.payload = q, card["title"], card
        row.provider, row.model = card["provider"], card["model"]
        row.hits = (row.hits or 0) + 1
        row.updated_at = dt.datetime.utcnow()
    try:
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    card["cached"] = False
    return {"query": q, "source": card["provider"],
            "latency_ms": int((time.time() - t0) * 1000), "lesson": card}


@router.get("/topic/{slug}")
def get_topic(slug: str, db: Session = Depends(get_db)):
    row = db.get(AcademyTopic, _topic_slug(slug))
    if row is None:
        raise HTTPException(404, "Topic not generated yet")
    return {"source": "cache", "lesson": _topic_wire(row)}


@router.get("/{track_id}")
def track_page(track_id: str):
    t = TRACKS.get(track_id)
    if not t:
        raise HTTPException(404, "Unknown track")
    return {"id": track_id, "title": t["title"], "level": t["level"],
            "summary": t["summary"], "asset": t["asset"], "asof": ASOF,
            "lessons": t["lessons"]}
