"""Zip/city to TDU (utility) lookup for the Austin region.

Maps a Texas zip code or city name to its Transmission and Distribution
Utility (TDU), and gives the Base offer status for that TDU.

Four statuses (TDU_STATUS, plus mixed per zip):
  energy_and_backup - competitive ERCOT area. Base can be the retail
                      electric provider, with or without a battery.
  backup_only       - the utility stays the provider. Base installs a
                      battery only ("Backup Only" plan). Austin Energy is
                      in this group since the 2026-07-15 launch.
  not_served        - no Base offer found for this TDU.
  mixed             - per zip, not per TDU. Power to Choose shows a
                      competitive TDU in part of the zip, and a muni or
                      co-op (or Austin Energy) serves the rest. The row's
                      mixed_with field names the other part.

Each TDU row has its own confidence and source. A zip row also has its own
confidence (for the zip -> TDU mapping). Both apply.

Austin Energy evidence (checked 2026-09-26):
  - Austin Energy news release, 2026-05-19: 40 MW of residential Base
    batteries across the Austin Energy service territory.
    https://austinenergy.com/about/news/news-releases/2026/Austin-Energy-expands-local-battery-storage-to-support-reliable-affordable-power
  - Base launch release (Yahoo Finance copy), 2026-07-15: customers "will
    be billed at their normal Austin Energy rates"; $695 install, $19/mo;
    "Capacity is limited."
    https://finance.yahoo.com/energy/articles/power-brings-affordable-home-backup-110000290.html
  - Base landing page: https://www.basepowercompany.com/austinenergy
  - Base home page lists "Backup Only -- Get home backup with your existing
    utility, only available in select areas" (faq/corpus/home.md).
  - City of Austin permits, Aug-Sep 2026: about 300 Base backup battery
    permits ("BASE: Installing a backup battery system and additional
    meter socket").

Coverage: Travis, Williamson, Hays, and Bastrop counties (greater Austin).
This is NOT a full 120-zip table. It covers the 59 zips in
data/ptc_tdu.json, each tagged with a confidence level.
Confirm any row before using it for a real customer decision -- the
authoritative live source is the zip lookup at https://www.powertochoose.org.

Sources checked (2026-09-26):
  - PUCT service area maps: https://www.puc.texas.gov/industry/maps/
    (fetch blocked by a paywall/402 in this session, not used directly)
  - Oncor service area (Wikipedia, confirms Round Rock is Oncor):
    https://en.wikipedia.org/wiki/Oncor_Electric_Delivery
  - Power to Choose API, fetched 2026-09-26 for every zip in ZIP_TABLE
    (data/ptc_tdu.json): http://api.powertochoose.org/api/PowerToChoose/plans?zip_code=<zip>
    plans > 0 names the competitive TDU in some part of the zip; 0 plans
    means no competitive retail anywhere in the zip.
  - PEC and Bluebonnet official service-area pages did not resolve in this
    session (DNS / 404 errors). Their rows below are general-knowledge
    estimates, confidence LOW-MEDIUM, and should be re-verified.

Confidence levels:
  HIGH   - confirmed against a fetched source this session
  MEDIUM - well-known public fact, not independently re-verified today
  LOW    - best-guess inference, needs verification before relying on it
"""

import sys

PRICING = "basepowercompany.com/pricing (faq/corpus/pricing.md)"

# tdu -> (status, confidence, source)
TDU_STATUS = {
    "Oncor": ("energy_and_backup", "HIGH",
              PRICING + " lists Energy + backup, Energy only"),
    "CenterPoint Energy": ("energy_and_backup", "HIGH",
                           PRICING + " lists Energy + backup, Energy only"),
    "AEP Texas Central": ("energy_and_backup", "MEDIUM",
                          PRICING + " lists the TDU ('See plans'); plan mix not read"),
    "AEP Texas North": ("energy_and_backup", "MEDIUM",
                        PRICING + " lists the TDU ('See plans'); plan mix not read"),
    "TNMP": ("energy_and_backup", "MEDIUM",
             PRICING + " lists Texas-New Mexico Power ('See plans'); plan mix not read"),
    "Austin Energy": ("backup_only", "HIGH",
                      "Austin Energy release 2026-05-19 + Base launch 2026-07-15: "
                      "battery only, billed at normal Austin Energy rates"),
    "Pedernales Electric Cooperative (PEC)": ("not_served", "MEDIUM",
                                              "not on " + PRICING + "; no partnership found 2026-09-26"),
    "Bluebonnet Electric Cooperative": ("not_served", "MEDIUM",
                                        "not on " + PRICING + "; no partnership found 2026-09-26"),
    "Georgetown Utility Systems": ("not_served", "MEDIUM",
                                   "not on " + PRICING + "; no partnership found 2026-09-26"),
    "San Marcos Electric Utility": ("not_served", "MEDIUM",
                                    "not on " + PRICING + "; no partnership found 2026-09-26"),
}

