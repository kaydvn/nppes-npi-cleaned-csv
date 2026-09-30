#!/usr/bin/env python3
"""Stream the NPPES monthly dissemination CSV into a cleaned, slim dataset.

Output (in OUT_DIR):
  npi_active_all.csv.gz          all active NPIs, slim columns
  by_state/<ST>.csv.gz           same rows split by practice-location state
  summary.json                   row counts
Deactivated NPIs (deactivation date set and no reactivation) are dropped.
Stdlib only; memory use is constant (one open gzip writer per state).
"""
import csv, gzip, json, os, sys, zipfile, io

csv.field_size_limit(10**7)

SRC = {
    "npi": "NPI",
    "entity_type": "Entity Type Code",
    "org_name": "Provider Organization Name (Legal Business Name)",
    "last_name": "Provider Last Name (Legal Name)",
    "first_name": "Provider First Name",
    "middle_name": "Provider Middle Name",
    "credential": "Provider Credential Text",
    "gender": "Provider Sex Code",
    "addr1": "Provider First Line Business Practice Location Address",
    "addr2": "Provider Second Line Business Practice Location Address",
    "city": "Provider Business Practice Location Address City Name",
    "state": "Provider Business Practice Location Address State Name",
    "zip": "Provider Business Practice Location Address Postal Code",
    "phone": "Provider Business Practice Location Address Telephone Number",
    "enumeration_date": "Provider Enumeration Date",
    "last_update": "Last Update Date",
    "deactivation_date": "NPI Deactivation Date",
    "reactivation_date": "NPI Reactivation Date",
}
GENDER_ALT = "Provider Gender Code"  # older files
# 50 states, DC, territories and military mail codes; anything else goes to OTHER
US_STATES = set("""AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS
MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC
PR GU VI AS MP FM MH PW AA AE AP""".split())
OUT_COLS = ["npi", "entity_type", "name", "org_name", "last_name", "first_name",
            "middle_name", "credential", "gender", "primary_taxonomy",
            "all_taxonomies", "addr1", "addr2", "city", "state", "zip5", "zip",
            "phone", "enumeration_date", "last_update"]


def iso(d):
    # NPPES dates are MM/DD/YYYY
    d = d.strip()
    if len(d) == 10 and d[2] == "/" and d[5] == "/":
        return f"{d[6:]}-{d[:2]}-{d[3:5]}"
    return d


def build_index(header):
    pos = {h: i for i, h in enumerate(header)}
    idx = {}
    for k, col in SRC.items():
        if col in pos:
            idx[k] = pos[col]
        elif k == "gender" and GENDER_ALT in pos:
            idx[k] = pos[GENDER_ALT]
        else:
            raise KeyError(f"missing column: {col}")
    tax = []
    for n in range(1, 16):
        c = pos.get(f"Healthcare Provider Taxonomy Code_{n}")
        s = pos.get(f"Healthcare Provider Primary Taxonomy Switch_{n}")
        if c is not None:
            tax.append((c, s))
    return idx, tax


def transform(row, idx, tax):
    g = lambda k: row[idx[k]].strip() if idx[k] < len(row) else ""
    if g("deactivation_date") and not g("reactivation_date"):
        return None
    et = g("entity_type")
    if et not in ("1", "2"):
        return None  # blank rows for deactivated records
    codes, primary = [], ""
    for c, s in tax:
        code = row[c].strip() if c < len(row) else ""
        if code and code not in codes:
            codes.append(code)
            if s is not None and s < len(row) and row[s].strip() == "Y":
                primary = code
    if not primary and codes:
        primary = codes[0]
    if et == "1":
        name = " ".join(x for x in (g("first_name"), g("middle_name"), g("last_name")) if x)
    else:
        name = g("org_name")
    z = g("zip")
    return [g("npi"), "individual" if et == "1" else "organization", name,
            g("org_name"), g("last_name"), g("first_name"), g("middle_name"),
            g("credential"), g("gender"), primary, "|".join(codes),
            g("addr1"), g("addr2"), g("city"), g("state").upper(), z[:5], z,
            g("phone"), iso(g("enumeration_date")), iso(g("last_update"))]


def open_source(path):
    if path.endswith(".zip"):
        zf = zipfile.ZipFile(path)
        name = next(n for n in zf.namelist()
                    if n.startswith("npidata_pfile_") and n.endswith(".csv")
                    and "fileheader" not in n.lower())
        return io.TextIOWrapper(zf.open(name), encoding="utf-8", errors="replace", newline="")
    return open(path, encoding="utf-8", errors="replace", newline="")


def gz_writer(path):
    f = gzip.open(path, "wt", encoding="utf-8", newline="", compresslevel=6)
    w = csv.writer(f)
    w.writerow(OUT_COLS)
    return f, w


def run(src, out_dir):
    os.makedirs(os.path.join(out_dir, "by_state"), exist_ok=True)
    counts = {"read": 0, "kept": 0, "individual": 0, "organization": 0, "by_state": {}}
    allf, allw = gz_writer(os.path.join(out_dir, "npi_active_all.csv.gz"))
    states = {}
    with open_source(src) as fh:
        r = csv.reader(fh)
        idx, tax = build_index(next(r))
        for row in r:
            counts["read"] += 1
            out = transform(row, idx, tax)
            if out is None:
                continue
            counts["kept"] += 1
            counts[out[1]] += 1
            allw.writerow(out)
            st = out[14] if out[14] in US_STATES else "OTHER"
            if st not in states:
                states[st] = gz_writer(os.path.join(out_dir, "by_state", f"{st}.csv.gz"))
            states[st][1].writerow(out)
            counts["by_state"][st] = counts["by_state"].get(st, 0) + 1
    allf.close()
    for f, _ in states.values():
        f.close()
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(counts, f, indent=1, sort_keys=True)
    return counts


if __name__ == "__main__":
    c = run(sys.argv[1], sys.argv[2])
    print(json.dumps({k: v for k, v in c.items() if k != "by_state"}))
