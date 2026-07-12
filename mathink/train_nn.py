"""MathInk의 CNN 기호 분류기를 CROHME 데이터로 학습한다.

사용법:
    python train_nn.py --zip CROHME_full_v2.zip [--epochs 12]

출력 (같은 폴더에 저장):
    nn_model.npz   - numpy 추론용 가중치 (앱이 시작할 때 자동 로드)
    nn_labels.json - 클래스 라벨 목록

학습에는 PyTorch(CPU)가 필요하지만, 앱 실행에는 numpy만 있으면 된다.
templates.json의 사용자 필체도 함께 학습된다 (3배 가중).
"""

import argparse
import collections
import json
import os
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from import_crohme import DEFAULT_SYMBOLS, load_samples
from recognizer import render_strokes, IMG_SIZE

HERE = os.path.dirname(os.path.abspath(__file__))
# CROHME 라벨 -> 출력 문자 (import_crohme 기본 세트 + 추가 기호)
EXTRA_SYMBOLS = {
    "\\sin": "sin", "\\cos": "cos", "\\tan": "tan",
    "\\log": "log", "\\lim": "lim",
    "|": "|", "[": "[", "]": "]", "!": "!", ",": ",",
}
CLASS_MAP = {**DEFAULT_SYMBOLS, **EXTRA_SYMBOLS}
MIN_USER_CLASS = 5   # 사용자 전용 라벨이 클래스가 되기 위한 최소 샘플 수
USER_REPEAT = 3      # 사용자 필체 학습 가중 (반복 횟수)


