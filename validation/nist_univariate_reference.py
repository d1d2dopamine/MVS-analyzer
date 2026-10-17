#!/usr/bin/env python3
"""Independent, standard-library StRD univariate reference and comparisons.

This module does not execute MVS, fetch data, or change production algorithms.
Original source bytes are hashed before parsing and are never rewritten. Exact
decimal-input moments and binary64-input moments use rational arithmetic. The
100/200-digit square roots and logarithms are descriptive diagnostics only.
Neither a certificate check nor passing this comparison certifies software.
"""
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import math
import re
import struct


SCHEMA = "mvs-nist-univariate-reference/v1"
PRIMARY_RELATIVE_TOLERANCE = Fraction(1, 10**10)
PRECISION_CONSISTENCY_TOLERANCE = Fraction(1, 10**90)
_NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
_NUMERIC = re.compile(_NUMBER + r"\Z")
_BITS = re.compile(r"[0-9a-f]{16}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _decimal(text):
    _require(type(text) is str and _NUMERIC.fullmatch(text) is not None,
             "expected one finite decimal token")
    try:
        value = Decimal(text)
    except (ValueError, ArithmeticError) as exc:
        raise ValueError("invalid decimal token") from exc
    _require(value.is_finite(), "nonfinite decimal token")
    return value


def float_bits(value):
    """Canonical IEEE-754 binary64 bit string; integers/bools are not doubles."""
    _require(type(value) is float and math.isfinite(value), "finite float required")
    return struct.pack(">d", value).hex()


def _token_float(token):
    _decimal(token)
    value = float(token)
    _require(math.isfinite(value), "decimal token overflows binary64")
    return value


def _range(lines, label):
    pattern = re.compile(r"^\s*" + re.escape(label) +
                         r"\s*:\s*lines\s+([0-9]+)\s+to\s+([0-9]+)\s*"
                         r"\(\s*=\s*([0-9]+)\s*\)\s*$")
    candidates = [(i + 1, line) for i, line in enumerate(lines)
                  if re.match(r"^\s*" + re.escape(label) + r"\s*:", line)
                  and (label != "Data" or re.search(r"\blines\b", line))]
    _require(len(candidates) == 1, "missing or duplicate " + label + " line declaration")
    line, text = candidates[0]
    match = pattern.fullmatch(text)
    _require(match is not None, "malformed " + label + " line declaration")
    start, end, count = map(int, match.groups())
    _require(start >= 1 and end >= start and count == end - start + 1,
             "inconsistent " + label + " line declaration")
    return start, end, count, line


def _header(lines, prefix, pattern):
    candidates = [(i + 1, line) for i, line in enumerate(lines)
                  if re.match(r"^\s*" + re.escape(prefix) + r"\b", line)]
    _require(len(candidates) == 1, "missing or duplicate " + prefix + " header")
    number, line = candidates[0]
    match = re.fullmatch(pattern, line)
    _require(match is not None, "malformed " + prefix + " header")
    return match, number


def parse_dataset(raw):
    """Parse unchanged ASCII StRD bytes, without computing sample statistics.

    Declared line ranges, row count, certified-field placement, sample divisor,
    dataset/file identity and duplicate relevant headers are checked strictly.
    Exactly one finite numeric token is required on each declared data line;
    even blank extra lines after the declared data are rejected.
    """
    _require(type(raw) is bytes, "original source must be bytes")
    try:
        source = raw.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("source is not ASCII") from exc
    _require(all(ch in "\t\r\n" or 32 <= ord(ch) <= 126 for ch in source),
             "source contains forbidden control characters")
    _require("\r" not in source.replace("\r\n", ""), "bare CR line ending")
    lines = source.replace("\r\n", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()  # The terminal newline terminates a row, not an extra row.
    hs, he, _, hl = _range(lines, "Header")
    cs, ce, _, cl = _range(lines, "Certified Values")
    ds, de, count, dl = _range(lines, "Data")
    _require(hs == 1 and he == ds - 1 and hs <= cs <= ce <= he,
             "invalid or overlapping header/certificate/data ranges")
    _require(all(hs <= x <= he for x in (hl, cl, dl)), "line declaration outside header")
    _require(count >= 2 and len(lines) == de, "truncated, extra, or insufficient data rows")
    header = lines[:he]
    file_match, _ = _header(header, "File Name",
                           r"\s*File Name\s*:\s*([A-Za-z][A-Za-z0-9_]*)\.dat\s*")
    dataset_id = file_match.group(1)
    _header(header, "File Format", r"\s*File Format\s*:\s*ASCII\s*")
    name_match, _ = _header(header, "Dataset Name",
                           r"\s*Dataset Name\s*:\s*([A-Za-z][A-Za-z0-9_]*)"
                           r"(?:\s+\([^\r\n]*\))?\s*")
    _require(name_match.group(1) == dataset_id, "dataset/file identity mismatch")
    _header(header, "Stat Category", r"\s*Stat Category\s*:\s*Univariate"
            r"(?:\s*:\s*Summary Statistics)?\s*")
    obs_match, _ = _header(header, "Number of Observations",
                          r"\s*Number of Observations\s*:\s*([0-9]+)\s*")
    _require(int(obs_match.group(1)) == count, "observation count disagrees with declared data")
    secondary_counts = [int(m.group(1)) for line in header
                        if (m := re.fullmatch(r"\s*(?:-->\s*)?([0-9]+)\s+Observations\s*", line))]
    _require(len(secondary_counts) <= 1 and all(x == count for x in secondary_counts),
             "duplicate or inconsistent descriptive observation count")
    _require(ds >= 3 and re.fullmatch(r"\s*Data:\s*Y\s*", lines[ds - 3]) is not None
             and re.fullmatch(r"\s*-+\s*", lines[ds - 2]) is not None,
             "data range lacks expected Data: Y marker and separator")
    _require(sum(bool(re.fullmatch(r"\s*Data:\s*Y\s*", x)) for x in header) == 1,
             "duplicate Data: Y marker")
    certified = {}
    specs = (("mean", "Sample Mean", r"Sample Mean\s+ybar"),
             ("standardDeviation", "Sample Standard Deviation",
              r"Sample Standard Deviation\s*\(denom\.\s*=\s*n-1\)\s+s"))
    for key, prefix, label in specs:
        match, line = _header(header, prefix, r"\s*" + label + r"\s*:\s*(" +
                              _NUMBER + r")\s*(\(exact\))?\s*")
        _require(cs <= line <= ce, "certified field outside declared certified lines")
        text = match.group(1)
        value = _decimal(text)
        if key == "standardDeviation":
            _require(value >= 0, "negative certified standard deviation")
        certified[key] = {"text": text, "exact": match.group(2) is not None, "line": line}
    tokens = []
    for line_number in range(ds, de + 1):
        token = lines[line_number - 1].strip(" \t")
        _token_float(token)
        tokens.append(token)
    return {"schema": SCHEMA, "id": dataset_id, "fileName": dataset_id + ".dat",
            "sourceSha256": hashlib.sha256(raw).hexdigest(), "count": count,
            "dataLineStart": ds, "dataLineEnd": de, "tokens": tokens,
            "certified": certified}


def _validate_parsed(parsed):
    _require(type(parsed) is dict and parsed.get("schema") == SCHEMA, "invalid parsed schema")
    _require(type(parsed.get("id")) is str and bool(parsed["id"]), "invalid parsed id")
    _require(type(parsed.get("sourceSha256")) is str and
             _SHA.fullmatch(parsed["sourceSha256"]) is not None, "invalid source hash")
    count = parsed.get("count")
    _require(type(count) is int and count >= 2, "integer count >= 2 required")
    tokens = parsed.get("tokens")
    _require(type(tokens) is list and len(tokens) == count, "parsed token count mismatch")
    for token in tokens:
        _token_float(token)
    cert = parsed.get("certified")
    _require(type(cert) is dict and set(cert) == {"mean", "standardDeviation"},
             "invalid certified fields")
    for key, field in cert.items():
        _require(type(field) is dict and type(field.get("exact")) is bool,
                 "certified exact flag must be bool")
        value = _decimal(field.get("text"))
        _require(key != "standardDeviation" or value >= 0, "negative certified SD")


def exact_moments(values):
    """Exact mean and n-1 sample variance, using a two-pass rational formula."""
    values = tuple(values)
    _require(len(values) >= 2 and all(type(x) is Fraction for x in values),
             "at least two Fraction observations required")
    mean = sum(values, Fraction(0)) / len(values)
    variance = sum(((x - mean)**2 for x in values), Fraction(0)) / (len(values) - 1)
    return mean, variance


def _rational(value):
    return str(value.numerator) + "/" + str(value.denominator)


def _context(precision):
    # Explicit fresh contexts make the oracle independent of caller rounding,
    # precision, traps, and previously raised Decimal flags.
    return Context(prec=precision, rounding=ROUND_HALF_EVEN)


def _as_decimal(value):
    return Decimal(value.numerator) / Decimal(value.denominator)


def _decimal_at(value, precision=200):
    with localcontext(_context(precision)):
        return _as_decimal(value)


def _precision_check(low, high):
    difference = abs(Fraction(low) - Fraction(high))
    bound = PRECISION_CONSISTENCY_TOLERANCE * max(Fraction(1), abs(Fraction(high)))
    return {"passed": difference <= bound, "absoluteDifference": str(_decimal_at(difference)),
            "allowedDifference": str(_decimal_at(bound)),
            "rule": "abs(ref100-ref200) <= 1e-90 * max(1,abs(ref200))"}


def _moment_reference(values):
    mean, variance = exact_moments(values)
    out = {"meanRational": _rational(mean), "sampleVarianceRational": _rational(variance),
           "divisor": "n-1", "precisionRuns": []}
    for precision in (100, 200):
        with localcontext(_context(precision)) as ctx:
            decimal_mean = _as_decimal(mean)
            decimal_variance = _as_decimal(variance)
            sd = decimal_variance.sqrt()
            out["meanDecimal" + str(precision)] = str(decimal_mean)
            out["sampleVarianceDecimal" + str(precision)] = str(decimal_variance)
            out["standardDeviationDecimal" + str(precision)] = str(sd)
            out["precisionRuns"].append({"precision": precision, "rounding": "ROUND_HALF_EVEN",
                                         "flags": sorted(signal.__name__ for signal, raised
                                                         in ctx.flags.items() if raised)})
    checks = {key: _precision_check(Decimal(out[key + "Decimal100"]),
                                   Decimal(out[key + "Decimal200"]))
              for key in ("mean", "sampleVariance", "standardDeviation")}
    out["precisionConsistency"] = {"passed": all(x["passed"] for x in checks.values()), **checks}
    return out


def certificate_interval(field):
    """Exact certified value and half of its last published decimal quantum."""
    _require(type(field) is dict and type(field.get("exact")) is bool,
             "certified exact flag must be bool")
    decimal = _decimal(field.get("text"))
    value = Fraction(decimal)
    quantum = Fraction(Decimal((0, (1,), decimal.as_tuple().exponent)))
    half_quantum = Fraction(0) if field["exact"] else quantum / 2
    return value, half_quantum


def verify_certificates(parsed, mean, variance):
    """Check rounded/exact certificates without using a rounded square root."""
    _validate_parsed(parsed)
    _require(type(mean) is Fraction and type(variance) is Fraction and variance >= 0,
             "exact rational moments required")
    result = {}
    for key in ("mean", "standardDeviation"):
        field = parsed["certified"][key]
        center, q = certificate_interval(field)
        low, high = center - q, center + q
        if key == "mean":
            passed = low <= mean <= high
            details = {"referenceRational": _rational(mean), "comparison": "mean interval"}
        else:
            low = max(Fraction(0), low)
            passed = low**2 <= variance <= high**2
            details = {"referenceVarianceRational": _rational(variance),
                       "squaredLowerRational": _rational(low**2),
                       "squaredUpperRational": _rational(high**2),
                       "comparison": "variance within squared nonnegative SD interval"}
        result[key] = {"passed": passed, "certifiedText": field["text"], "exact": field["exact"],
                       "halfQuantumRational": _rational(q), "lowerRational": _rational(low),
                       "upperRational": _rational(high), **details}
    return {"passed": all(x["passed"] for x in result.values()), **result}


def reference_dataset(parsed):
    """Compute independent exact decimal and exact parsed-binary64 references."""
    _validate_parsed(parsed)
    decimal_values = [Fraction(_decimal(t)) for t in parsed["tokens"]]
    binary_values = [_token_float(t) for t in parsed["tokens"]]
    decimal_reference = _moment_reference(decimal_values)
    binary_reference = _moment_reference([Fraction.from_float(v) for v in binary_values])
    certificates = verify_certificates(parsed, Fraction(decimal_reference["meanRational"]),
                                      Fraction(decimal_reference["sampleVarianceRational"]))
    return {"schema": SCHEMA, "id": parsed["id"], "sourceSha256": parsed["sourceSha256"],
            "count": parsed["count"], "certifiedValidation": certificates,
            "decimalInput": decimal_reference, "binary64Input": binary_reference,
            "inputBits": [float_bits(v) for v in binary_values]}


def _decode_bits(bits):
    _require(type(bits) is str and _BITS.fullmatch(bits) is not None,
             "binary64 bits must be 16 lowercase hexadecimal digits")
    value = struct.unpack(">d", bytes.fromhex(bits))[0]
    _require(math.isfinite(value), "nonfinite binary64 bit pattern")
    return value


def _reported_value(number, bits):
    _require(type(number) in (int, float), "reported value must be numeric, not bool or string")
    try:
        reported = float(number)
    except (ValueError, OverflowError) as exc:
        raise ValueError("invalid reported number") from exc
    _require(math.isfinite(reported), "nonfinite reported number")
    value = _decode_bits(bits)
    _require(float_bits(reported) == bits, "reported value disagrees with its binary64 bits")
    _require(type(number) is not int or Fraction(number) == Fraction.from_float(value),
             "reported integer is not the exact value of its binary64 bits")
    return value


def _error_fields(signed_error, reference, exact_zero):
    """200-digit decimal diagnostics, never NaN/Infinity JSON values."""
    absolute = abs(signed_error)
    relative = None if reference == 0 else absolute / abs(reference)
    if exact_zero:
        lre = {"status": "zero_error", "value": None}
    elif reference == 0:
        lre = {"status": "zero_reference", "value": None}
    elif relative == 0:
        lre = {"status": "below_diagnostic_precision", "value": None}
    else:
        lre = {"status": "finite", "value": str(-relative.log10())}
    return {"exactZeroError": exact_zero, "signedErrorDecimal200": str(signed_error),
            "absoluteErrorDecimal200": str(absolute),
            "relativeErrorDecimal200": None if relative is None else str(relative),
            "logRelativeError": lre}


def _primary_comparison(value, field, zero_contract):
    certified = Fraction(_decimal(field["text"]))
    error = value - certified
    if certified == 0:
        _require(zero_contract == "exact", "zero certified value requires explicit zero_contract='exact'")
        bound, passed, contract = Fraction(0), error == 0, "explicit zero-reference exact-equality"
    else:
        bound = abs(certified) * PRIMARY_RELATIVE_TOLERANCE
        passed, contract = abs(error) <= bound, "abs(native-certified) <= abs(certified)/10^10"
    with localcontext(_context(200)):
        fields = _error_fields(_as_decimal(error), _as_decimal(certified), error == 0)
    return {"passed": passed, "contract": contract, "certifiedText": field["text"],
            "certifiedRational": _rational(certified), "nativeRational": _rational(value),
            "signedErrorRational": _rational(error), "allowedErrorRational": _rational(bound),
            "relativeErrorRational": None if certified == 0 else _rational(abs(error / certified)),
            **fields}


def _against_exact_moments(native_mean, native_sd, reference):
    mean, variance = Fraction(reference["meanRational"]), Fraction(reference["sampleVarianceRational"])
    with localcontext(_context(200)):
        root = _as_decimal(variance).sqrt()
        mean_error = native_mean - mean
        sd_zero = native_sd >= 0 and native_sd**2 == variance
        # Rationalization retains tiny errors that subtracting two rounded
        # 200-digit roots/values could erase.
        if sd_zero:
            sd_error = Decimal(0)
        elif native_sd >= 0:
            sd_error = _as_decimal(native_sd**2 - variance) / (_as_decimal(native_sd) + root)
        else:
            sd_error = _as_decimal(native_sd) - root
        return {"mean": _error_fields(_as_decimal(mean_error), _as_decimal(mean), mean_error == 0),
                "standardDeviation": _error_fields(sd_error, root, sd_zero)}


def _representation_contribution(decimal_reference, binary_reference):
    dm, bm = (Fraction(ref["meanRational"]) for ref in (decimal_reference, binary_reference))
    dv, bv = (Fraction(ref["sampleVarianceRational"]) for ref in (decimal_reference, binary_reference))
    with localcontext(_context(200)):
        droot, broot = _as_decimal(dv).sqrt(), _as_decimal(bv).sqrt()
        sd_error = Decimal(0) if bv == dv else _as_decimal(bv - dv) / (broot + droot)
        return {"mean": _error_fields(_as_decimal(bm - dm), _as_decimal(dm), bm == dm),
                "standardDeviation": _error_fields(sd_error, droot, bv == dv)}


def compare_native(nativecase, parsed, reference, *, zero_contract=None):
    """Validate native provenance/bits, then apply the exact frozen relative gate.

    No absolute floor, certificate rounding allowance, or diagnostic precision
    tolerance is added to the primary 1e-10 relative bound. Zero certificates
    require a separately supplied explicit exact-equality contract.
    """
    _validate_parsed(parsed)
    _require(zero_contract in (None, "exact"), "unknown zero-reference contract")
    _require(type(nativecase) is dict and type(reference) is dict, "native/reference objects required")
    for key in ("id", "sourceSha256", "count"):
        _require(type(nativecase.get(key)) is type(parsed[key]) and nativecase[key] == parsed[key],
                 "native " + key + " mismatch")
        _require(type(reference.get(key)) is type(parsed[key]) and reference[key] == parsed[key],
                 "reference " + key + " mismatch")
    _require(reference.get("schema") == SCHEMA, "reference schema mismatch")
    _require(reference.get("certifiedValidation", {}).get("passed") is True,
             "certificate verification failed")
    for kind in ("decimalInput", "binary64Input"):
        _require(reference.get(kind, {}).get("precisionConsistency", {}).get("passed") is True,
                 "reference precision consistency failed")
    expected_bits = [float_bits(_token_float(t)) for t in parsed["tokens"]]
    bits = nativecase.get("inputBits")
    _require(type(bits) is list and len(bits) == parsed["count"], "native inputBits count mismatch")
    for actual, expected in zip(bits, expected_bits):
        _decode_bits(actual)
        _require(actual == expected, "native inputBits disagree with decimal-token binary64 conversion")
    _require(reference.get("inputBits") == expected_bits, "reference inputBits mismatch")
    values = {key: Fraction.from_float(_reported_value(nativecase.get(key), nativecase.get(key + "Bits")))
              for key in ("mean", "standardDeviation")}
    _require(values["standardDeviation"] >= 0, "negative native sample standard deviation")
    primary = {key: _primary_comparison(values[key], parsed["certified"][key], zero_contract)
               for key in values}
    return {"schema": SCHEMA, "id": parsed["id"], "sourceSha256": parsed["sourceSha256"],
            "count": parsed["count"], "integrityValidated": True,
            "primary": {"passed": all(x["passed"] for x in primary.values()), **primary},
            "algorithmErrorAgainstBinary64Input": _against_exact_moments(
                values["mean"], values["standardDeviation"], reference["binary64Input"]),
            "totalErrorAgainstDecimalInput": _against_exact_moments(
                values["mean"], values["standardDeviation"], reference["decimalInput"]),
            "decimalToBinary64RepresentationContribution": _representation_contribution(
                reference["decimalInput"], reference["binary64Input"])}
