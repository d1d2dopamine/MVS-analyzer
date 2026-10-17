#!/usr/bin/env python3
"""Validate retained benchmark evidence and render its secondary Russian table.

This offline, standard-library checker does not run benchmarks, create scientific
inputs, call the native engine, or fetch external references. Exit 0 means the
registry is internally consistent with its pinned local sources, not that a
scientific claim is independently validated. Exit 1 means invalid evidence or a
stale committed table; exit 2 is reserved for argparse usage errors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import urlsplit


CURRENT_VERSION = "1.1.0"
HISTORICAL_VERSION = "1.0.0"
VERSION_PATHS = {
    HISTORICAL_VERSION: ("validation/benchmark-suite-v1.json", "docs/BENCHMARK_RESULTS_RU.md"),
    CURRENT_VERSION: ("validation/benchmark-suite-v1.1.json", "docs/BENCHMARK_RESULTS_V1_1_RU.md"),
}
REGISTRY_PATH, TABLE_PATH = VERSION_PATHS[CURRENT_VERSION]
NIST_BENCHMARK_ID = "MVS-NUM-NIST-UNIVARIATE-1.0.0"
NIST_PROTOCOL_PATH = "validation/nist-univariate-protocol-v1.json"
NIST_RESULTS_PATH = "validation/round53-results.json"
CATEGORY_NATURE = {
    "numerical_reference": "numerical_contract",
    "development_simulation": "historical_development",
    "computational_audit": "computational_audit",
    "engineering_contract": "engineering_contract",
    "stability_diagnostic": "historical_development",
}
CATEGORY_LABELS = {
    "numerical_reference": "Численные эталоны",
    "development_simulation": "Разработческие симуляции",
    "computational_audit": "Вычислительный аудит",
    "engineering_contract": "Инженерные контракты",
    "stability_diagnostic": "Диагностика устойчивости",
}
EXECUTION_STATUSES = {
    "completed", "not_run", "technical_failure_with_supplemental_audit",
}
GATE_STATUSES = {
    "historical_no_go", "candidate_no_go", "predeclared_numerical_pass",
    "descriptive_only", "inconclusive", "not_assessed",
}
TRUTHS = {"null", "alternative", "numerical", "not_applicable"}
TOP_FIELDS = {"schema_version", "suite_id", "suite_version", "sources",
              "nist_support", "benchmarks"}
BENCHMARK_FIELDS = {
    "id", "name_en", "version", "category", "nature", "execution_status",
    "gate_status", "retrospective_registration",
    "independent_scientific_validation", "ademp", "methods", "identity",
    "uncertainty_ru", "failures_ru", "stopping_ru", "comparability_ru",
    "conclusion_ru", "observations",
}
OBSERVATION_FIELDS = {
    "label_ru", "reference", "value", "unit", "denominator",
    "denominator_reference", "denominator_note_ru", "interpretation_ru", "truth",
}
ADEMP_FIELDS = {"aims", "data", "estimands", "methods", "performance", "truth"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, required, where):
    require(type(value) is dict, f"{where}: expected an object")
    missing = required - value.keys()
    extra = value.keys() - required
    require(not missing and not extra,
            f"{where}: missing fields {sorted(missing)}; unknown fields {sorted(extra)}")


def string(value, where):
    require(type(value) is str and bool(value.strip()), f"{where}: expected nonempty text")
    require(not any(ord(char) < 32 and char not in "\n\t\r" for char in value),
            f"{where}: invalid control character")
    return value


def identifier(value, where):
    string(value, where)
    require(bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:+-]*", value)),
            f"{where}: expected an English identifier")


def sequence(value, where, nonempty=False):
    require(type(value) is list, f"{where}: expected an array")
    require(not nonempty or bool(value), f"{where}: array must not be empty")
    return value


def choice(value, allowed, where):
    require(type(value) is str and value in allowed,
            f"{where}: unknown value {value!r}")


def positive_integer(value, where):
    require(type(value) is int and value > 0, f"{where}: expected a positive integer")


def finite_json(value, where="JSON"):
    """Reject Python extensions to JSON, including nonfinite nested numbers."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        require(math.isfinite(value), f"{where}: nonfinite number")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            finite_json(item, f"{where}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            require(type(key) is str, f"{where}: non-string object key")
            finite_json(item, f"{where}.{key}")
        return
    raise ValueError(f"{where}: not a JSON value")


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"JSON: duplicate object key {key!r}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"JSON: nonfinite literal {value}")


