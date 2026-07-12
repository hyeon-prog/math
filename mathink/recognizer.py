"""손글씨 기호 인식기: CNN(신경망) + $P 포인트 클라우드 융합.

- CNN: CROHME 데이터셋으로 학습된 분류기 (train_nn.py로 학습,
  nn_model.npz가 있으면 numpy만으로 추론). 기본 기호의 정확도 담당.
- $P: 획을 32개 점으로 정규화해 템플릿과 탐욕 매칭. 사용자가 T키로
  즉시 학습시키는 개인 필체와 CNN이 모르는 기호 담당.
두 점수를 합쳐 최종 후보를 낸다. 모델 파일이 없으면 $P만 사용.
참고: Vatavu, Anthony, Wobbrock - "Gestures as Point Clouds" (2012)
"""

import json
import math
import os

N_POINTS = 32
PREFILTER_KEEP = 40        # 근사 거리로 남길 정밀 매칭 후보 수
STROKE_COUNT_PENALTY = 0.35  # 획 수가 1개 다를 때마다 더할 거리 (최대 2개분)
IMG_SIZE = 28              # CNN 입력 이미지 크기
NN_WEIGHT = 0.6            # 융합 시 CNN 점수 가중치 (나머지는 $P)


def render_strokes(strokes, size=IMG_SIZE, margin=2):
    """획들을 size x size 흑백 이미지(numpy float32)로 렌더링.

    좌표 스케일과 무관하게 기호 bbox를 여백을 남기고 중앙 배치한다.
    학습(train_nn.py)과 추론이 반드시 같은 함수를 써야 한다.
    """
    import numpy as np
    img = np.zeros((size, size), dtype=np.float32)
    pts = [(p[0], p[1]) for s in strokes for p in s]
    if not pts:
        return img
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0 = min(xs), min(ys)
    span = max(max(xs) - x0, max(ys) - y0, 1e-6)
    scale = (size - 1 - 2 * margin) / span
    ox = (size - 1 - (max(xs) - x0) * scale) / 2
    oy = (size - 1 - (max(ys) - y0) * scale) / 2
    for stroke in strokes:
        if len(stroke) == 1:
            stroke = [stroke[0], stroke[0]]
        for i in range(1, len(stroke)):
            ax, ay = stroke[i - 1][0], stroke[i - 1][1]
            bx, by = stroke[i][0], stroke[i][1]
            gax, gay = (ax - x0) * scale + ox, (ay - y0) * scale + oy
            gbx, gby = (bx - x0) * scale + ox, (by - y0) * scale + oy
            n = int(max(abs(gbx - gax), abs(gby - gay))) + 1
            for t in range(n + 1):
                fx = gax + (gbx - gax) * t / n
                fy = gay + (gby - gay) * t / n
                xi, yi = int(fx), int(fy)
                for dy in (0, 1):      # 2x2 bilinear splat
                    for dx in (0, 1):
                        px, py = xi + dx, yi + dy
                        if 0 <= px < size and 0 <= py < size:
                            w = (1 - abs(fx - px)) * (1 - abs(fy - py))
                            if w > img[py, px]:
                                img[py, px] = w
    return img


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
        self.nn = self._load_nn()  # CNN 모델이 있으면 융합 인식 사용

    def _load_nn(self):
        """같은 폴더에 학습된 CNN(nn_model.npz)이 있으면 로드한다."""
        base = os.path.dirname(os.path.abspath(self.path))
        model = os.path.join(base, "nn_model.npz")
        labels = os.path.join(base, "nn_labels.json")
        if os.path.exists(model) and os.path.exists(labels):
            try:
                return NeuralClassifier(model, labels)
            except Exception:
                return None
        return None

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

    def _recognize_pp(self, strokes, top=3):
        """$P 매칭: [(라벨, 거리), ...] 오름차순. 거리가 작을수록 유사.

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

    def recognize(self, strokes, top=3):
        """CNN과 $P 점수를 융합한 최종 후보 [(라벨, 점수), ...].

        점수는 0~1로 작을수록 확신이 높다 (기존 거리 표기와 호환).
        CNN 모델이 없으면 $P 결과를 그대로 반환한다. CNN이 모르는 라벨
        (사용자가 직접 학습한 기호)은 $P 점수를 가중 없이 온전히 반영해
        개인 필체가 불리하지 않게 한다.
        """
        pp = self._recognize_pp(strokes, top=6)
        if self.nn is None:
            return pp[:top]
        try:
            nn_cands = self.nn.predict(strokes, top=6)
        except Exception:
            return pp[:top]
        scores = {}
        for label, d in pp:
            s = math.exp(-d)
            scores[label] = s if label not in self.nn.label_set \
                else (1 - NN_WEIGHT) * s
        for label, p in nn_cands:
            scores[label] = scores.get(label, 0.0) + NN_WEIGHT * p
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:top]
        return [(label, round(1 - s, 4)) for label, s in ranked]


class NeuralClassifier:
    """train_nn.py로 학습한 CNN을 numpy만으로 추론한다 (torch 불필요)."""

    def __init__(self, model_path, labels_path):
        import numpy as np
        self.np = np
        z = np.load(model_path)
        self.w = {k: z[k].astype(np.float32) for k in z.files}
        with open(labels_path, encoding="utf-8") as f:
            self.labels = json.load(f)
        self.label_set = set(self.labels)

    def _conv(self, x, w, b):
        """3x3, padding 1 합성곱 (im2col 방식)."""
        np = self.np
        C, H, W = x.shape
        xp = np.pad(x, ((0, 0), (1, 1), (1, 1)))
        cols = np.empty((C * 9, H * W), dtype=np.float32)
        k = 0
        for c in range(C):
            for i in range(3):
                for j in range(3):
                    cols[k] = xp[c, i:i + H, j:j + W].ravel()
                    k += 1
        out = w.reshape(w.shape[0], -1) @ cols + b[:, None]
        return out.reshape(w.shape[0], H, W)

    def _pool(self, x):
        C, H, W = x.shape
        return x.reshape(C, H // 2, 2, W // 2, 2).max(axis=(2, 4))

    def predict(self, strokes, top=5):
        """[(라벨, 확률), ...] 확률 내림차순 top개."""
        np = self.np
        w = self.w
        x = render_strokes(strokes)[None].astype(np.float32)
        x = np.maximum(self._conv(x, w["c1w"], w["c1b"]), 0)
        x = self._pool(np.maximum(self._conv(x, w["c2w"], w["c2b"]), 0))
        x = np.maximum(self._conv(x, w["c3w"], w["c3b"]), 0)
        x = self._pool(np.maximum(self._conv(x, w["c4w"], w["c4b"]), 0))
        ns = min(max(len([s for s in strokes if s]), 1), 4)
        onehot = np.zeros(4, dtype=np.float32)
        onehot[ns - 1] = 1.0
        v = np.concatenate([x.ravel(), onehot])
        h = np.maximum(w["f1w"] @ v + w["f1b"], 0)
        logits = w["f2w"] @ h + w["f2b"]
        e = np.exp(logits - logits.max())
        p = e / e.sum()
        order = np.argsort(-p)[:top]
        return [(self.labels[i], float(p[i])) for i in order]
