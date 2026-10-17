"""Synthetic-only tests: no NIST dataset or native result is read or executed."""
import copy
from decimal import Decimal, Inexact, ROUND_UP, getcontext, localcontext
from fractions import Fraction as F
import hashlib
import json
import math
import unittest

import nist_univariate_reference as oracle


def synthetic(tokens=("1", "2", "3"), mean="2", sd="1", mean_exact=True,
              sd_exact=True, name="Synthetic", newline="\r\n"):
    count = len(tokens)
    lines = [""] * 60
    lines[0] = "File Name: " + name + ".dat"
    lines[2] = "File Format: ASCII"
    lines[3] = "Header: lines 1 to 60 (= 60)"
    lines[4] = "Certified Values: lines 41 to 43 (= 3)"
    lines[5] = "Data: lines 61 to " + str(60 + count) + " (= " + str(count) + ")"
    lines[7] = "Dataset Name: " + name + " (Synthetic test only)"
    lines[18] = "Stat Category: Univariate: Summary Statistics"
    lines[23] = str(count) + " Observations"
    lines[39] = "Certified Values"
    lines[40] = "Sample Mean ybar: " + mean + (" (exact)" if mean_exact else "")
    lines[41] = "Sample Standard Deviation (denom. = n-1) s: " + sd + (" (exact)" if sd_exact else "")
    lines[42] = "Sample Autocorrelation Coefficient (lag 1) r(1): 0"
    lines[44] = "Number of Observations: " + str(count)
    lines[58] = "Data: Y"
    lines[59] = "----------"
    return (newline.join(lines + list(tokens)) + newline).encode("ascii")


def replace_line(raw, line, text):
    lines = raw.decode("ascii").split("\r\n")
    lines[line - 1] = text
    return "\r\n".join(lines).encode("ascii")


def native(parsed, mean=2.0, sd=1.0):
    return {"id": parsed["id"], "sourceSha256": parsed["sourceSha256"],
            "count": parsed["count"], "mean": mean, "standardDeviation": sd,
            "meanBits": oracle.float_bits(mean), "standardDeviationBits": oracle.float_bits(sd),
            "inputBits": [oracle.float_bits(float(t)) for t in parsed["tokens"]]}


