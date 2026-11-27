"""Static OpenAPI 3 description of the JSON feeds this site already publishes.

GitHub Pages cannot run a server. The file describes the feeds build.py writes.
Nothing here adds a field to those feeds.
"""
import json
import os

ATTRIBUTION = "Source: Every Debt Clock (everydebtclock.com), from U.S. Treasury Debt to the Penny."


def _schema():
    money = {"type": "number", "nullable": True}
    day = {"type": "string", "format": "date", "nullable": True}
    change = {
        "type": "object",
        "nullable": True,
        "properties": {
            "amount": {"type": "number"},
            "from_date": {"type": "string", "format": "date"},
            "from_value": {"type": "number"},
        },
    }
    days_est = {
        "type": "object",
        "nullable": True,
        "description": "Estimate, not a Treasury forecast and not an X-date. Null unless the limit status is in_force and the 90-day slope is positive.",
        "properties": {
            "days": {"type": "number"},
            "projected_date": {"type": "string", "format": "date"},
            "per_day": {"type": "number"},
            "from_date": {"type": "string", "format": "date"},
            "method": {"type": "string"},
        },
    }
    return {
        "Daily": {
            "type": "object",
            "required": ["schema_version", "site_url"],
            "properties": {
                "schema_version": {"type": "integer", "enum": [2]},
                "as_of": {"type": "string", "description": "Page build time, America/Chicago offset."},
                "fetched_at": {"type": "string", "nullable": True, "description": "When the Treasury rows were pulled, America/Chicago offset."},
                "treasury_record_date": day,
                "total_debt_official": money,
                "total_debt_projected_now": {"type": "number", "nullable": True},
                "change_1d_official": change,
                "change_7d_official": change,
                "change_30d_official": change,
                "avg_daily_change_90d": {
                    "type": "object", "nullable": True,
                    "properties": {
                        "amount_per_day": {"type": "number"},
                        "from_date": {"type": "string"},
                        "to_date": {"type": "string"},
                        "method": {"type": "string"},
                    },
                },
                "per_second_rate": money,
                "held_at_debt_limit": {"type": "boolean"},
                "per_second_rate_method": {"type": "string", "nullable": True},
                "clock_daily_change_90d": {
                    "type": "object", "nullable": True,
                    "properties": {
                        "amount_per_day": {"type": "number"},
                        "per_second": {"type": "number"},
                        "from_date": {"type": "string", "nullable": True},
                        "to_date": {"type": "string", "nullable": True},
                        "method": {"type": "string"},
                    },
                },
                "debt_per_person_official": money,
                "census_population_official": {"type": "integer", "nullable": True},
                "census_population_vintage": {"type": "string", "nullable": True},
                "census_population_date": day,
                "debt_per_person_projected_now": money,
                "population_projected_now": {"type": "number", "nullable": True},
                "debt_per_household_official": money,
                "debt_per_household_projected_now": money,
                "households_official": {"type": "integer", "nullable": True},
                "households_source": {"type": "string", "nullable": True},
                "per_person_basis": {"type": "string"},
                "displayed_per_person": {"type": "string", "description": "Which per-person field the site displays. Currently debt_per_person_official."},
                "displayed_per_person_note": {"type": "string"},
                "stale": {"type": "boolean"},
                "source_url": {"type": "string"},
                "source_api": {"type": "string"},
                "site_url": {"type": "string"},
                "debt_subject_to_limit": money,
                "statutory_limit": {"type": "number", "nullable": True, "description": "Null unless debt_limit_reported_status is in_force."},
                "dts_record_date": day,
                "debt_limit_headroom": {"type": "number", "nullable": True},
                "debt_limit_reported_status": {
                    "type": "string", "nullable": True,
                    "description": "in_force, suspended, unreported, or ambiguous. Null when Table III-C is not in the build.",
                },
                "days_to_limit_estimate": days_est,
                "extraordinary_measures": {
                    "type": "string", "nullable": True,
                    "description": "Label recorded from Treasury's debt-limit page. Absent or null means the feed does not say.",
                },
            },
        },
        "Place": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "name": {"type": "string"},
                "kind": {"type": "string", "enum": ["state", "country"]},
                "country": {"type": "string", "nullable": True},
                "region_code": {"type": "string", "nullable": True},
                "demonym": {"type": "string"},
                "label": {"type": "string"},
                "currency": {"type": "string"},
                "sym": {"type": "string"},
                "frequency": {"type": "string"},
                "base": {"type": "number"},
                "base_date": {"type": "string"},
                "t0": {"type": "number"},
                "rate": {"type": "number", "description": "Per second. Zero means the official figure is not projected."},
                "population": {"type": "number"},
                "publisher": {"type": "string"},
                "url": {"type": "string", "description": "Path relative to the site root."},
            },
        },
        "SearchHit": {
            "type": "object",
            "properties": {
                "n": {"type": "string", "description": "Name."},
                "u": {"type": "string", "description": "URL relative to the site root."},
                "k": {"type": "string"},
                "a": {"type": "string", "description": "Extra search words."},
            },
        },
        "WorldCountry": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "name": {"type": "string"},
                "iso3": {"type": "string"},
                "tier": {"type": "string", "enum": ["official", "harmonized", "imf"]},
                "currency": {"type": "string"},
                "debt_local": {"type": "number"},
                "as_of": {"type": "string"},
                "measure": {"type": "string"},
                "usd_per_unit": {"type": "number"},
                "fx_date": {"type": "string"},
                "fx_source": {"type": "string"},
                "debt_usd": {"type": "number"},
                "debt_to_gdp": {"type": "number", "nullable": True},
                "share_pct": {"type": "number"},
                "population": {"type": "number", "nullable": True},
                "trend_usd_per_sec": {"type": "number"},
                "trend": {"type": "string", "nullable": True},
                "projected_usd": {"type": "number"},
                "below_anchor_reason": {"type": "string"},
                "source": {"type": "string"},
                "source_url": {"type": "string"},
                "imf_debt_2026_usd": {"type": "number", "nullable": True},
                "url": {"type": "string"},
            },
        },
        "WealthFund": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "name": {"type": "string"},
                "country": {"type": "string"},
                "rank_by_assets": {"type": "integer"},
                "rank_global_swf": {"type": "integer", "nullable": True},
                "assets_usd": {"type": "number"},
                "assets_basis": {"type": "string"},
                "assets_as_of": {"type": "string"},
                "assets_local": {"type": "number", "nullable": True},
                "assets_source": {"type": "string"},
                "population": {"type": "number"},
                "population_as_of": {"type": "string"},
                "population_source": {"type": "string"},
                "assets_per_person_usd": {"type": "number"},
                "disclosure": {"type": "string"},
                "url": {"type": "string"},
                "detail": {"type": "string"},
            },
        },
    }


