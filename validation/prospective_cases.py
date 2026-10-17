"""Frozen prospective input contract; no CLI, native launcher, or study runner.

Generation requires an explicitly supplied RNG factory. The provided NumPy
factory rejects the reserved study namespace: execution admission is separate.
Tests exercise planned coordinates using scripted draws, and real PCG64 only
under TEST_MASTER. Every finite value, including out-of-import-bounds values,
is retained without clipping, replacement, positivity conditioning or retries.
"""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import re
import struct

import prospective_ademp as ademp

SCHEMA = "mvs-prospective-case/v1"
PROTOCOL_SHA256 = "75d594af6fd2f249ca044340013ea02d16e8cdbae71aef8c4e16ff6853a324ed"
TEST_MASTER = 56005600  # Engineering-only namespace; never the study master.
FIELDS = frozenset(("schema", "protocol_id", "protocol_sha256", "purpose", "case_id",
                    "cell_index", "replication_zero_based", "native_seed",
                    "entities_per_group", "repeats_per_entity", "value_order",
                    "values_bits", "ordered_binary64_sha256"))
HEX64 = re.compile(r"[0-9a-f]{16}\Z")


def frozen_config():
    raw = (Path(__file__).parent / "prospective-ademp-v1.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("frozen protocol hash mismatch")
    return ademp.loads(raw)


def coordinate(cell_index, replication_zero_based):
    if type(cell_index) is not int or not 0 <= cell_index < 12:
        raise ValueError("invalid cell_index")
    if type(replication_zero_based) is not int or not 0 <= replication_zero_based < 1000:
        raise ValueError("invalid replication_zero_based")
    return [2026101754, 1, 0, cell_index, replication_zero_based]


def case_identity(cell_index, replication_zero_based, purpose="planned_case"):
    coordinate(cell_index, replication_zero_based)
    if type(purpose) is not str or purpose not in ("planned_case", "engineering_literal"):
        raise ValueError("invalid purpose")
    prefix = ademp.PROTOCOL_ID if purpose == "planned_case" else purpose
    return f"{prefix}/C{cell_index:02d}/R{replication_zero_based:04d}"


def encode_values(values):
    result = []
    for value in values:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("values must be finite binary64 numbers")
        result.append(struct.pack(">d", value).hex())
    return result


def decode_values(bits):
    if type(bits) is not list:
        raise ValueError("values_bits must be a list")
    values = []
    for value in bits:
        if type(value) is not str or HEX64.fullmatch(value) is None:
            raise ValueError("invalid canonical binary64 encoding")
        decoded = struct.unpack(">d", bytes.fromhex(value))[0]
        if not math.isfinite(decoded):
            raise ValueError("nonfinite binary64 value")
        values.append(decoded)
    return values


def binary64_hash(values):
    return hashlib.sha256(b"".join(struct.pack("<d", v) for v in values)).hexdigest()


def make_case(values, cell_index, replication_zero_based, purpose="engineering_literal"):
    identity = case_identity(cell_index, replication_zero_based, purpose)
    cell = frozen_config()["cells"][cell_index]
    bits = encode_values(values)
    result = dict(schema=SCHEMA, protocol_id=ademp.PROTOCOL_ID,
                  protocol_sha256=PROTOCOL_SHA256, purpose=purpose, case_id=identity,
                  cell_index=cell_index, replication_zero_based=replication_zero_based,
                  native_seed=1540000000 + 1000 * cell_index + replication_zero_based,
                  entities_per_group=cell["entities_per_group"],
                  repeats_per_entity=cell["repeats_per_entity"],
                  value_order="group_entity_repeat", values_bits=bits,
                  ordered_binary64_sha256=binary64_hash(decode_values(bits)))
    validate_case(result)
    return result


def validate_case(case):
    if type(case) is not dict or set(case) != FIELDS:
        raise ValueError("case fields mismatch")
    cell_index, replication = case["cell_index"], case["replication_zero_based"]
    identity = case_identity(cell_index, replication, case["purpose"])
    cell = frozen_config()["cells"][cell_index]
    fixed = dict(schema=SCHEMA, protocol_id=ademp.PROTOCOL_ID,
                 protocol_sha256=PROTOCOL_SHA256, case_id=identity,
                 native_seed=1540000000 + 1000 * cell_index + replication,
                 entities_per_group=cell["entities_per_group"],
                 repeats_per_entity=cell["repeats_per_entity"],
                 value_order="group_entity_repeat")
    for key, wanted in fixed.items():
        if type(case[key]) is not type(wanted) or case[key] != wanted:
            raise ValueError("case identity mismatch: " + key)
    values = decode_values(case["values_bits"])
    if len(values) != 2 * cell["entities_per_group"] * cell["repeats_per_entity"]:
        raise ValueError("case dimensions mismatch")
    digest = case["ordered_binary64_sha256"]
    if type(digest) is not str or digest != binary64_hash(values):
        raise ValueError("ordered binary64 hash mismatch")
    return values


def loads(raw):
    case = ademp.loads(raw)  # Reject duplicate keys and nonfinite JSON at every depth.
    validate_case(case)
    return case


def numpy_test_rng_factory(coordinates):
    """Real PCG64, pinned version, restricted to explicit engineering namespace."""
    if (type(coordinates) is not list or len(coordinates) != 5
            or any(type(x) is not int for x in coordinates)
            or coordinates[:3] != [TEST_MASTER, 1, 0]):
        raise ValueError("only test-only PCG64 coordinates are admitted")
    coordinate(coordinates[3], coordinates[4])
    import numpy as np
    if np.__version__ != "2.3.5":
        raise ValueError("frozen NumPy 2.3.5 required")
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(coordinates)))


