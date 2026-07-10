"""$P 포인트 클라우드 기반 손글씨 기호 인식기.

획(stroke) 목록을 32개 점의 포인트 클라우드로 정규화한 뒤,
학습된 템플릿과 탐욕적 클라우드 매칭으로 거리를 계산해 가장 가까운 기호를 찾는다.
참고: Vatavu, Anthony, Wobbrock - "Gestures as Point Clouds: A $P Recognizer" (2012)
"""

import json
import math
import os

N_POINTS = 32
PREFILTER_KEEP = 40        # 근사 거리로 남길 정밀 매칭 후보 수
STROKE_COUNT_PENALTY = 0.35  # 획 수가 1개 다를 때마다 더할 거리 (최대 2개분)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _path_length(stroke):
    return sum(_dist(stroke[i - 1], stroke[i]) for i in range(1, len(stroke)))


def _resample_stroke(stroke, n):
    """획 하나를 등간격 n개 점으로 리샘플링."""
    if n <= 1 or len(stroke) < 2:
        return [tuple(stroke[0])] * max(1, n)
    total = _path_length(stroke)
    if total <= 1e-12:
        return [tuple(stroke[0])] * n
    interval = total / (n - 1)
    out = [tuple(stroke[0])]
    acc = 0.0
    prev = stroke[0]
    i = 1
    while i < len(stroke):
        p = stroke[i]
        d = _dist(prev, p)
        if acc + d >= interval and d > 0:
            t = (interval - acc) / d
            q = (prev[0] + t * (p[0] - prev[0]), prev[1] + t * (p[1] - prev[1]))
            out.append(q)
            prev = q
            acc = 0.0
        else:
            acc += d
            prev = p
            i += 1
    while len(out) < n:
        out.append(tuple(stroke[-1]))
    return out[:n]


def preprocess(strokes):
    """획 목록 -> 정규화된 N_POINTS 포인트 클라우드 (스케일/위치 불변)."""
    strokes = [s for s in strokes if s]
    if not strokes:
        return None
    lengths = [_path_length(s) for s in strokes]
    total = sum(lengths)
    if total <= 1e-9:  # 점(dot)처럼 움직임이 거의 없는 입력
        return [(0.0, 0.0)] * N_POINTS
    alloc = [max(1, round(N_POINTS * ln / total)) for ln in lengths]
    while sum(alloc) > N_POINTS and max(alloc) > 1:
        alloc[alloc.index(max(alloc))] -= 1
    while sum(alloc) < N_POINTS:
        alloc[alloc.index(max(alloc))] += 1
    pts = []
    for s, n in zip(strokes, alloc):
        pts.extend(_resample_stroke(s, n))
    pts = pts[:N_POINTS]
    while len(pts) < N_POINTS:
        pts.append(pts[-1])
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    scale = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
    cx = sum(xs) / len(pts)
    cy = sum(ys) / len(pts)
    return [((x - cx) / scale, (y - cy) / scale) for x, y in pts]


def _aligned_dist(a, b):
    """리샘플링 순서 그대로 점끼리 비교하는 값싼 근사 거리 (프리필터용)."""
    return sum(math.hypot(pa[0] - pb[0], pa[1] - pb[1])
               for pa, pb in zip(a, b))


def _greedy(a, b, start):
    n = len(a)
    matched = [False] * n
    total = 0.0
    i = start
    for k in range(n):
        best_j = -1
        best_d = float("inf")
        for j in range(n):
            if not matched[j]:
                d = (a[i][0] - b[j][0]) ** 2 + (a[i][1] - b[j][1]) ** 2
                if d < best_d:
                    best_d = d
                    best_j = j
        matched[best_j] = True
        total += (1.0 - k / n) * math.sqrt(best_d)
        i = (i + 1) % n
    return total


def cloud_distance(a, b):
    n = len(a)
    step = max(1, round(math.sqrt(n)))
    best = float("inf")
    for start in range(0, n, step):
        best = min(best, _greedy(a, b, start), _greedy(b, a, start))
    return best


class TemplateStore:
    """라벨별 손글씨 샘플을 JSON 파일로 저장/로드하고 인식을 수행한다."""

    def __init__(self, path):
        self.path = path
        self._samples = {}  # label -> [{"strokes": ..., "cloud": ...}]
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for label, samples in data.get("labels", {}).items():
                for strokes in samples:
                    self._add_sample(label, strokes)

    def _add_sample(self, label, strokes):
        cloud = preprocess(strokes)
        if cloud is None:
            return
        self._samples.setdefault(label, []).append(
            {"strokes": strokes, "cloud": cloud,
             "nstrokes": len([s for s in strokes if s])})

    def add(self, label, strokes, save=True):
        self._add_sample(label, strokes)
        if save:
            self.save()

    def remove_last(self, label, save=True):
        """해당 라벨의 가장 최근 샘플 하나를 삭제 (잘못 학습한 것 취소용)."""
        samples = self._samples.get(label)
        if not samples:
            return False
        samples.pop()
        if not samples:
            del self._samples[label]
        if save:
            self.save()
        return True

    def save(self):
        data = {"labels": {label: [s["strokes"] for s in samples]
                           for label, samples in self._samples.items()}}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def count(self, label=None):
        if label is not None:
            return len(self._samples.get(label, []))
        return len(self._samples)

    def recognize(self, strokes, top=3):
        """[(라벨, 거리), ...]를 거리 오름차순으로 반환. 거리가 작을수록 유사.

        1단계: 값싼 근사 거리로 전체 템플릿 중 상위 PREFILTER_KEEP개만 남기고
        2단계: 남은 후보에만 정밀($P) 매칭. 획 수 차이에는 페널티를 더해
        모양은 비슷하지만 획 구성이 다른 기호(- 와 = 등)를 구분한다.
        """
        cloud = preprocess(strokes)
        if cloud is None or not self._samples:
            return []
        n_in = len([s for s in strokes if s])
        entries = [(label, s) for label, samples in self._samples.items()
                   for s in samples]
        if len(entries) > PREFILTER_KEEP:
            entries.sort(key=lambda e: _aligned_dist(cloud, e[1]["cloud"]))
            entries = entries[:PREFILTER_KEEP]
        best = {}
        for label, s in entries:
            d = cloud_distance(cloud, s["cloud"])
            d += STROKE_COUNT_PENALTY * min(abs(n_in - s["nstrokes"]), 2)
            if d < best.get(label, float("inf")):
                best[label] = d
        results = sorted(best.items(), key=lambda r: r[1])
        return results[:top]