def document(site):
    site = site.rstrip("/")
    free = "Free. No API key and no account. " + ATTRIBUTION
    def op(summary, schema, text=False):
        content = "text/plain" if text else "application/json"
        body = {"type": "string"} if text else {"$ref": f"#/components/schemas/{schema}"}
        return {
            "get": {
                "operationId": schema.lower() if not text else "dailytext",
                "summary": summary,
                "responses": {"200": {"description": summary, "content": {content: {"schema": body}}}},
            }
        }
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Every Debt Clock feeds",
            "version": "1.0.0",
            "description": (
                "Static JSON and text feeds published by Every Debt Clock (everydebtclock.com). "
                "The site is a static build. These URLs are files, not a query API. "
                + free + " "
                "State, country, world, and wealth rows name their own official source in the payload. "
                "Null means that input was not available. Do not treat a null as zero."
            ),
            "contact": {"email": "hello@everydebtclock.com", "url": site + "/contact/"},
            "license": {"name": "Free to use with attribution", "url": site + "/terms/"},
            "x-attribution": ATTRIBUTION,
        },
        "servers": [{"url": site}],
        "paths": {
            "/api/daily.json": op("Latest official US total, changes, and debt-limit fields.", "Daily"),
            "/api/daily.txt": op("The same US total as one plain-English line.", "DailyText", text=True),
            "/api/places.json": op("State and country clocks.", "Places"),
            "/api/search.json": op("Names for the on-site search box.", "Search"),
            "/api/world.json": op("World Debt Clock rows, with source tier and as-of date.", "World"),
            "/api/world_government_debt.json": op("IMF general-government estimate for the same economies.", "WorldGovernment"),
            "/api/wealth.json": op("Sovereign wealth fund ranking.", "Wealth"),
        },
        "components": {
            "schemas": {
                **_schema(),
                "DailyText": {"type": "string"},
                "Places": {
                    "type": "object",
                    "properties": {
                        "_doc": {"type": "string"},
                        "generated": {"type": "string"},
                        "default": {"type": "string"},
                        "hub": {"type": "string"},
                        "hub_label": {"type": "string"},
                        "places": {"type": "array", "items": {"$ref": "#/components/schemas/Place"}},
                    },
                },
                "Search": {
                    "type": "object",
                    "properties": {
                        "_doc": {"type": "string"},
                        "places": {"type": "array", "items": {"$ref": "#/components/schemas/SearchHit"}},
                    },
                },
                "World": {
                    "type": "object",
                    "properties": {
                        "_doc": {"type": "string"},
                        "generated": {"type": "string"},
                        "url": {"type": "string"},
                        "countries_count": {"type": "integer"},
                        "counts": {"type": "object"},
                        "total_latest_usd": {"type": "number"},
                        "total_projected_now_usd": {"type": "number"},
                        "rate_usd_per_sec": {"type": "number"},
                        "anchor_method": {"type": "string"},
                        "imf_panel_2026_usd": {"type": "number", "nullable": True},
                        "gdp_coverage": {"type": "object", "nullable": True},
                        "fx": {"type": "object"},
                        "not_converted": {"type": "array", "items": {"type": "object"}},
                        "gap_vs_imf_usd": {"type": "number", "nullable": True},
                        "review_over_25pct": {"type": "array", "items": {"type": "object"}},
                        "gap_drivers": {"type": "array", "items": {"type": "object"}},
                        "kept_on_imf": {"type": "array", "items": {"type": "object"}},
                        "countries": {"type": "array", "items": {"$ref": "#/components/schemas/WorldCountry"}},
                    },
                },
                "WorldGovernment": {
                    "type": "object",
                    "description": "IMF World Economic Outlook general government gross debt. Not the Treasury US total.",
                    "properties": {
                        "_doc": {"type": "string"},
                        "generated": {"type": "string"},
                        "url": {"type": "string"},
                        "vintage": {"type": "string"},
                        "source": {"type": "string"},
                        "source_url": {"type": "string"},
                        "panel_count": {"type": "integer"},
                        "panel_2026_usd": {"type": "number"},
                        "panel_2025_usd": {"type": "number"},
                        "projected_now_usd": {"type": "number"},
                        "rate_usd_per_sec": {"type": "number"},
                        "economies": {"type": "array", "items": {"type": "object"}},
                    },
                },
                "Wealth": {
                    "type": "object",
                    "properties": {
                        "_doc": {"type": "string"},
                        "ranking_source": {"type": "string"},
                        "funds": {"type": "array", "items": {"$ref": "#/components/schemas/WealthFund"}},
                    },
                },
            }
        },
    }