def generate_case(cell_index, replication_zero_based, *, rng_factory,
                  test_namespace=False):
    """Pure one-case draw kernel with injectable factory; no execution authorization.

    Factory receives exact five-coordinate SeedSequence entropy. Scripted factories
    can verify reserved coordinates without constructing any study-seed RNG. The
    explicit test_namespace mode changes only master/purpose, never draw mechanics.
    Factory must expose bit_generator.state and standard_normal/standard_t.
    """
    coordinates = coordinate(cell_index, replication_zero_based)
    if type(test_namespace) is not bool:
        raise ValueError("test_namespace must be bool")
    purpose = "planned_case"
    if test_namespace:
        coordinates[0] = TEST_MASTER
        purpose = "engineering_literal"
    cell = frozen_config()["cells"][cell_index]
    rng = rng_factory(list(coordinates))
    before = deepcopy(rng.bit_generator.state)
    n, m = cell["entities_per_group"], cell["repeats_per_entity"]

    def draw(distribution, count):
        if distribution == "gaussian":
            drawn = rng.standard_normal(count)
            scale = 1.0
        elif distribution == "standardized_t5":
            drawn = rng.standard_t(5, count)
            scale = math.sqrt(3.0 / 5.0)
        else:
            raise ValueError("unknown distribution")
        result = [float(value) * scale for value in drawn]
        if len(result) != count or any(not math.isfinite(v) for v in result):
            raise ValueError("RNG returned invalid draws")
        return result

    # Frozen order: ALL group/entity intercepts, THEN ALL group/entity/repeat residuals.
    intercepts = draw(cell["between_distribution"], 2 * n)
    residuals = draw(cell["within_distribution"], 2 * n * m)
    values = []
    for group in range(2):
        parameters = cell[f"group{group}"]
        for entity in range(n):
            intercept = intercepts[group * n + entity]
            for repeat in range(m):
                residual = residuals[(group * n + entity) * m + repeat]
                values.append(parameters["mean"] + parameters["between_sd"] * intercept
                              + parameters["within_sd"] * residual)
    after = deepcopy(rng.bit_generator.state)
    case = make_case(values, cell_index, replication_zero_based, purpose)
    provenance = dict(data_coordinates=list(coordinates),
                      native_seed_coordinates=[coordinates[0], 1, 1, cell_index, replication_zero_based],
                      native_seed=case["native_seed"], state_before=before, state_after=after,
                      test_namespace=test_namespace,
                      generator_contract="numpy.random.PCG64", numpy_version_contract="2.3.5",
                      actual_rng_type=type(rng).__module__ + "." + type(rng).__qualname__,
                      rng_factory_injected=True)
    return case, provenance