class SymbolCNN(nn.Module):
    def __init__(self, n_classes):
        super().__init__()
        self.c1 = nn.Conv2d(1, 16, 3, padding=1)
        self.c2 = nn.Conv2d(16, 16, 3, padding=1)
        self.c3 = nn.Conv2d(16, 32, 3, padding=1)
        self.c4 = nn.Conv2d(32, 32, 3, padding=1)
        flat = 32 * (IMG_SIZE // 4) * (IMG_SIZE // 4)
        self.f1 = nn.Linear(flat + 4, 256)   # +4: 획 수 원핫(1,2,3,4+)
        self.f2 = nn.Linear(256, n_classes)
        self.drop = nn.Dropout(0.3)

    def forward(self, x, ns):
        x = F.relu(self.c1(x))
        x = F.max_pool2d(F.relu(self.c2(x)), 2)
        x = F.relu(self.c3(x))
        x = F.max_pool2d(F.relu(self.c4(x)), 2)
        x = torch.cat([x.flatten(1), ns], dim=1)
        x = self.drop(F.relu(self.f1(x)))
        return self.f2(x)


def build_dataset(zip_path):
    """(라벨, 획들, 사용자여부) 리스트를 만든다."""
    by_label = load_samples(zip_path)
    data = []
    for crohme_label, samples in by_label.items():
        out = CLASS_MAP.get(crohme_label)
        if out:
            for s in samples:
                data.append((out, s, False))
    tpath = os.path.join(HERE, "templates.json")
    if os.path.exists(tpath):
        user = json.load(open(tpath, encoding="utf-8"))["labels"]
        known = set(CLASS_MAP.values())
        n_user = 0
        for label, samples in user.items():
            if label in known or len(samples) >= MIN_USER_CLASS:
                for s in samples:
                    data.append((label, s, True))
                    n_user += 1
        print(f"사용자 필체 {n_user}개 포함 (반복 {USER_REPEAT}배)")
    return data


def rand_theta(n, rng):
    """배치용 랜덤 어파인 파라미터 (회전/크기/기울임/이동)."""
    ang = rng.uniform(-0.16, 0.16, n)
    sc = rng.uniform(0.85, 1.18, n)
    shx = rng.uniform(-0.15, 0.15, n)
    tx = rng.uniform(-0.12, 0.12, n)
    ty = rng.uniform(-0.12, 0.12, n)
    theta = np.zeros((n, 2, 3), dtype=np.float32)
    c, s = np.cos(ang) * sc, np.sin(ang) * sc
    theta[:, 0, 0] = c
    theta[:, 0, 1] = -s + shx
    theta[:, 0, 2] = tx
    theta[:, 1, 0] = s
    theta[:, 1, 1] = c
    theta[:, 1, 2] = ty
    return torch.from_numpy(theta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default=None, help="CROHME_full_v2.zip 경로")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch", type=int, default=256)
    args = ap.parse_args()
    if not args.zip or not os.path.exists(args.zip):
        raise SystemExit("--zip 으로 CROHME_full_v2.zip 경로를 지정하세요")

    rng = np.random.default_rng(7)
    torch.manual_seed(7)

    print("데이터셋 구성 중...")
    data = build_dataset(args.zip)
    labels = sorted({d[0] for d in data})
    lab_idx = {l: i for i, l in enumerate(labels)}
    print(f"샘플 {len(data)}개 / 클래스 {len(labels)}종")

    print("이미지 렌더링 중 (1회)...")
    t0 = time.time()
    X = np.zeros((len(data), IMG_SIZE, IMG_SIZE), dtype=np.uint8)
    y = np.zeros(len(data), dtype=np.int64)
    ns = np.zeros(len(data), dtype=np.int64)
    is_user = np.zeros(len(data), dtype=bool)
    for i, (label, strokes, u) in enumerate(data):
        X[i] = (render_strokes(strokes) * 255).astype(np.uint8)
        y[i] = lab_idx[label]
        ns[i] = min(len([s for s in strokes if s]), 4)
        is_user[i] = u
        if (i + 1) % 20000 == 0:
            print(f"  {i + 1}/{len(data)}")
    print(f"  렌더링 {time.time() - t0:.0f}초")

    # 클래스별 층화 분할 (검증 8%, 사용자 샘플은 전부 학습에)
    val_mask = np.zeros(len(data), dtype=bool)
    for ci in range(len(labels)):
        idxs = np.where((y == ci) & ~is_user)[0]
        if len(idxs) >= 20:
            k = max(2, int(len(idxs) * 0.08))
            val_mask[rng.choice(idxs, k, replace=False)] = True
    train_idx = np.where(~val_mask)[0]
    # 사용자 필체 가중
    user_idx = np.where(is_user)[0]
    train_idx = np.concatenate([train_idx] + [user_idx] * (USER_REPEAT - 1))
    val_idx = np.where(val_mask)[0]
    print(f"학습 {len(train_idx)} / 검증 {len(val_idx)}")

    freq = np.bincount(y[train_idx], minlength=len(labels)).astype(np.float64)
    w = 1.0 / np.sqrt(np.maximum(freq, 1))
    w *= len(labels) / w.sum()
    class_w = torch.tensor(w, dtype=torch.float32)

    model = SymbolCNN(len(labels))
    opt = torch.optim.AdamW(model.parameters(), lr=1.5e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    lossf = nn.CrossEntropyLoss(weight=class_w)

    Xt = torch.from_numpy(X)
    yt = torch.from_numpy(y)
    nst = F.one_hot(torch.from_numpy(ns) - 1, 4).float()

    def eval_val():
        model.eval()
        correct = 0
        with torch.no_grad():
            for b in range(0, len(val_idx), 512):
                bi = val_idx[b:b + 512]
                xb = Xt[bi].float().div_(255).unsqueeze(1)
                out = model(xb, nst[bi])
                correct += (out.argmax(1) == yt[bi]).sum().item()
        return correct / max(len(val_idx), 1)

    best_acc, best_state = 0.0, None
    for ep in range(1, args.epochs + 1):
        model.train()
        perm = rng.permutation(train_idx)
        t0 = time.time()
        total_loss = 0.0
        for b in range(0, len(perm), args.batch):
            bi = perm[b:b + args.batch]
            xb = Xt[bi].float().div_(255).unsqueeze(1)
            theta = rand_theta(len(bi), rng)
            grid = F.affine_grid(theta, xb.shape, align_corners=False)
            xb = F.grid_sample(xb, grid, align_corners=False)
            out = model(xb, nst[bi])
            loss = lossf(out, yt[bi])
            opt.zero_grad()
            loss.backward()
            opt.step()
            total_loss += loss.item() * len(bi)
        sched.step()
        acc = eval_val()
        print(f"epoch {ep:2d}/{args.epochs}  loss {total_loss / len(perm):.4f}"
              f"  val {acc * 100:.2f}%  ({time.time() - t0:.0f}s)", flush=True)
        if acc > best_acc:
            best_acc = acc
            best_state = {k: v.detach().clone()
                          for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    out = {
        "c1w": model.c1.weight.detach().numpy(),
        "c1b": model.c1.bias.detach().numpy(),
        "c2w": model.c2.weight.detach().numpy(),
        "c2b": model.c2.bias.detach().numpy(),
        "c3w": model.c3.weight.detach().numpy(),
        "c3b": model.c3.bias.detach().numpy(),
        "c4w": model.c4.weight.detach().numpy(),
        "c4b": model.c4.bias.detach().numpy(),
        "f1w": model.f1.weight.detach().numpy(),
        "f1b": model.f1.bias.detach().numpy(),
        "f2w": model.f2.weight.detach().numpy(),
        "f2b": model.f2.bias.detach().numpy(),
    }
    np.savez_compressed(os.path.join(HERE, "nn_model.npz"), **out)
    with open(os.path.join(HERE, "nn_labels.json"), "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False)
    print(f"\n완료: 최고 검증 정확도 {best_acc * 100:.2f}% -> nn_model.npz 저장")


if __name__ == "__main__":
    main()
