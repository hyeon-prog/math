"""CROHME 손글씨 수식 데이터셋에서 기호 템플릿을 추출해 templates.json에 병합.

CROHME(Competition on Recognition of Online Handwritten Mathematical
Expressions) 데이터의 수식 InkML에는 기호 단위 라벨(traceGroup)이 있어,
이를 낱개 기호 획 데이터로 추출해 $P 인식기의 템플릿으로 쓸 수 있다.

사용법:
    python import_crohme.py CROHME_full_v2.zip              # 기본 기호 세트 가져오기
    python import_crohme.py CROHME_full_v2.zip --list       # 사용 가능한 라벨 목록
    python import_crohme.py CROHME_full_v2.zip --samples 8  # 기호당 템플릿 수
    python import_crohme.py CROHME_full_v2.zip --only "\\pi \\sum 0 1"

zip 대신 미리 추출한 .jsonl({"label":..,"strokes":..} 줄 단위)도 받는다.

데이터 출처: CROHME 2013 (https://www.isical.ac.in/~crohme/) — 연구/교육 목적.
"""

import argparse
import collections
import json
import os
import random
import sys
import xml.etree.ElementTree as ET
import zipfile

from recognizer import TemplateStore, preprocess, cloud_distance

NS = {"ink": "http://www.w3.org/2003/InkML"}

# CROHME 라벨 -> 이 프로그램이 출력할 문자
DEFAULT_SYMBOLS = {
    **{d: d for d in "0123456789"},
    # "." 은 크기 정보가 정규화로 사라져 템플릿 매칭이 불가능 -> 앱에서 휴리스틱 처리
    "+": "+", "-": "-", "=": "=", "(": "(", ")": ")", "/": "/",
    "x": "x", "y": "y", "a": "a", "b": "b", "n": "n", "t": "t",
    "\\times": "×", "\\div": "÷", "\\pm": "±",
    "\\pi": "π", "\\alpha": "α", "\\beta": "β", "\\gamma": "γ",
    "\\theta": "θ", "\\phi": "φ", "\\lambda": "λ", "\\mu": "μ",
    "\\sigma": "σ",
    "\\leq": "≤", "\\geq": "≥", "\\neq": "≠", "\\lt": "<", "\\gt": ">",
    "\\infty": "∞", "\\sqrt": "√", "\\sum": "Σ", "\\int": "∫",
    "\\rightarrow": "→",
}


def _norm(strokes):
    """기호를 [0,1] 박스로 정규화(종횡비 유지), 좌표 반올림."""
    xs = [p[0] for s in strokes for p in s]
    ys = [p[1] for s in strokes for p in s]
    x0, y0 = min(xs), min(ys)
    scale = max(max(xs) - x0, max(ys) - y0, 1e-9)
    return [[(round((x - x0) / scale, 4), round((y - y0) / scale, 4))
             for x, y in s] for s in strokes]


def _parse_inkml(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    traces = {}
    for tr in root.findall("ink:trace", NS):
        pts = []
        for chunk in (tr.text or "").strip().split(","):
            parts = chunk.split()
            if len(parts) >= 2:
                try:
                    pts.append((float(parts[0]), float(parts[1])))
                except ValueError:
                    break
        if pts:
            traces[tr.get("id")] = pts
    out = []
    top = root.find("ink:traceGroup", NS)
    if top is None:
        return out
    for g in top.findall("ink:traceGroup", NS):
        ann = g.find("ink:annotation[@type='truth']", NS)
        if ann is None or not ann.text:
            continue
        strokes = [traces[tv.get("traceDataRef")]
                   for tv in g.findall("ink:traceView", NS)
                   if tv.get("traceDataRef") in traces]
        if strokes:
            out.append((ann.text.strip(), _norm(strokes)))
    return out


def load_samples(path):
    """zip 또는 jsonl에서 {라벨: [획목록, ...]} 로드."""
    by_label = collections.defaultdict(list)
    if path.endswith(".jsonl"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                by_label[rec["label"]].append(rec["strokes"])
        return by_label
    z = zipfile.ZipFile(path)
    files = [n for n in z.namelist()
             if "TrainINKML" in n and n.endswith(".inkml")]
    print(f"InkML 파일 {len(files)}개 파싱 중...")
    for i, name in enumerate(files):
        for label, strokes in _parse_inkml(z.read(name)):
            by_label[label].append(strokes)
        if (i + 1) % 2000 == 0:
            print(f"  {i + 1}/{len(files)}")
    return by_label


def select_diverse(samples, k, rng, cand_cap=30):
    """이상치를 걸러낸 뒤 서로 최대한 다른 k개 샘플을 고른다 (필체 다양성 확보)."""
    cands = samples if len(samples) <= cand_cap else rng.sample(samples, cand_cap)
    clouds = [preprocess(s) for s in cands]
    n = len(cands)
    if n <= k:
        return cands
    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            dist[i][j] = dist[j][i] = cloud_distance(clouds[i], clouds[j])
    # 같은 라벨 안에서 유독 동떨어진 샘플(분할 오류/악필)은 후보에서 제외
    med = sorted(range(n), key=lambda i: sorted(dist[i])[n // 2])
    keep = med[:max(k, int(n * 0.75))]
    # 가장 중심적인 샘플에서 시작해 farthest-point 방식으로 k개 선택
    chosen = [keep[0]]
    while len(chosen) < k:
        best_i, best_v = None, -1.0
        for i in keep:
            if i in chosen:
                continue
            v = min(dist[i][j] for j in chosen)
            if v > best_v:
                best_v, best_i = v, i
        chosen.append(best_i)
    return [cands[i] for i in chosen]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", help="CROHME zip 또는 추출된 jsonl 경로")
    ap.add_argument("--samples", type=int, default=8, help="기호당 템플릿 수")
    ap.add_argument("--only", help='가져올 CROHME 라벨만 지정 (예: "0 1 \\pi")')
    ap.add_argument("--list", action="store_true", help="라벨 목록만 출력")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if stream:
            stream.reconfigure(encoding="utf-8", errors="replace")

    by_label = load_samples(args.source)
    if args.list:
        for label, ss in sorted(by_label.items(), key=lambda kv: -len(kv[1])):
            mark = " *" if label in DEFAULT_SYMBOLS else ""
            print(f"{len(ss):6d}  {label}{mark}")
        print("(* = 기본 세트에 포함)")
        return

    wanted = DEFAULT_SYMBOLS
    if args.only:
        names = args.only.split()
        wanted = {n: DEFAULT_SYMBOLS.get(n, n.lstrip("\\")) for n in names}

    rng = random.Random(args.seed)
    store = TemplateStore(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "templates.json"))
    imported = skipped = 0
    for crohme_label, out_label in wanted.items():
        samples = by_label.get(crohme_label, [])
        if len(samples) < 3:
            print(f"건너뜀: {crohme_label} (샘플 {len(samples)}개뿐)")
            skipped += 1
            continue
        for strokes in select_diverse(samples, args.samples, rng):
            store.add(out_label, strokes, save=False)
        imported += 1
        print(f"{crohme_label:14s} -> '{out_label}'  "
              f"(보유 {len(samples)}개 중 {min(args.samples, len(samples))}개 선택)")
    store.save()
    print(f"\n완료: {imported}종 가져옴, {skipped}종 건너뜀 "
          f"-> 총 {store.count()}종 라벨이 templates.json에 저장됨")


if __name__ == "__main__":
    main()
