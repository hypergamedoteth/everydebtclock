#!/usr/bin/env python3
"""One-off helper: create places/<slug>.json for a Eurostat-sourced country from the Poland (national currency) or Spain (euro) file.
Only wording and identifiers are written here; every number is then filled in by `python3 pipeline/fetch_eurostat.py` from Eurostat's API
(and the country must be added to PLACES in fetch_eurostat.py). Usage: python3 pipeline/add_eurostat_country.py denmark"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# slug: (name, ISO2, ISO3, currency code, symbol, currency noun for text, national publisher short note, extra sources [(name, url)], cross-check note, central-gov scope)
C = {
 "denmark": ("Denmark", "DK", "DNK", "DKK", "kr", "kroner",
             [("Danmarks Nationalbank, Government debt (statsgæld)", "https://www.nationalbanken.dk/en/what-we-do/statistics"), ("Statistics Denmark, Government finances", "https://www.dst.dk/en/Statistik/emner/oekonomi/offentlige-finanser")],
             "Cross-check: Danmarks Nationalbank publishes the central government debt (statsgælden) on a national basis, which differs from the Maastricht central government sector used here (for example, in how the government's own deposits and holdings are treated).",
             "In Denmark this is the central government (the State and the central-government bodies classified with it); the municipalities and regions are separate sectors."),
 "czechia": ("Czechia", "CZ", "CZE", "CZK", "Kč", "koruna",
             [("Ministry of Finance of the Czech Republic, State debt management", "https://www.mfcr.cz/en/state-budget/state-debt"), ("Czech Statistical Office, Government finance statistics", "https://csu.gov.cz/government-finance-statistics")],
             "Cross-check: the Czech Ministry of Finance publishes the state debt on a national definition that differs from the Maastricht central government sector used here.",
             "In Czechia this is the central government (the State and the central-government bodies classified with it); the municipalities and regions and the health insurance funds are separate sectors."),
 "romania": ("Romania", "RO", "ROU", "RON", "lei", "lei",
             [("Ministry of Public Finance of Romania, Public debt", "https://mfinante.gov.ro/en/domenii/datorie-publica"), ("National Institute of Statistics (Romania)", "https://insse.ro/cms/en")],
             "Cross-check: Romania's Ministry of Public Finance publishes the government debt on a national definition that differs from the Maastricht central government sector used here.",
             "In Romania this is the central government (the State and the central-government bodies classified with it); local governments and the social security funds are separate sectors."),
 "hungary": ("Hungary", "HU", "HUN", "HUF", "Ft", "forint",
             [("Government Debt Management Agency (ÁKK), Hungary", "https://www.akk.hu/en"), ("Hungarian Central Statistical Office, Government finance", "https://www.ksh.hu/?lang=en")],
             "Cross-check: the Government Debt Management Agency (ÁKK) publishes the central government debt on a national basis, which differs from the Maastricht central government sector used here.",
             "In Hungary this is the central government (the State and the central-government bodies classified with it); local governments are a separate sector."),
 "portugal": ("Portugal", "PT", "PRT", "EUR", "€", "euros",
              [("Banco de Portugal, Public finance statistics", "https://www.bportugal.pt/en/page/public-finance"), ("IGCP, Portuguese Treasury and Debt Management Agency", "https://www.igcp.pt/en/")],
              "Cross-check: Banco de Portugal and the national statistics institute (INE) publish the same EDP (Maastricht) debt by sub-sector; IGCP publishes the State's direct debt on a national basis, which differs.",
              "In Portugal this is the central government (the State and the central-government bodies classified with it); the regions, local governments and social security are separate sectors."),
 "finland": ("Finland", "FI", "FIN", "EUR", "€", "euros",
             [("State Treasury of Finland, State debt", "https://www.treasuryfinland.fi/state-debt/"), ("Statistics Finland, Public finances", "https://stat.fi/en/topics/national-accounts")],
             "Cross-check: the State Treasury of Finland publishes the central government debt on a national basis, which differs from the Maastricht central government sector used here.",
             "In Finland this is the central government (the State and the central-government bodies classified with it); the municipalities, the wellbeing services counties and the social security funds are separate sectors."),
 "greece": ("Greece", "EL", "GRC", "EUR", "€", "euros",
            [("Public Debt Management Agency (PDMA), Public debt bulletin", "https://www.pdma.gr/en/investor-relations/public-dept-bulletings"), ("Bank of Greece, Government debt statistics", "https://www.bankofgreece.gr/en/statistics")],
            "Cross-check: the Public Debt Management Agency's bulletin states the budgetary central government debt on a national basis (EUR 402.6 billion at 30 June 2026), which is higher than the Maastricht central government sector used here because Eurostat consolidates debt held between government units.",
            "In Greece this is the central government (the State and the central-government bodies classified with it); the social security funds and local governments are separate sectors."),
 "slovakia": ("Slovakia", "SK", "SVK", "EUR", "€", "euros",
            [("Debt and Liquidity Management Agency (ARDAL), Slovakia", "https://www.ardal.sk/en"), ("Statistical Office of the Slovak Republic, Government finance", "https://slovak.statistics.sk/")],
            "Cross-check: ARDAL publishes the state debt on a national basis, which differs from the Maastricht central government sector used here.",
            "In Slovakia this is the central government (the State and the central-government bodies classified with it); the municipalities, regions and the health and social insurance funds are separate sectors."),
 "croatia": ("Croatia", "HR", "HRV", "EUR", "€", "euros",
            [("Ministry of Finance of Croatia, Public debt", "https://mfin.gov.hr/en"), ("Croatian Bureau of Statistics", "https://dzs.gov.hr/en")],
            "Cross-check: the Ministry of Finance publishes the general government debt on a national basis, which differs from the Maastricht central government sector used here.",
            "In Croatia this is the central government (the State and the central-government bodies classified with it); local governments are a separate sector."),
 "lithuania": ("Lithuania", "LT", "LTU", "EUR", "€", "euros",
            [("Ministry of Finance of Lithuania, Government debt", "https://finmin.lrv.lt/en/"), ("Statistics Lithuania, Government finance", "https://osp.stat.gov.lt/en/")],
            "Cross-check: the Ministry of Finance publishes the government debt on a national basis, which differs from the Maastricht central government sector used here.",
            "In Lithuania this is the central government (the State and the central-government bodies classified with it); the municipalities and the social security fund are separate sectors."),
 "slovenia": ("Slovenia", "SI", "SVN", "EUR", "€", "euros",
            [("Ministry of Finance of Slovenia, Public debt", "https://www.gov.si/en/state-authorities/ministries/ministry-of-finance/"), ("Statistical Office of the Republic of Slovenia, Government finance", "https://www.stat.si/StatWeb/en")],
            "Cross-check: the Ministry of Finance publishes the central government debt on a national basis, which differs from the Maastricht central government sector used here.",
            "In Slovenia this is the central government (the State and the central-government bodies classified with it); the municipalities and the social security funds are separate sectors."),
}
def main(slug):
    name, a2, a3, code, sym, noun, extra, note_x, scope = C[slug]
    tpl_slug = "spain" if code == "EUR" else "poland"
    p = json.load(open(os.path.join(ROOT, "places", tpl_slug + ".json")))
    tname = "Spain" if tpl_slug == "spain" else "Poland"
    txt = json.dumps(p, ensure_ascii=False).replace(tname + "'s", name + "'s").replace(tname, name)
    p = json.loads(txt)
    p.update(slug=slug, country=a2, iso3=a3, name=name, status="live")
    p["currency"] = {"code": code, "symbol": sym}
    p["link_label"] = f"central government debt, {sym}"
    p["_doc"] = f"One file per place; see places_build.py. Amounts in {noun}. The debt component, history and facts are refreshed by pipeline/fetch_eurostat.py from Eurostat tables gov_10q_ggdebt and demo_pjan; edit wording here, not numbers."
    if code != "EUR": p["scope_note"] = p["scope_note"].replace("Figures are in zlotys", f"Figures are in {noun}").replace("zlotys", noun)
    else: p["scope_note"] = p["scope_note"].replace("euros", noun)
    p["population"]["source_name"] = f"Eurostat, Population on 1 January by age and sex (demo_pjan), {name}"
    p["population"]["noun_full"] = f"people in {name}"
    c = p["components"][0]
    c["source_locator"] = f"geo={a2}, sector S1311, na_item GD, unit {'MIO_EUR' if code == 'EUR' else 'MIO_NAC'}; machine-readable: https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10q_ggdebt"
    c["source_name"] = f"Eurostat, Quarterly government debt (gov_10q_ggdebt), central government (S1311), Maastricht debt, million {noun}"
    c["includes"] = "Central government gross debt at nominal value in the EU's Maastricht (EDP) definition: currency and deposits, short- and long-term debt securities and loans. " + scope
    for f in c["facts"]:
        f["source_locator"] = f"geo={a2}, sector S13, na_item GD, unit {'MIO_EUR' if code == 'EUR' else 'MIO_NAC'}"
    p["extra_sources"] = p["extra_sources"][:1] + [{"name": n, "url": u} for n, u in extra]
    notes = p["notes"][:3]
    if code != "EUR":
        notes.append(f"Currency: {name} reports to Eurostat in {noun} (million {code}, national currency, as published in table gov_10q_ggdebt, unit MIO_NAC). The world page converts to US dollars at the ECB's daily reference rate for {code}.")
    notes.append(note_x)
    p["notes"] = notes
    p["title"] = f"{name} National Debt Clock: Live Debt, Official Data"
    out = os.path.join(ROOT, "places", slug + ".json")
    json.dump(p, open(out, "w"), indent=1, ensure_ascii=False); open(out, "a").write("\n")
    print("wrote", out)
if __name__ == "__main__":
    for s in sys.argv[1:]: main(s)