def read_json(path):
    result = json.loads(path.read_text(encoding="utf-8-sig"),
                        object_pairs_hook=_object, parse_constant=_constant)
    finite_json(result)
    return result


def local_path(root, value, *, must_exist=True):
    """Require a canonical relative POSIX path and containment after symlinks."""
    string(value, "local path")
    require("\\" not in value and ":" not in value and "\x00" not in value,
            f"Unsafe local path: {value!r}")
    parts = value.split("/")
    require(all(part not in ("", ".", "..") for part in parts),
            f"Unsafe local path: {value!r}")
    require(not PurePosixPath(value).is_absolute(), f"Unsafe local path: {value!r}")
    root = Path(root).resolve(strict=True)
    candidate = root.joinpath(*parts)
    resolved = candidate.resolve(strict=must_exist)
    require(resolved.is_relative_to(root), f"Local path escapes root: {value!r}")
    if must_exist:
        require(resolved.is_file(), f"Not a local file: {value!r}")
    return candidate


def sha256(value, where):
    require(type(value) is str and bool(re.fullmatch("[0-9a-f]{64}", value)),
            f"{where}: expected lowercase SHA-256")


def file_reference(root, reference, where, *, extra_fields=frozenset()):
    fields(reference, {"path", "sha256"} | set(extra_fields), where)
    sha256(reference["sha256"], f"{where}.sha256")
    path = local_path(root, reference["path"])
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    require(actual == reference["sha256"], f"{where}: SHA-256 mismatch for {reference['path']}")
    return path


def json_pointer(document, pointer):
    """Resolve RFC 6901 without coercion, negative indexes, or silent omissions."""
    require(type(pointer) is str, "JSON pointer must be a string")
    if pointer == "":
        return document
    require(pointer.startswith("/"), f"Invalid JSON pointer: {pointer!r}")
    current = document
    for raw in pointer[1:].split("/"):
        require(re.search(r"~(?![01])", raw) is None,
                f"Invalid JSON pointer escape: {pointer!r}")
        token = raw.replace("~1", "/").replace("~0", "~")
        if type(current) is dict:
            require(token in current, f"JSON pointer key missing: {pointer!r}")
            current = current[token]
        elif type(current) is list:
            require(bool(re.fullmatch(r"0|[1-9][0-9]*", token)),
                    f"Invalid JSON pointer array index: {pointer!r}")
            index = int(token)
            require(index < len(current), f"JSON pointer index missing: {pointer!r}")
            current = current[index]
        else:
            raise ValueError(f"JSON pointer traverses a scalar: {pointer!r}")
    return current


def typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            typed_equal(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(
            typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def external_url(value, where):
    string(value, where)
    parsed = urlsplit(value)
    require(parsed.scheme == "https" and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None,
            f"{where}: expected an HTTPS reference URL")
    require(not any(char.isspace() for char in value), f"{where}: whitespace in URL")


def unique(value, seen, where):
    require(value not in seen, f"{where}: duplicate identifier {value!r}")
    seen.add(value)


def validate_registry(root, registry, expected_version=None):
    """Validate schema, provenance, typed observations and claim boundaries."""
    root = Path(root).resolve(strict=True)
    finite_json(registry)
    fields(registry, TOP_FIELDS, "registry")
    require(type(registry["schema_version"]) is int and registry["schema_version"] == 1,
            "Unsupported schema_version")
    require(registry["suite_id"] == "MVS-Benchmark-Suite", "Unknown suite_id")
    version = registry["suite_version"]
    choice(version, VERSION_PATHS, "suite_version")
    if expected_version is not None:
        choice(expected_version, VERSION_PATHS, "requested suite version")
        require(version == expected_version,
                f"Suite version/path mismatch: requested {expected_version}, found {version}")
    source_ids = set()
    for source in sequence(registry["sources"], "sources", nonempty=True):
        fields(source, {"id", "role", "url"}, "source")
        identifier(source["id"], "source.id")
        unique(source["id"], source_ids, "sources")
        string(source["role"], "source.role")
        external_url(source["url"], "source.url")
    operations = set()
    for item in sequence(registry["nist_support"], "nist_support", nonempty=True):
        fields(item, {"operation", "status", "source_url", "code_refs", "reason_ru"},
               "NIST mapping")
        string(item["operation"], "NIST operation")
        unique(item["operation"], operations, "nist_support")
        nist_statuses = {"mapped_not_run", "unsupported"}
        if version == CURRENT_VERSION:
            nist_statuses.add("executed_numerical")
        choice(item["status"], nist_statuses, "NIST status")
        external_url(item["source_url"], "NIST source_url")
        string(item["reason_ru"], "NIST reason_ru")
        refs = sequence(item["code_refs"], "NIST code_refs")
        require(item["status"] not in {"mapped_not_run", "executed_numerical"} or bool(refs),
                "Mapped NIST operation requires local code references")
        for ref in refs:
            path = file_reference(root, ref, "NIST code reference", extra_fields={"lines"})
            lines = ref["lines"]
            require(type(lines) is list and len(lines) == 2,
                    "NIST code lines must be [start, end]")
            for line in lines:
                positive_integer(line, "NIST line number")
            line_count = len(path.read_text(encoding="utf-8-sig").splitlines())
            require(lines[0] <= lines[1] <= line_count, "NIST code line range is invalid")
    benchmark_ids = set()
    for benchmark in sequence(registry["benchmarks"], "benchmarks", nonempty=True):
        fields(benchmark, BENCHMARK_FIELDS, "benchmark")
        where = f"benchmark {benchmark['id']}"
        identifier(benchmark["id"], f"{where}.id")
        unique(benchmark["id"], benchmark_ids, "benchmarks")
        string(benchmark["name_en"], f"{where}.name_en")
        require(bool(re.search("[A-Za-z]", benchmark["name_en"]))
                and not re.search("[А-Яа-яЁё]", benchmark["name_en"]),
                f"{where}: name_en must be an English name")
        string(benchmark["version"], f"{where}.version")
        category = benchmark["category"]
        choice(category, CATEGORY_NATURE, f"{where}.category")
        require(benchmark["nature"] == CATEGORY_NATURE[category],
                f"{where}: category/nature claim mismatch")
        execution = benchmark["execution_status"]
        gate = benchmark["gate_status"]
        choice(execution, EXECUTION_STATUSES, f"{where}.execution_status")
        gate_statuses = GATE_STATUSES | ({"predeclared_numerical_fail"} if version == CURRENT_VERSION else set())
        choice(gate, gate_statuses, f"{where}.gate_status")
        require(benchmark["retrospective_registration"] is True,
                f"{where}: registration must remain explicitly retrospective")
        require(benchmark["independent_scientific_validation"] is False,
                f"{where}: retained evidence is not independent scientific validation")
        if gate in {"predeclared_numerical_pass", "predeclared_numerical_fail"}:
            require(category == "numerical_reference" and execution == "completed",
                    f"{where}: numerical gate cannot certify this claim category/status")
        if gate == "historical_no_go":
            require(category == "development_simulation", f"{where}: historical gate category mismatch")
        if gate == "candidate_no_go":
            require(category in {"numerical_reference", "development_simulation", "stability_diagnostic"},
                    f"{where}: candidate gate category mismatch")
        fields(benchmark["ademp"], ADEMP_FIELDS, f"{where}.ademp")
        for key in sorted(ADEMP_FIELDS):
            string(benchmark["ademp"][key], f"{where}.ademp.{key}")
        method_ids = set()
        for method in sequence(benchmark["methods"], f"{where}.methods", nonempty=True):
            fields(method, {"id", "version"}, f"{where}.method")
            identifier(method["id"], f"{where}.method.id")
            unique(method["id"], method_ids, f"{where}.methods")
            string(method["version"], f"{where}.method.version")
        identity = benchmark["identity"]
        fields(identity, {"protocol_id", "protocol_refs", "data_id", "data_hash",
                          "data_limitations_ru"}, f"{where}.identity")
        for key in ("protocol_id", "data_id", "data_limitations_ru"):
            string(identity[key], f"{where}.identity.{key}")
        if identity["data_hash"] is not None:
            sha256(identity["data_hash"], f"{where}.identity.data_hash")
        ref_paths = set()
        for ref in sequence(identity["protocol_refs"], f"{where}.protocol_refs", nonempty=True):
            file_reference(root, ref, f"{where}.protocol reference")
            unique(ref["path"], ref_paths, f"{where}.protocol_refs")
        for key in ("uncertainty_ru", "failures_ru", "stopping_ru", "comparability_ru", "conclusion_ru"):
            string(benchmark[key], f"{where}.{key}")
        observations = sequence(benchmark["observations"], f"{where}.observations")
        if execution == "not_run":
            require(not observations and gate == "not_assessed",
                    f"{where}: not_run must have no observations and gate not_assessed")
        else:
            require(bool(observations), f"{where}: executed evidence requires observations")
        labels = set()
        for observation in observations:
            fields(observation, OBSERVATION_FIELDS, f"{where}.observation")
            for key in ("label_ru", "denominator_note_ru", "interpretation_ru"):
                string(observation[key], f"{where}.observation.{key}")
            unique(observation["label_ru"], labels, f"{where}.observation labels")
            choice(observation["unit"], {"count", "rate", "diagnostic", "text"},
                   f"{where}.observation.unit")
            choice(observation["truth"], TRUTHS, f"{where}.observation.truth")
            denominator = observation["denominator"]
            if denominator is not None:
                positive_integer(denominator, f"{where}.observation.denominator")
                denominator_ref = observation["denominator_reference"]
                denominator_path = file_reference(
                    root, denominator_ref, f"{where}.denominator reference", extra_fields={"pointer"})
                actual_denominator = json_pointer(read_json(denominator_path), denominator_ref["pointer"])
                require(typed_equal(denominator, actual_denominator),
                        f"{where}: typed denominator mismatch at "
                        f"{denominator_ref['path']}#{denominator_ref['pointer']}")
            else:
                require(observation["denominator_reference"] is None,
                        f"{where}: null denominator requires null denominator_reference")
            value = observation["value"]
            if observation["unit"] == "count":
                positive_integer(denominator, f"{where}.count.denominator")
                require(type(value) is int and 0 <= value <= denominator,
                        f"{where}: count must be an integer within its denominator")
            if observation["unit"] == "rate":
                positive_integer(denominator, f"{where}.rate.denominator")
                require(type(value) in (int, float) and 0 <= value <= 1,
                        f"{where}: rate must be a finite number in [0, 1]")
            if observation["unit"] == "text":
                string(value, f"{where}.text.value")
            reference = observation["reference"]
            path = file_reference(root, reference, f"{where}.observation reference",
                                  extra_fields={"pointer"})
            source_value = json_pointer(read_json(path), reference["pointer"])
            require(typed_equal(value, source_value),
                    f"{where}: typed value mismatch at {reference['path']}#{reference['pointer']}")
    executed_nist = any(item["status"] == "executed_numerical" for item in registry["nist_support"])
    nist = next((item for item in registry["benchmarks"] if item["id"] == NIST_BENCHMARK_ID), None)
    if nist is not None:
        require(version == CURRENT_VERSION, "NIST execution entry is unavailable in historical suite 1.0.0")
        require(executed_nist, "NIST execution entry requires executed_numerical support status")
    if executed_nist:
        require(nist is not None, "executed_numerical requires the identified NIST benchmark entry")
        require(nist["version"] == "1.0.0" and nist["category"] == "numerical_reference"
                and nist["execution_status"] == "completed",
                "executed_numerical requires a completed versioned numerical_reference entry")
        require(nist["independent_scientific_validation"] is False,
                "NIST numerical execution is not independent scientific validation")
        references = {ref["path"]: ref for ref in nist["identity"]["protocol_refs"]}
        require({NIST_PROTOCOL_PATH, NIST_RESULTS_PATH}.issubset(references),
                "NIST entry requires pinned protocol and results references")
        require(any(obs["reference"]["path"] == NIST_RESULTS_PATH for obs in nist["observations"]),
                "NIST entry requires source-bound results observations")
        protocol = read_json(local_path(root, NIST_PROTOCOL_PATH))
        result = read_json(local_path(root, NIST_RESULTS_PATH))
        require(type(protocol) is dict and protocol.get("schema") == "mvs-nist-univariate-protocol/v1"
                and protocol.get("id") == NIST_BENCHMARK_ID,
                "NIST protocol schema/identity mismatch")
        require(type(result) is dict and result.get("schema") == "mvs-nist-study-result/v1",
                "NIST results schema mismatch")
        require(result.get("executionStatus") == "completed", "NIST results execution is not completed")
        require(result.get("protocolId") == NIST_BENCHMARK_ID
                and nist["identity"]["protocol_id"] == NIST_BENCHMARK_ID,
                "NIST result/entry protocol identity mismatch")
        passed = result.get("numericalContractPassed")
        require(type(passed) is bool, "NIST results require explicit numericalContractPassed boolean")
        required_gate = "predeclared_numerical_pass" if passed else "predeclared_numerical_fail"
        require(nist["gate_status"] == required_gate, "NIST numerical gate disagrees with retained results")
        names = protocol.get("datasetNames")
        require(type(names) is list and len(names) == 9 and all(type(name) is str for name in names)
                and len(set(names)) == 9, "NIST protocol requires nine identified datasets")
        rows = result.get("results")
        require(type(rows) is list and len(rows) == 9 and all(type(row) is dict for row in rows)
                and [row.get("id") for row in rows] == names,
                "NIST results must retain all nine ordered datasets")
        expected_pairs = {(index, operation) for index in range(9) for operation in ("mean", "standardDeviation")}
        covered_pairs = set()
        for observation in nist["observations"]:
            if observation["reference"]["path"] == NIST_RESULTS_PATH:
                match = re.match(r"^/results/([0-8])/primary/(mean|standardDeviation)(?:/|$)",
                                 observation["reference"]["pointer"])
                if match:
                    covered_pairs.add((int(match.group(1)), match.group(2)))
        require(covered_pairs == expected_pairs,
                "NIST observations must cover all 18 dataset-operation results")
    return registry


def load_registry(root, version=CURRENT_VERSION):
    root = Path(root).resolve(strict=True)
    choice(version, VERSION_PATHS, "requested suite version")
    registry_path, _ = VERSION_PATHS[version]
    return validate_registry(root, read_json(local_path(root, registry_path)), expected_version=version)


def cell(value):
    """Keep retained text literal in Markdown tables, including pipes/newlines."""
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("\\", "&#92;")
            .replace("|", "&#124;").replace("`", "&#96;")
            .replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>"))


def json_value(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))


def render_table(registry):
    """Render a validated registry deterministically, without numerical analysis."""
    version = registry["suite_version"]
    choice(version, VERSION_PATHS, "suite_version")
    registry_path, _ = VERSION_PATHS[version]
    lines = [
        "# Реестр бенчмарков: сохранённые результаты", "",
        f"Набор: {cell(registry['suite_id'])}, версия {cell(registry['suite_version'])}.", "",
        f"Таблица автоматически воспроизводится из {registry_path}. "
        "Это вторичная русская таблица; полная академическая спецификация: [BENCHMARK_SUITE.md](BENCHMARK_SUITE.md).", "",
        "Регистрация ретроспективная: протоколы и результаты уже существовали до этого реестра. "
        "Проверка сверяет локальные SHA-256 и точные значения JSON, не выполняет новые научные запуски. "
        "Совпадение хэшей подтверждает идентичность файлов, а не научную корректность. "
        "Ни одна запись не является независимой научной валидацией. Общего балла нет.", "",
        "Статусы выполнения и решения исходного протокола разделены. Исторический NO-GO сохраняется; "
        "численный проход не означает подтверждение статистической калибровки, мощности или внешней валидности.", "",
        "## Методологические источники", "",
        "Внешние ссылки приводятся для методологии и карты поддержки. Проверка работает без сети "
        "и не требует загрузки внешних данных.", "",
        "| Источник | Роль | Ссылка |", "| --- | --- | --- |",
    ]
    if version == CURRENT_VERSION:
        lines[4:4] = ["Снимок версии 1.1.0: 2026-10-17, Round53. "
                      "Исторический снимок 1.0.0 сохранён без изменения в [BENCHMARK_RESULTS_RU.md](BENCHMARK_RESULTS_RU.md).", ""]
    for source in registry["sources"]:
        lines.append("| " + " | ".join(cell(source[key]) for key in ("id", "role", "url")) + " |")
    nist_heading = "## NIST: карта поддержки без запуска"
    nist_explanation = ("mapped_not_run означает сопоставление с реализацией; сертифицированные данные NIST "
                        "не запускались в этом наборе. unsupported означает отсутствие соответствующей операции в охвате карты.")
    if version == CURRENT_VERSION:
        nist_heading = "## NIST: версия 1.1.0, поддержка и численное выполнение"
        nist_explanation = ("executed_numerical означает выполненное численное сравнение, закреплённое за протоколом "
                            "и результатами Round53; исход численного критерия указан отдельно. "
                            "Это не сертификация NIST и не независимая научная валидация. "
                            "mapped_not_run означает сопоставление без запуска; unsupported означает отсутствие "
                            "соответствующей операции в охвате карты. Исторические статусы версии 1.0.0 не изменены.")
    lines += ["", nist_heading, "", nist_explanation, "",
              "| Операция | Поддержка | Основание и ограничение | Источник |",
              "| --- | --- | --- | --- |"]
    for item in registry["nist_support"]:
        refs = "; ".join(f"{ref['path']}:{ref['lines'][0]}-{ref['lines'][1]} "
                         f"(SHA-256 {ref['sha256']})" for ref in item["code_refs"])
        lines.append("| " + " | ".join(cell(value) for value in (
            item["operation"], item["status"], item["reason_ru"] + ("; " + refs if refs else ""),
            item["source_url"])) + " |")
    for category, label in CATEGORY_LABELS.items():
        benchmarks = [b for b in registry["benchmarks"] if b["category"] == category]
        if not benchmarks:
            continue
        lines += ["", f"## {label}", "",
                  "| Бенчмарк и версия | Выполнение | Решение протокола | Вывод в пределах данных |",
                  "| --- | --- | --- | --- |"]
        for b in benchmarks:
            lines.append("| " + " | ".join(cell(value) for value in (
                f"{b['id']} {b['version']}: {b['name_en']}", b["execution_status"],
                b["gate_status"], b["conclusion_ru"])) + " |")
        for b in benchmarks:
            identity = b["identity"]
            lines += ["", f"### {cell(b['id'])} — {cell(b['name_en'])}", "",
                      f"Версия записи: {cell(b['version'])}. Тип свидетельства: {cell(b['nature'])}.", "",
                      "Методы: " + "; ".join(f"{cell(m['id'])} ({cell(m['version'])})" for m in b["methods"]) + ".", "",
                      f"Протокол: {cell(identity['protocol_id'])}. Данные: {cell(identity['data_id'])}.", "",
                      "SHA-256 идентичности данных: " + (cell(identity["data_hash"]) if identity["data_hash"] is not None
                                                        else "не задан единый хэш; см. ограничения и закреплённые источники") + ".", "",
                      "Закреплённые файлы протокола:"]
            for ref in identity["protocol_refs"]:
                lines.append(f"- {cell(ref['path'])}; SHA-256 {ref['sha256']}")
            lines += ["", "Ограничения данных: " + cell(identity["data_limitations_ru"]), "",
                      "ADEMP (ретроспективная сводка сохранённых источников):", ""]
            for key in ("aims", "data", "estimands", "truth", "methods", "performance"):
                lines.append(f"- {key}: {cell(b['ademp'][key])}")
            lines += ["", "| Наблюдение | Сохранённое значение | Единица | Истина | Знаменатель и правило | Интерпретация | Файл, SHA-256 и JSON pointer |",
                      "| --- | --- | --- | --- | --- | --- | --- |"]
            for obs in b["observations"]:
                ref = obs["reference"]
                denominator = str(obs["denominator"]) if obs["denominator"] is not None else "не применим / недоступен"
                denominator_ref = obs["denominator_reference"]
                if denominator_ref is not None:
                    denominator += (f"; {denominator_ref['path']}; SHA-256 {denominator_ref['sha256']}; "
                                    f"pointer {json_value(denominator_ref['pointer'])}")
                values = (obs["label_ru"], json_value(obs["value"]), obs["unit"], obs["truth"],
                          denominator + "; " + obs["denominator_note_ru"], obs["interpretation_ru"],
                          f"{ref['path']}; SHA-256 {ref['sha256']}; pointer {json_value(ref['pointer'])}")
                lines.append("| " + " | ".join(cell(value) for value in values) + " |")
            if not b["observations"]:
                lines.append("| Нет наблюдений: запуск не выполнен | — | — | — | — | — | — |")
            lines += ["", "Неопределённость: " + cell(b["uncertainty_ru"]), "",
                      "Сбои и недоступные результаты: " + cell(b["failures_ru"]), "",
                      "Остановка и полнота: " + cell(b["stopping_ru"]), "",
                      "Сопоставимость: " + cell(b["comparability_ru"]), ""]
    return "\n".join(lines).rstrip() + "\n"


def check_or_write(root, *, write=False, version=CURRENT_VERSION):
    choice(version, VERSION_PATHS, "requested suite version")
    require(not write or version == CURRENT_VERSION,
            "Historical suite 1.0.0 is immutable; --write is permitted only for current suite 1.1.0")
    if version == CURRENT_VERSION:
        # History is required, even for an explicit write of the current view.
        check_or_write(root, version=HISTORICAL_VERSION)
    registry = load_registry(root, version=version)
    rendered = render_table(registry)
    _, table_path = VERSION_PATHS[version]
    path = local_path(root, table_path, must_exist=not write)
    if write:
        require(path.parent.is_dir(), "Output documentation directory is missing")
        path.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        require(path.read_bytes() == rendered.encode("utf-8"),
                f"Stale rendered table: {table_path}; "
                + ("historical view must be preserved" if version == HISTORICAL_VERSION
                   else "review the registry, then use --write"))
    return registry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Repository root (default: this script's repository)")
    parser.add_argument("--version", choices=tuple(VERSION_PATHS), default=CURRENT_VERSION,
                        help="Suite version (default: 1.1.0, also requiring valid historical 1.0.0)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Validate registry and committed table (default)")
    mode.add_argument("--write", action="store_true", help="Regenerate only the current Russian table; history is immutable")
    args = parser.parse_args(argv)
    try:
        registry = check_or_write(args.root, write=args.write, version=args.version)
    except (ValueError, OSError, UnicodeError, RecursionError) as error:
        print(f"Benchmark registry FAIL: {error}", file=sys.stderr)
        return 1
    print(f"Benchmark registry PASS: suite {registry['suite_version']}; {len(registry['benchmarks'])} entries; "
          f"table {'written' if args.write else 'current'}; no scientific execution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