class ParserTests(unittest.TestCase):
    def test_original_bytes_and_decimal_text_preserved(self):
        raw = synthetic((" +1.00", "2e0\t", " 3."), mean="2.000", sd="1.00")
        before = raw[:]
        parsed = oracle.parse_dataset(raw)
        self.assertEqual(raw, before)
        self.assertEqual(parsed["tokens"], ["+1.00", "2e0", "3."])
        self.assertEqual(parsed["sourceSha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(parsed["certified"]["mean"], {"text": "2.000", "exact": True, "line": 41})
        self.assertEqual((parsed["dataLineStart"], parsed["dataLineEnd"], parsed["count"]), (61, 63, 3))

    def test_scientific_notation_exact_markers(self):
        raw = synthetic(("1e-1", ".20", "+3.0E-1"), mean="2.0e-1", sd="1.0E-1")
        parsed = oracle.parse_dataset(raw)
        self.assertTrue(all(f["exact"] for f in parsed["certified"].values()))
        result = oracle.reference_dataset(parsed)
        self.assertTrue(result["certifiedValidation"]["passed"])
        self.assertEqual(result["decimalInput"]["meanRational"], "1/5")
        self.assertEqual(result["decimalInput"]["sampleVarianceRational"], "1/100")

    def test_lf_and_optional_final_newline(self):
        a = oracle.parse_dataset(synthetic(newline="\n"))
        b = oracle.parse_dataset(synthetic(newline="\n").rstrip(b"\n"))
        self.assertEqual(a["tokens"], b["tokens"])
        self.assertNotEqual(a["sourceSha256"], b["sourceSha256"])

    def test_requires_raw_bytes(self):
        for raw in (synthetic().decode(), bytearray(synthetic()), True, None):
            with self.subTest(type=type(raw)), self.assertRaises(ValueError):
                oracle.parse_dataset(raw)

    def test_invalid_encoding_and_controls(self):
        for raw in (synthetic() + b"\xff", synthetic().replace(b"Synthetic", b"S\x00ynthetic"),
                    synthetic().replace(b"\r\n", b"\r", 1), synthetic().replace(b"Synthetic", b"S\vynthetic")):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                oracle.parse_dataset(raw)

    def test_truncated_extra_and_empty_rows(self):
        for raw in (synthetic().rsplit(b"3\r\n", 1)[0], synthetic() + b"4\r\n",
                    synthetic() + b"\r\n", replace_line(synthetic(), 62, "")):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                oracle.parse_dataset(raw)

    def test_bad_numeric_rows(self):
        for token in ("NaN", "nan", "Infinity", "-inf", "1e9999", "1 2", "2,3", "1_000", "0x1p2", "1e", "."):
            with self.subTest(token=token), self.assertRaises(ValueError):
                oracle.parse_dataset(synthetic(("1", token, "3")))

    def test_count_and_ranges(self):
        changes = ((6, "Data: lines 61 to 63 (= 4)"), (6, "Data: lines 61 to 62 (= 2)"),
                   (4, "Header: lines 1 to 59 (= 59)"), (5, "Certified Values: lines 40 to 41 (= 2)"),
                   (45, "Number of Observations: 4"), (24, "4 Observations"),
                   (6, "Data: 61 to 63 (= 3)"), (6, "Data: lines 0 to 2 (= 3)"))
        for line, text in changes:
            with self.subTest(line=line, text=text), self.assertRaises(ValueError):
                oracle.parse_dataset(replace_line(synthetic(), line, text))

    def test_one_observation_rejected(self):
        with self.assertRaises(ValueError):
            oracle.parse_dataset(synthetic(("1",), mean="1", sd="0"))

    def test_duplicate_relevant_headers(self):
        raw = synthetic()
        lines = raw.decode().split("\r\n")
        for source_line in (1, 3, 4, 5, 6, 8, 19, 24, 41, 42, 45, 59):
            with self.subTest(source_line=source_line), self.assertRaises(ValueError):
                oracle.parse_dataset(replace_line(raw, 50, lines[source_line - 1]))

    def test_metadata_and_divisor_malformed(self):
        changes = ((1, "File Name: Other.dat"), (3, "File Format: UTF-8"),
                   (19, "Stat Category: Multivariate"), (59, "Data: X"), (60, "separator"),
                   (41, "Sample Mean ybar: 2 approximately"), (41, "Sample Mean ybar: NaN"),
                   (42, "Sample Standard Deviation (denom. = n) s: 1 (exact)"),
                   (42, "Sample Standard Deviation (denom. = n-1) s: -1 (exact)"))
        for line, text in changes:
            with self.subTest(line=line, text=text), self.assertRaises(ValueError):
                oracle.parse_dataset(replace_line(synthetic(), line, text))

    def test_lowercase_descriptive_mean_not_a_duplicate_certificate(self):
        raw = replace_line(synthetic(), 15, "sample mean = 2 (exact)")
        raw = replace_line(raw, 16, "sample standard deviation = 1 (exact)")
        self.assertEqual(oracle.parse_dataset(raw)["certified"]["mean"]["text"], "2")


class ExactReferenceTests(unittest.TestCase):
    def test_hand_known_fractions(self):
        mean, variance = oracle.exact_moments([F(1, 10), F(1, 5), F(3, 10)])
        self.assertEqual(mean, F(1, 5))
        self.assertEqual(variance, F(1, 100))
        self.assertEqual(oracle.exact_moments([F(1), F(3)]), (F(2), F(2)))

    def test_sample_not_population_variance(self):
        parsed = oracle.parse_dataset(synthetic(("1", "3"), sd="1.414213562373095", sd_exact=False))
        result = oracle.reference_dataset(parsed)
        self.assertEqual(F(result["decimalInput"]["sampleVarianceRational"]), 2)
        self.assertTrue(result["certifiedValidation"]["passed"])
        self.assertNotEqual(F(result["decimalInput"]["sampleVarianceRational"]), 1)

    def test_translation_and_scale(self):
        values = [F(-2), F(1, 2), F(5)]
        m, v = oracle.exact_moments(values)
        scaled_m, scaled_v = oracle.exact_moments([3*x + 10000000 for x in values])
        self.assertEqual(scaled_m, 3*m + 10000000)
        self.assertEqual(scaled_v, 9*v)

    def test_invalid_moment_types(self):
        for values in ([], [F(1)], [1, 2], [True, F(2)], [1.0, 2.0]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                oracle.exact_moments(values)

    def test_exact_certificate_failure_is_not_relaxed(self):
        parsed = oracle.parse_dataset(synthetic(mean="2.000000000000001"))
        result = oracle.reference_dataset(parsed)
        self.assertFalse(result["certifiedValidation"]["passed"])
        self.assertEqual(result["certifiedValidation"]["mean"]["halfQuantumRational"], "0/1")

    def test_rounded_mean_half_quantum_inclusive_boundaries(self):
        parsed = oracle.parse_dataset(synthetic(mean="2.0", mean_exact=False))
        for mean, expected in ((F(39, 20), True), (F(41, 20), True),
                               (F(19499, 10000), False), (F(20501, 10000), False)):
            self.assertEqual(oracle.verify_certificates(parsed, mean, F(1))["mean"]["passed"], expected)

    def test_rounded_sd_squared_boundaries(self):
        parsed = oracle.parse_dataset(synthetic(sd="1.0", sd_exact=False))
        for variance, expected in ((F(19, 20)**2, True), (F(21, 20)**2, True),
                                  (F(19, 20)**2 - F(1, 10**20), False),
                                  (F(21, 20)**2 + F(1, 10**20), False)):
            self.assertEqual(oracle.verify_certificates(parsed, F(2), variance)["standardDeviation"]["passed"], expected)

    def test_exact_sd_checked_by_variance_equality(self):
        parsed = oracle.parse_dataset(synthetic(sd="1.000"))
        self.assertTrue(oracle.verify_certificates(parsed, F(2), F(1))["standardDeviation"]["passed"])
        self.assertFalse(oracle.verify_certificates(parsed, F(2), F(1) + F(1, 10**250))["standardDeviation"]["passed"])

    def test_nonnegative_sd_interval(self):
        parsed = oracle.parse_dataset(synthetic(sd="0", sd_exact=False))
        certificate = oracle.verify_certificates(parsed, F(2), F(0))["standardDeviation"]
        self.assertTrue(certificate["passed"])
        self.assertEqual(certificate["lowerRational"], "0/1")
        self.assertFalse(oracle.verify_certificates(parsed, F(2), F(1))["standardDeviation"]["passed"])

    def test_scientific_published_quantum(self):
        center, bound = oracle.certificate_interval({"text": "1.230e+2", "exact": False})
        self.assertEqual((center, bound), (F(123), F(1, 20)))
        self.assertEqual(oracle.certificate_interval({"text": "1e-3", "exact": False}), (F(1, 1000), F(1, 2000)))

    def test_binary_input_moments_are_separate_and_exact(self):
        parsed = oracle.parse_dataset(synthetic(("0.1", "0.2", "0.3"), mean=".2", sd=".1"))
        reference = oracle.reference_dataset(parsed)
        m, v = oracle.exact_moments([F.from_float(float(t)) for t in parsed["tokens"]])
        self.assertEqual(F(reference["binary64Input"]["meanRational"]), m)
        self.assertEqual(F(reference["binary64Input"]["sampleVarianceRational"]), v)
        self.assertNotEqual(m, F(reference["decimalInput"]["meanRational"]))
        self.assertNotEqual(v, F(reference["decimalInput"]["sampleVarianceRational"]))

    def test_precision_runs_and_consistency_log(self):
        parsed = oracle.parse_dataset(synthetic(("1", "3"), sd="1.414213562373095", sd_exact=False))
        reference = oracle.reference_dataset(parsed)
        for kind in ("decimalInput", "binary64Input"):
            row = reference[kind]
            self.assertEqual([r["precision"] for r in row["precisionRuns"]], [100, 200])
            self.assertTrue(row["precisionConsistency"]["passed"])
            self.assertIn("Inexact", row["precisionRuns"][0]["flags"])
            self.assertGreater(len(row["standardDeviationDecimal200"]), len(row["standardDeviationDecimal100"]))

    def test_reference_independent_of_callers_decimal_context(self):
        parsed = oracle.parse_dataset(synthetic(("1", "3"), sd="1.414213562373095", sd_exact=False))
        reference = oracle.reference_dataset(parsed)
        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_UP
            context.traps[Inexact] = True
            self.assertEqual(oracle.reference_dataset(parsed), reference)

    def test_precision_tolerance_exact_boundary(self):
        self.assertTrue(oracle._precision_check(Decimal("1"), Decimal("1"))["passed"])
        self.assertFalse(oracle._precision_check(Decimal("1"), Decimal("1.0000000000000000001"))["passed"])

    def test_parsed_typed_bool_and_field_rejections(self):
        original = oracle.parse_dataset(synthetic())
        bad_cases = []
        for key, value in (("count", True), ("tokens", ["1", "2"]), ("sourceSha256", "f")):
            bad = copy.deepcopy(original); bad[key] = value; bad_cases.append(bad)
        bad = copy.deepcopy(original); bad["certified"]["mean"]["exact"] = 1; bad_cases.append(bad)
        for bad in bad_cases:
            with self.assertRaises(ValueError): oracle.reference_dataset(bad)


class NativeComparisonTests(unittest.TestCase):
    def setUp(self):
        self.parsed = oracle.parse_dataset(synthetic())
        self.reference = oracle.reference_dataset(self.parsed)
        self.native = native(self.parsed)

    def test_exact_pass_and_zero_error_lre(self):
        result = oracle.compare_native(self.native, self.parsed, self.reference)
        self.assertTrue(result["integrityValidated"])
        self.assertTrue(result["primary"]["passed"])
        for key in ("mean", "standardDeviation"):
            self.assertEqual(result["primary"][key]["logRelativeError"], {"status": "zero_error", "value": None})
        json.dumps(result, allow_nan=False)

    def test_primary_fraction_boundary_and_just_outside(self):
        cert = {"text": "2", "exact": True}
        bound = F(2, 10**10)
        self.assertTrue(oracle._primary_comparison(F(2) + bound, cert, None)["passed"])
        self.assertTrue(oracle._primary_comparison(F(2) - bound, cert, None)["passed"])
        self.assertFalse(oracle._primary_comparison(F(2) + bound + F(1, 10**40), cert, None)["passed"])

    def test_no_absolute_floor_on_small_reference(self):
        result = oracle._primary_comparison(F(1, 10**20) + F(1, 10**29), {"text": "1e-20", "exact": True}, None)
        self.assertFalse(result["passed"])

    def test_no_rounding_allowance_added_to_gate(self):
        cert = {"text": "2", "exact": False}
        self.assertFalse(oracle._primary_comparison(F(2000000001, 10**9), cert, None)["passed"])

    def test_nonzero_native_error_logs_finite_lre(self):
        sample = native(self.parsed, mean=2.0 + 1e-8)
        result = oracle.compare_native(sample, self.parsed, self.reference)
        self.assertFalse(result["primary"]["passed"])
        error = result["primary"]["mean"]
        self.assertEqual(error["logRelativeError"]["status"], "finite")
        expected = F.from_float(sample["mean"]) - 2
        self.assertEqual(F(error["signedErrorRational"]), expected)

    def test_negative_certified_mean_uses_absolute_denominator(self):
        parsed = oracle.parse_dataset(synthetic(("-3", "-2", "-1"), mean="-2"))
        result = oracle.compare_native(native(parsed, mean=-2.0), parsed, oracle.reference_dataset(parsed))
        self.assertTrue(result["primary"]["passed"])

    def test_zero_reference_requires_separate_explicit_contract(self):
        parsed = oracle.parse_dataset(synthetic(("-1", "0", "1"), mean="0"))
        reference = oracle.reference_dataset(parsed)
        case = native(parsed, mean=0.0)
        with self.assertRaisesRegex(ValueError, "zero certified value"):
            oracle.compare_native(case, parsed, reference)
        result = oracle.compare_native(case, parsed, reference, zero_contract="exact")
        self.assertTrue(result["primary"]["passed"])
        self.assertIsNone(result["primary"]["mean"]["relativeErrorRational"])
        self.assertFalse(oracle.compare_native(native(parsed, mean=1e-300), parsed, reference,
                                               zero_contract="exact")["primary"]["passed"])

    def test_zero_sd_and_constant_data(self):
        parsed = oracle.parse_dataset(synthetic(("2", "2", "2"), sd="0"))
        result = oracle.compare_native(native(parsed, sd=0.0), parsed, oracle.reference_dataset(parsed), zero_contract="exact")
        self.assertTrue(result["primary"]["passed"])
        json.dumps(result, allow_nan=False)

    def test_binary_representation_and_algorithm_errors_are_distinct(self):
        parsed = oracle.parse_dataset(synthetic(("0.1", "0.2", "0.3"), mean=".2", sd=".1"))
        reference = oracle.reference_dataset(parsed)
        result = oracle.compare_native(native(parsed, mean=.2, sd=.1), parsed, reference)
        self.assertTrue(result["primary"]["passed"])
        representation = result["decimalToBinary64RepresentationContribution"]
        self.assertFalse(representation["mean"]["exactZeroError"])
        for key in ("mean", "standardDeviation"):
            with localcontext() as context:
                context.prec = 180
                algorithm = Decimal(result["algorithmErrorAgainstBinary64Input"][key]["signedErrorDecimal200"])
                conversion = Decimal(representation[key]["signedErrorDecimal200"])
                total = Decimal(result["totalErrorAgainstDecimalInput"][key]["signedErrorDecimal200"])
                self.assertLess(abs(algorithm + conversion - total), Decimal("1e-180"))

    def test_sqrt_error_rationalization_preserves_tiny_nonzero(self):
        reference = {"meanRational": "1/1", "sampleVarianceRational": str(F(1) + F(1, 10**250))}
        result = oracle._against_exact_moments(F(1), F(1), reference)["standardDeviation"]
        self.assertFalse(result["exactZeroError"])
        self.assertLess(Decimal(result["signedErrorDecimal200"]), 0)
        self.assertEqual(result["logRelativeError"]["status"], "finite")

    def test_provenance_and_typed_bool_rejected(self):
        for key, value in (("id", "Other"), ("sourceSha256", "0"*64), ("count", 4),
                           ("count", True), ("mean", True), ("standardDeviation", False),
                           ("mean", "2"), ("mean", None), ("standardDeviation", float("nan")),
                           ("mean", float("inf"))):
            case = copy.deepcopy(self.native); case[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                oracle.compare_native(case, self.parsed, self.reference)

    def test_input_bits_validation(self):
        for bits in (["3ff0000000000001"] + self.native["inputBits"][1:],
                     self.native["inputBits"][:-1], [True] * 3, ["3FF0000000000000"] * 3,
                     ["0x3ff0000000000000"] * 3, ["7ff0000000000000"] * 3):
            case = copy.deepcopy(self.native); case["inputBits"] = bits
            with self.subTest(bits=bits), self.assertRaises(ValueError):
                oracle.compare_native(case, self.parsed, self.reference)

    def test_output_bits_validation_and_report_consistency(self):
        for value in ("4000000000000001", "7ff8000000000000", "7ff0000000000000", "400000000000000A", 0):
            case = copy.deepcopy(self.native); case["meanBits"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                oracle.compare_native(case, self.parsed, self.reference)

    def test_json_integer_must_equal_binary64_value_exactly(self):
        self.assertEqual(oracle._reported_value(2, oracle.float_bits(2.0)), 2.0)
        with self.assertRaises(ValueError):
            oracle._reported_value(9007199254740993, oracle.float_bits(9007199254740992.0))

    def test_signed_zero_bit_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            oracle._reported_value(0.0, oracle.float_bits(-0.0))

    def test_negative_native_sd_rejected(self):
        with self.assertRaises(ValueError):
            oracle.compare_native(native(self.parsed, sd=-1.0), self.parsed, self.reference)

    def test_failed_reference_checks_are_blockers(self):
        for key in ("certifiedValidation", "decimalInput", "binary64Input"):
            ref = copy.deepcopy(self.reference)
            target = ref[key] if key == "certifiedValidation" else ref[key]["precisionConsistency"]
            target["passed"] = False
            with self.subTest(key=key), self.assertRaises(ValueError):
                oracle.compare_native(self.native, self.parsed, ref)

    def test_reference_identity_inputbits_rejected(self):
        for key, value in (("count", True), ("sourceSha256", "0"*64), ("inputBits", [])):
            ref = copy.deepcopy(self.reference); ref[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                oracle.compare_native(self.native, self.parsed, ref)

    def test_compare_independent_of_callers_decimal_context(self):
        expected = oracle.compare_native(self.native, self.parsed, self.reference)
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_UP
            context.traps[Inexact] = True
            self.assertEqual(oracle.compare_native(self.native, self.parsed, self.reference), expected)


if __name__ == "__main__":
    unittest.main()
