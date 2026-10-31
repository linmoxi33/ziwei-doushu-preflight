import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin", "ziwei-preflight")


def run(payload, suffix=".json", extra=("--json",)):
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as fh:
        fh.write(payload if isinstance(payload, str) else json.dumps(payload))
    try:
        cmd = [sys.executable, BIN] + list(extra or []) + [path]
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p
    finally:
        os.unlink(path)


def codes(p):
    return [f["code"] for f in json.loads(p.stdout)["findings"]]


class CleanInput(unittest.TestCase):
    def test_valid_record_passes(self):
        p = run({"year": 1990, "month": 5, "day": 20, "hour": 5, "gender": "male"})
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["summary"]["errors"], 0)

    def test_warning_only_still_exits_zero(self):
        p = run({"year": 1990, "month": 5, "day": 20, "hour": 5, "gender": "female",
                 "city": "上海市"})
        self.assertEqual(p.returncode, 0)
        self.assertIn("W_CITY_WITHOUT_LONGITUDE", codes(p))


class GenderCoercion(unittest.TestCase):
    def test_uppercase_male_is_coerced(self):
        p = run({"year": 1990, "month": 5, "day": 20, "hour": 5, "gender": "M"})
        self.assertEqual(p.returncode, 1)
        self.assertIn("E_GENDER_COERCED", codes(p))

    def test_missing_gender_is_error(self):
        p = run({"year": 1990, "month": 5, "day": 20, "hour": 5})
        self.assertEqual(p.returncode, 1)
        self.assertIn("E_GENDER_MISSING", codes(p))


class DateAndHour(unittest.TestCase):
    def test_feb_30_rejected(self):
        p = run({"year": 2026, "month": 2, "day": 30, "hour": 2, "gender": "female"})
        self.assertEqual(p.returncode, 1)
        self.assertIn("E_DATE_NOT_EXIST", codes(p))

    def test_non_leap_feb_29_rejected(self):
        p = run({"year": 2025, "month": 2, "day": 29, "hour": 2, "gender": "female"})
        self.assertIn("E_DATE_NOT_EXIST", codes(p))

    def test_clock_hour_23_rejected_as_branch_index(self):
        p = run({"year": 1990, "month": 5, "day": 20, "hour": 23, "gender": "male"})
        self.assertEqual(p.returncode, 1)
        self.assertIn("E_HOUR_RANGE", codes(p))


class Longitude(unittest.TestCase):
    def test_longitude_crossing_branch_is_error(self):
        p = run({"year": 1992, "month": 8, "day": 3, "hour": 6, "gender": "male",
                 "longitude": 87.6,
                 "origInput": {"year": 1992, "month": 8, "day": 3,
                               "clockHour": 11, "clockMinute": 50}})
        self.assertEqual(p.returncode, 1)
        self.assertIn("E_LONGITUDE_CHANGES_BRANCH", codes(p))
        msg = json.loads(p.stdout)["findings"][0]["message"]
        self.assertIn("午时 -> 巳时", msg)

    def test_longitude_without_crossing_is_warning(self):
        p = run({"year": 1992, "month": 8, "day": 3, "hour": 6, "gender": "male",
                 "longitude": 116.4,
                 "origInput": {"year": 1992, "month": 8, "day": 3,
                               "clockHour": 12, "clockMinute": 0}})
        self.assertEqual(p.returncode, 0)
        self.assertIn("W_LONGITUDE_IGNORED", codes(p))

    def test_longitude_out_of_range(self):
        p = run({"year": 1992, "month": 8, "day": 3, "hour": 6, "gender": "male",
                 "longitude": 999})
        self.assertEqual(p.returncode, 1)
        self.assertIn("E_LONGITUDE_RANGE", codes(p))


class DstAndFields(unittest.TestCase):
    def test_dst_window_warning(self):
        p = run({"year": 1990, "month": 6, "day": 1, "hour": 5, "gender": "male",
                 "origInput": {"year": 1990, "month": 6, "day": 1,
                               "clockHour": 10, "clockMinute": 0}})
        self.assertEqual(p.returncode, 0)
        self.assertIn("W_DST_WINDOW", codes(p))

    def test_unknown_field_warning(self):
        p = run({"year": 1990, "month": 5, "day": 20, "hour": 5, "gender": "male",
                 "longtitude": 121.4})
        self.assertEqual(p.returncode, 0)
        self.assertIn("W_UNKNOWN_FIELD", codes(p))


class CliContract(unittest.TestCase):
    def test_json_output_is_parseable_with_summary(self):
        p = run({"year": 2026, "month": 2, "day": 30, "hour": 2, "gender": "female"},
                extra=["--json"])
        doc = json.loads(p.stdout)
        self.assertEqual(doc["summary"]["errors"], 1)
        self.assertEqual(doc["upstream"], "https://github.com/Renhuai123/ziwei-doushu")

    def test_jsonl_input(self):
        p = run('{"year":1990,"month":5,"day":20,"hour":5,"gender":"male"}\n'
                '{"year":1990,"month":5,"day":20,"hour":5,"gender":"x"}\n',
                suffix=".jsonl", extra=["--json"])
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["records"], 2)

    def test_no_arguments_exits_two(self):
        p = subprocess.run([sys.executable, BIN], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

    def test_malformed_json_exits_two(self):
        p = run("{not json")
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
