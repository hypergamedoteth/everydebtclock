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
 "bulgaria": ("Bulgaria", "BG", "BGR", "EUR", "€", "euros",
            [("Ministry of Finance of Bulgaria, Government debt", "https://www.minfin.bg/en/statistics/"), ("National Statistical Institute of Bulgaria", "https://www.nsi.bg/en")],
            "Cross-check: the Ministry of Finance publishes government debt on the national definition as well. Eurostat's euro and national-currency units for Bulgaria are the same figures.",
            ""),
 "estonia": ("Estonia", "EE", "EST", "EUR", "€", "euros",
            [("Statistics Estonia, Government finance", "https://www.stat.ee/en"), ("Ministry of Finance of Estonia", "https://www.fin.ee/en")],
            "Cross-check: Statistics Estonia and the Ministry of Finance publish the same EDP debt that is reported to Eurostat.",
            ""),
 "latvia": ("Latvia", "LV", "LVA", "EUR", "€", "euros",
            [("Treasury of Latvia, Debt management", "https://www.kase.gov.lv/en"), ("Official statistics of Latvia", "https://stat.gov.lv/en")],
            "Cross-check: the Treasury of Latvia publishes central government debt; the clock uses the general government total Eurostat compiles from the national accounts.",
            ""),
 "luxembourg": ("Luxembourg", "LU", "LUX", "EUR", "€", "euros",
            [("STATEC, Public finances", "https://statistiques.public.lu/en.html"), ("Ministry of Finance of Luxembourg", "https://mfin.gouvernement.lu/en.html")],
            "Cross-check: STATEC publishes the government finance figures that feed the Eurostat table.",
            ""),
 "malta": ("Malta", "MT", "MLT", "EUR", "€", "euros",
            [("National Statistics Office of Malta, Government finance", "https://nso.gov.mt/"), ("Malta Treasury", "https://treasury.gov.mt/")],
            "Cross-check: the National Statistics Office publishes the EDP debt reported to Eurostat.",
            ""),
 "cyprus": ("Cyprus", "CY", "CYP", "EUR", "€", "euros",
            [("Public Debt Management Office, Cyprus", "https://www.mof.gov.cy/"), ("Statistical Service of Cyprus", "https://www.cystat.gov.cy/")],
            "Cross-check: the Public Debt Management Office publishes central government debt. The general government total used here consolidates debt held between government units, so it can be lower than the central government figure.",
            ""),
 "norway": ("Norway", "NO", "NOR", "NOK", "kr", "kroner",
            [("Statistics Norway, Gross public debt, table 11559", "https://www.ssb.no/en/statbank/table/11559"), ("Statistics Norway, General government", "https://www.ssb.no/en/offentlig-sektor")],
            "Cross-check: Statistics Norway table 11559 publishes the same general-government gross debt, face value, in million kroner. The 2026Q2 total matches this Eurostat figure. The stock includes a large loan component, so it moves more than a securities-only measure and sits above the IMF general-government estimate.",
            ""),
}
GENERAL = {"bulgaria", "estonia", "latvia", "luxembourg", "malta", "cyprus", "norway"}
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
    p["iso3"] = a3
    p["title"] = f"{name} National Debt Clock: Live Debt, Official Data"
    if slug in GENERAL:
        sym = p["currency"]["symbol"]
        p["source_tier"] = "harmonized"
        p["headline"] = "general government debt"
        p["headline_long"] = "general government gross debt"
        p["world_measure"] = "General government, gross"
        p["link_label"] = f"general government debt, {sym}"
        p["subject"] = f"The general government of {name}"
        p["hist_label"] = "General government gross debt"
        p["sum_note"] = (f"{name} general government gross debt (Maastricht definition, quarter-end), from Eurostat's quarterly government debt statistics, "
                         "which are compiled from national data.")
        p["scope_note"] = ("This is general government gross debt in the EU Maastricht (excessive deficit procedure) definition, from Eurostat's quarterly table: "
                           "currency and deposits, debt securities and loans of central government, local government and social security funds, at nominal value, consolidated. "
                           f"Figures are in {noun}. Central government is shown below as a fact and is not added on top.")
        c = p["components"][0]
        c["label"] = f"{name} general government gross debt"
        c["short"] = "General government debt"
        c["key"] = "ggdebt"
        c["value"] = 1
        c["as_of"] = "2000-01-01"
        c["prior_value"] = 1
        c["prior_as_of"] = "1999-01-01"
        c["source_name"] = f"Eurostat, Quarterly government debt (gov_10q_ggdebt), general government (S13), Maastricht debt, million {noun}"
        c["source_locator"] = f"geo={a2}, sector S13, na_item GD, unit {'MIO_NAC' if code != 'EUR' else 'MIO_EUR'}; machine-readable: https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10q_ggdebt"
        c["includes"] = "General government gross debt at nominal value in the Maastricht (EDP) definition: currency and deposits, short- and long-term debt securities and loans, consolidated across general government."
        c["facts"] = [{
            "key": "cg", "label": f"{name} central government gross debt (Maastricht)", "value": 1, "kind": "usd", "as_of": "2000-01-01",
            "note": "Central government (Eurostat sector S.1311) in the same table. It is not added to the headline.",
            "source_name": "Eurostat, gov_10q_ggdebt (sector S1311, GD)",
            "source_url": "https://ec.europa.eu/eurostat/databrowser/view/gov_10q_ggdebt/default/table",
            "source_locator": f"geo={a2}, sector S1311, na_item GD, unit {'MIO_NAC' if code != 'EUR' else 'MIO_EUR'}",
        }]
        c["breakdown"] = []
        c["history"] = []
        p["notes"] = [
            "Why Eurostat: it publishes quarterly government debt for EU and EFTA countries on one Maastricht definition, compiled from the figures national statistical institutes and central banks report. The fetcher reads the public API directly.",
            "What this page counts: general government gross debt (sector S.13), not central government alone. The central government figure is a fact and is not added again.",
            "Provisional data: Eurostat flags the latest quarters as provisional and revises them. The page re-bases to each new release.",
            "Source tier: harmonized official dataset (Eurostat gov_10q_ggdebt). As-of date is the quarter-end of the latest published stock.",
            note_x,
        ]
        if code != "EUR":
            p["notes"].insert(4, f"Currency: {name} is published in million {code}. The world page converts to US dollars at the ECB daily reference rate.")
        p["population"]["value"] = 1
        p["population"]["as_of"] = "2000-01-01"
        p["population"]["noun_full"] = f"people in {name}"
    out = os.path.join(ROOT, "places", slug + ".json")
    json.dump(p, open(out, "w"), indent=1, ensure_ascii=False); open(out, "a").write("\n")
    print("wrote", out)
if __name__ == "__main__":
    for s in sys.argv[1:]: main(s)