# True where Base can be the energy provider (kept for older callers).
TDU_ELIGIBLE = {t: v[0] == "energy_and_backup" for t, v in TDU_STATUS.items()}

# zip -> (tdu, city, county, confidence, source_note, mixed_with)
# Built 2026-09-26 from data/ptc_tdu.json (Power to Choose API) and
# data/market.json base_by_zip (City of Austin Base permits). Rules:
#   plans > 0, and the old utility was a muni/co-op or Base has Austin
#     permits -> mixed: tdu = competitive TDU from PTC, mixed_with = the
#     muni/co-op part.
#   plans > 0, no other utility known -> competitive TDU, HIGH.
#   plans == 0, Base Austin permits or City of Austin zip -> Austin Energy.
#   plans == 0 otherwise -> co-op or muni (name from general knowledge).
ZIP_TABLE = {
    '76574': ('Oncor', 'Taylor', 'Williamson', 'HIGH', 'PTC 2026-09-26: 171 plans, TDU Oncor', None),
    '78602': ('Bluebonnet Electric Cooperative', 'Bastrop', 'Bastrop', 'LOW', 'PTC 2026-09-26: 0 plans (no competitive retail, HIGH); utility name from general knowledge', None),
    '78610': ('Pedernales Electric Cooperative (PEC)', 'Buda', 'Hays', 'LOW', 'PTC 2026-09-26: 0 plans (no competitive retail, HIGH); utility name from general knowledge', None),
    '78613': ('Pedernales Electric Cooperative (PEC)', 'Cedar Park', 'Williamson', 'MEDIUM', 'PTC 2026-09-26: 0 plans (no competitive retail, HIGH); utility name from general knowledge', None),
    '78617': ('Austin Energy', 'Del Valle', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 1 Base permit(s) in the Austin feed; Bluebonnet Electric Cooperative also present per old table', None),
    '78621': ('Oncor', 'Elgin', 'Bastrop', 'MEDIUM', 'PTC 2026-09-26: 171 plans, TDU Oncor; mixed: Bluebonnet Electric Cooperative from the old table, general knowledge', 'Bluebonnet Electric Cooperative'),
    '78626': ('Oncor', 'Georgetown', 'Williamson', 'MEDIUM', 'PTC 2026-09-26: 171 plans, TDU Oncor; mixed: Georgetown Utility Systems from the old table, general knowledge', 'Georgetown Utility Systems'),
    '78628': ('Oncor', 'Georgetown', 'Williamson', 'MEDIUM', 'PTC 2026-09-26: 171 plans, TDU Oncor; mixed: Georgetown Utility Systems from the old table, general knowledge', 'Georgetown Utility Systems'),
    '78634': ('Oncor', 'Hutto', 'Williamson', 'HIGH', 'PTC 2026-09-26: 171 plans, TDU Oncor', None),
    '78640': ('Pedernales Electric Cooperative (PEC)', 'Kyle', 'Hays', 'LOW', 'PTC 2026-09-26: 0 plans (no competitive retail, HIGH); utility name from general knowledge', None),
    '78641': ('Pedernales Electric Cooperative (PEC)', 'Leander', 'Williamson', 'MEDIUM', 'PTC 2026-09-26: 0 plans (no competitive retail, HIGH); utility name from general knowledge', None),
    '78653': ('Oncor', 'Manor', 'Travis', 'HIGH', 'PTC 2026-09-26: 171 plans, TDU Oncor; mixed: 1 Base permit(s) in the Austin feed, Bluebonnet Electric Cooperative from the old table, general knowledge', 'Bluebonnet Electric Cooperative + Austin Energy'),
    '78660': ('Oncor', 'Pflugerville', 'Travis', 'HIGH', 'PTC 2026-09-26: 171 plans, TDU Oncor; mixed: 1 Base permit(s) in the Austin feed', 'Austin Energy'),
    '78664': ('Oncor', 'Round Rock', 'Williamson', 'HIGH', 'PTC 2026-09-26: 171 plans, TDU Oncor', None),
    '78665': ('Oncor', 'Round Rock', 'Williamson', 'HIGH', 'PTC 2026-09-26: 171 plans, TDU Oncor', None),
    '78666': ('San Marcos Electric Utility', 'San Marcos', 'Hays', 'LOW', 'PTC 2026-09-26: 0 plans (no competitive retail, HIGH); utility name from general knowledge', None),
    '78681': ('Oncor', 'Round Rock', 'Williamson', 'HIGH', 'PTC 2026-09-26: 171 plans, TDU Oncor', None),
    '78701': ('Austin Energy', 'Austin (downtown)', 'Travis', 'MEDIUM', 'PTC 2026-09-26: 0 plans (no competitive retail); City of Austin zip, no Base permit yet', None),
    '78702': ('Austin Energy', 'Austin (East)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 7 Base permit(s) in the Austin feed', None),
    '78703': ('Austin Energy', 'Austin (Tarrytown)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 14 Base permit(s) in the Austin feed', None),
    '78704': ('Austin Energy', 'Austin (South Congress)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 19 Base permit(s) in the Austin feed', None),
    '78705': ('Austin Energy', 'Austin (West Campus)', 'Travis', 'MEDIUM', 'PTC 2026-09-26: 0 plans (no competitive retail); City of Austin zip, no Base permit yet', None),
    '78721': ('Austin Energy', 'Austin (East MLK)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 1 Base permit(s) in the Austin feed', None),
    '78722': ('Austin Energy', 'Austin (Cherrywood)', 'Travis', 'MEDIUM', 'PTC 2026-09-26: 0 plans (no competitive retail); City of Austin zip, no Base permit yet', None),
    '78723': ('Austin Energy', 'Austin (Windsor Park)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 12 Base permit(s) in the Austin feed', None),
    '78724': ('Austin Energy', 'Austin (Northeast)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 9 Base permit(s) in the Austin feed', None),
    '78725': ('Austin Energy', 'Austin (Southeast)', 'Travis', 'MEDIUM', 'PTC 2026-09-26: 0 plans (no competitive retail); City of Austin zip, no Base permit yet', None),
    '78726': ('Austin Energy', 'Austin (Four Points)', 'Travis', 'MEDIUM', 'PTC 2026-09-26: 0 plans (no competitive retail); City of Austin zip, no Base permit yet', None),
    '78727': ('Oncor', 'Austin (Scofield)', 'Travis', 'HIGH', 'PTC 2026-09-26: 171 plans, TDU Oncor; mixed: 7 Base permit(s) in the Austin feed', 'Austin Energy'),
    '78728': ('Oncor', 'Austin (Wells Branch)', 'Travis', 'HIGH', 'PTC 2026-09-26: 171 plans, TDU Oncor', None),
    '78729': ('Austin Energy', 'Austin (Anderson Mill)', 'Williamson', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 3 Base permit(s) in the Austin feed', None),
    '78730': ('Austin Energy', 'Austin (River Place)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 11 Base permit(s) in the Austin feed', None),
    '78731': ('Austin Energy', 'Austin (Northwest Hills)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 45 Base permit(s) in the Austin feed', None),
    '78732': ('Austin Energy', 'Austin (Steiner Ranch)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 4 Base permit(s) in the Austin feed', None),
    '78733': ('Austin Energy', 'Austin (Rob Roy)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 4 Base permit(s) in the Austin feed', None),
    '78734': ('AEP Texas North', 'Lakeway', 'Travis', 'HIGH', 'PTC 2026-09-26: 167 plans, TDU AEP Texas North; mixed: 3 Base permit(s) in the Austin feed, Pedernales Electric Cooperative (PEC) from the old table, general knowledge', 'Pedernales Electric Cooperative (PEC) + Austin Energy'),
    '78735': ('Austin Energy', 'Austin (Barton Creek)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 13 Base permit(s) in the Austin feed', None),
    '78736': ('Austin Energy', 'Austin (Oak Hill West)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 2 Base permit(s) in the Austin feed', None),
    '78737': ('Pedernales Electric Cooperative (PEC)', 'Austin (Dripping Springs edge)', 'Hays', 'LOW', 'PTC 2026-09-26: 0 plans (no competitive retail, HIGH); utility name from general knowledge', None),
    '78738': ('Austin Energy', 'Bee Cave', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 9 Base permit(s) in the Austin feed', None),
    '78739': ('Austin Energy', 'Austin (Circle C)', 'Travis', 'MEDIUM', 'PTC 2026-09-26: 0 plans (no competitive retail); City of Austin zip, no Base permit yet', None),
    '78741': ('Austin Energy', 'Austin (Riverside)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 2 Base permit(s) in the Austin feed', None),
    '78742': ('Austin Energy', 'Austin (Montopolis)', 'Travis', 'MEDIUM', 'PTC 2026-09-26: 0 plans (no competitive retail); City of Austin zip, no Base permit yet', None),
    '78744': ('Austin Energy', 'Austin (Southeast)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 3 Base permit(s) in the Austin feed', None),
    '78745': ('Austin Energy', 'Austin (South)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 9 Base permit(s) in the Austin feed', None),
    '78746': ('Austin Energy', 'West Lake Hills', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 35 Base permit(s) in the Austin feed', None),
    '78747': ('Austin Energy', 'Austin (Far South)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 9 Base permit(s) in the Austin feed', None),
    '78748': ('Austin Energy', 'Austin (Southpark Meadows)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 5 Base permit(s) in the Austin feed', None),
    '78749': ('Austin Energy', 'Austin (Southwest)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 12 Base permit(s) in the Austin feed', None),
    '78750': ('Oncor', 'Austin (Jollyville)', 'Travis', 'HIGH', 'PTC 2026-09-26: 171 plans, TDU Oncor; mixed: 2 Base permit(s) in the Austin feed', 'Austin Energy'),
    '78751': ('Austin Energy', 'Austin (Hyde Park)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 6 Base permit(s) in the Austin feed', None),
    '78752': ('Austin Energy', 'Austin (North Lamar)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 2 Base permit(s) in the Austin feed', None),
    '78753': ('Austin Energy', 'Austin (North)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 6 Base permit(s) in the Austin feed', None),
    '78754': ('Austin Energy', 'Austin (Harris Branch)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 2 Base permit(s) in the Austin feed', None),
    '78756': ('Austin Energy', 'Austin (Brentwood)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 6 Base permit(s) in the Austin feed', None),
    '78757': ('Austin Energy', 'Austin (Allandale)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 29 Base permit(s) in the Austin feed', None),
    '78758': ('Austin Energy', 'Austin (North Burnet)', 'Travis', 'HIGH', 'PTC 2026-09-26: 0 plans (no competitive retail); 1 Base permit(s) in the Austin feed', None),
    '78759': ('Oncor', 'Austin (Arboretum)', 'Travis', 'HIGH', 'PTC 2026-09-26: 171 plans, TDU Oncor; mixed: 21 Base permit(s) in the Austin feed', 'Austin Energy'),
    '78957': ('Bluebonnet Electric Cooperative', 'Smithville', 'Bastrop', 'LOW', 'PTC 2026-09-26: 0 plans (no competitive retail, HIGH); utility name from general knowledge', None),
}

CITY_TO_ZIP = {
    "round rock": "78665",
    "pflugerville": "78660",
    "hutto": "78634",
    "cedar park": "78613",
    "leander": "78641",
    "georgetown": "78626",
    "taylor": "76574",
    "austin": "78745",
    "del valle": "78617",
    "manor": "78653",
    "lakeway": "78734",
    "west lake hills": "78746",
    "kyle": "78640",
    "buda": "78610",
    "san marcos": "78666",
    "bastrop": "78602",
    "elgin": "78621",
    "smithville": "78957",
}


def zip_status(zip_code):
    """Return (status, tdu_confidence, tdu_source) for a zip in ZIP_TABLE.
    A zip with mixed_with set is "mixed"; else the TDU status."""
    tdu, _, _, _, _, mixed_with = ZIP_TABLE[zip_code]
    status, tdu_conf, tdu_src = TDU_STATUS.get(tdu, ("not_served", "LOW", "TDU not in TDU_STATUS"))
    if mixed_with:
        return "mixed", tdu_conf, f"{tdu_src}; rest of zip: {mixed_with}"
    return status, tdu_conf, tdu_src


def lookup(zip_or_city):
    """Look up TDU info by zip code or city name.

    Returns a dict with tdu, city, county, status, eligible, confidence,
    note, tdu_confidence, tdu_source --
    or a dict with error set if not found in the table.
    """
    key = str(zip_or_city).strip()

    zip_code = None
    if key.isdigit():
        zip_code = key
    else:
        zip_code = CITY_TO_ZIP.get(key.lower())

    if zip_code is None or zip_code not in ZIP_TABLE:
        return {
            "input": zip_or_city,
            "error": (
                "not in table -- check https://www.powertochoose.org "
                "zip lookup for the live TDU"
            ),
        }

    tdu, city, county, confidence, note, mixed_with = ZIP_TABLE[zip_code]
    status, tdu_conf, tdu_src = zip_status(zip_code)
    return {
        "input": zip_or_city,
        "zip": zip_code,
        "city": city,
        "county": county,
        "tdu": tdu,
        "mixed_with": mixed_with,
        "status": status,
        "eligible": status == "energy_and_backup",
        "confidence": confidence,
        "note": note,
        "tdu_confidence": tdu_conf,
        "tdu_source": tdu_src,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m house.territory <zip_or_city>")
        sys.exit(1)

    result = lookup(sys.argv[1])
    if "error" in result:
        print(f"{result['input']}: {result['error']}")
        sys.exit(1)

    print(
        f"{result['input']} -> {result['city']}, {result['county']} County | "
        f"TDU: {result['tdu']}" + (f" + {result['mixed_with']}" if result['mixed_with'] else "") + f" | {result['status']} "
        f"(TDU confidence {result['tdu_confidence']}: {result['tdu_source']}) | "
        f"zip confidence: {result['confidence']} ({result['note']})"
    )


if __name__ == "__main__":
    main()
