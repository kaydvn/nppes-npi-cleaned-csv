import csv, gzip, json, os, tempfile, zipfile, unittest
import nppes_clean as nc

HEADER = list(nc.SRC.values()) + [x for n in range(1, 16) for x in (
    f"Healthcare Provider Taxonomy Code_{n}", f"Healthcare Provider Primary Taxonomy Switch_{n}")]


def row(**kv):
    base = {c: "" for c in HEADER}
    for k, v in kv.items():
        base[nc.SRC.get(k, k)] = v
    return [base[c] for c in HEADER]


ROWS = [
    row(npi="1000000001", entity_type="1", first_name="ANA", last_name="LEE", state="ri",
        zip="029031234", enumeration_date="05/23/2005", **{
            "Healthcare Provider Taxonomy Code_1": "207Q00000X",
            "Healthcare Provider Primary Taxonomy Switch_1": "N",
            "Healthcare Provider Taxonomy Code_2": "208D00000X",
            "Healthcare Provider Primary Taxonomy Switch_2": "Y"}),
    row(npi="1000000002", entity_type="2", org_name="ACME CLINIC", state="TX", zip="75001"),
    row(npi="1000000003", entity_type="", deactivation_date="01/01/2020"),
    row(npi="1000000004", entity_type="1", last_name="X", deactivation_date="01/01/2020",
        reactivation_date="02/01/2021", state="TX"),
]


class T(unittest.TestCase):
    def test_zip_pipeline(self):
        d = tempfile.mkdtemp()
        csvp = os.path.join(d, "npidata_pfile_20050523-20260914.csv")
        with open(csvp, "w", newline="") as f:
            w = csv.writer(f); w.writerow(HEADER); w.writerows(ROWS)
        zp = os.path.join(d, "NPPES.zip")
        with zipfile.ZipFile(zp, "w") as z:
            z.write(csvp, os.path.basename(csvp))
            z.writestr("npidata_pfile_20050523-20260914_fileheader.csv", ",".join(HEADER))
        out = os.path.join(d, "out")
        c = nc.run(zp, out)
        self.assertEqual((c["read"], c["kept"], c["individual"], c["organization"]), (4, 3, 2, 1))
        self.assertEqual(c["by_state"], {"RI": 1, "TX": 2})
        with gzip.open(os.path.join(out, "by_state", "RI.csv.gz"), "rt") as f:
            r = list(csv.DictReader(f))
        self.assertEqual(r[0]["name"], "ANA LEE")
        self.assertEqual(r[0]["primary_taxonomy"], "208D00000X")
        self.assertEqual(r[0]["all_taxonomies"], "207Q00000X|208D00000X")
        self.assertEqual((r[0]["zip5"], r[0]["enumeration_date"]), ("02903", "2005-05-23"))
        self.assertTrue(os.path.exists(os.path.join(out, "summary.json")))

    def test_missing_column(self):
        with self.assertRaises(KeyError):
            nc.build_index(["NPI"])


if __name__ == "__main__":
    unittest.main()