def plugin(site):
    site = site.rstrip("/")
    return {
        "schema_version": "v1",
        "name_for_human": "Every Debt Clock",
        "name_for_model": "every_debt_clock",
        "description_for_human": "Official US, state, country, and wealth-fund debt figures.",
        "description_for_model": (
            "Read the free static JSON feeds on everydebtclock.com. No authentication. "
            "Quote the attribution string: " + ATTRIBUTION + " "
            "The publisher is Every Debt Clock, not usdebtclock.org and not us-debt-clock.com. "
            "Null fields are missing inputs, not zero."
        ),
        "auth": {"type": "none"},
        "api": {"type": "openapi", "url": site + "/openapi.json", "is_user_authenticated": False},
        "logo_url": site + "/icon-512.png",
        "contact_email": "hello@everydebtclock.com",
        "legal_info_url": site + "/terms/",
    }


def write(root, site):
    spec = document(site)
    if spec["openapi"].split(".")[0] != "3":
        raise SystemExit("openapi spec is not version 3")
    if spec["info"].get("x-attribution") != ATTRIBUTION:
        raise SystemExit("openapi spec is missing the attribution string")
    text = json.dumps(spec, indent=1) + "\n"
    json.loads(text)
    open(os.path.join(root, "openapi.json"), "w", encoding="utf-8").write(text)
    # /swagger.json is the same document. Crawlers request that name; GitHub Pages has no HTTP redirect.
    open(os.path.join(root, "swagger.json"), "w", encoding="utf-8").write(text)
    folder = os.path.join(root, ".well-known")
    os.makedirs(folder, exist_ok=True)
    plug = plugin(site)
    open(os.path.join(folder, "ai-plugin.json"), "w", encoding="utf-8").write(json.dumps(plug, indent=1) + "\n")
    return spec
