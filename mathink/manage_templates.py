"""학습된 필체 템플릿(templates.json) 관리 도구.

잘못 학습시킨 샘플을 찾아서 지울 때 사용한다. 수정 전에 자동으로
templates.json.bak 백업을 만든다 (실수하면 .bak을 복사해서 복원).

사용법:
    python manage_templates.py list [라벨]      # 라벨별 샘플 수 (라벨 지정 시 상세)
    python manage_templates.py show 라벨        # 샘플을 그림으로 표시 (번호 포함)
    python manage_templates.py remove 라벨 번호...   # show에서 본 번호의 샘플 삭제
    python manage_templates.py remove-last 라벨 [N]  # 최근 추가된 N개 삭제 (기본 1)
    python manage_templates.py delete 라벨      # 라벨을 통째로 삭제

예: 't'에 잘못 학습된 샘플이 있는 것 같을 때
    python manage_templates.py show t          # 그림을 보고 이상한 샘플 번호 확인
    python manage_templates.py remove t 9      # 9번 샘플 삭제
"""

import json
import os
import shutil
import sys

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "templates.json")


def load():
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def save(data):
    shutil.copy2(PATH, PATH + ".bak")
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"저장됨 (이전 상태 백업: {os.path.basename(PATH)}.bak)")


def render(strokes, width=36, height=13):
    """획들을 ASCII 그림으로. 획 순서를 1,2,3... 숫자로 표시."""
    pts = [(p[0], p[1]) for s in strokes for p in s]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0 = min(xs), min(ys)
    w = max(max(xs) - x0, 1e-9)
    h = max(max(ys) - y0, 1e-9)
    scale = min((width - 1) / w, (height - 1) / h)
    grid = [[" "] * width for _ in range(height)]
    for si, stroke in enumerate(strokes):
        ch = str((si + 1) % 10)
        prev = None
        for x, y in stroke:
            gx = int((x - x0) * scale)
            gy = int((y - y0) * scale)
            if prev is not None:  # 점 사이를 직선으로 보간
                px, py = prev
                steps = max(abs(gx - px), abs(gy - py), 1)
                for t in range(steps + 1):
                    ix = px + (gx - px) * t // steps
                    iy = py + (gy - py) * t // steps
                    grid[iy][ix] = ch
            else:
                grid[gy][gx] = ch
            prev = (gx, gy)
    return ["".join(row) for row in grid]


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream:
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd = args[0]
    data = load()
    labels = data.get("labels", {})

    if cmd == "list":
        if len(args) > 1:
            label = args[1]
            samples = labels.get(label)
            if samples is None:
                sys.exit(f"'{label}' 라벨이 없습니다")
            print(f"'{label}': {len(samples)}개 샘플 "
                  f"(자세히 보려면: show {label})")
            return
        print(f"총 {len(labels)}종")
        for label, samples in sorted(labels.items(),
                                     key=lambda kv: -len(kv[1])):
            print(f"{len(samples):4d}개  {label}")

    elif cmd == "show":
        if len(args) < 2:
            sys.exit("사용법: show 라벨")
        label = args[1]
        samples = labels.get(label)
        if samples is None:
            sys.exit(f"'{label}' 라벨이 없습니다")
        for i, strokes in enumerate(samples):
            print(f"\n--- [{i}] 샘플 {i} ({len(strokes)}획, "
                  f"숫자 = 획 순서) ---")
            for line in render(strokes):
                print("  " + line)
        print(f"\n삭제하려면: python manage_templates.py remove {label} 번호")

    elif cmd == "remove":
        if len(args) < 3:
            sys.exit("사용법: remove 라벨 번호 [번호...]")
        label = args[1]
        samples = labels.get(label)
        if samples is None:
            sys.exit(f"'{label}' 라벨이 없습니다")
        try:
            idxs = sorted({int(a) for a in args[2:]}, reverse=True)
        except ValueError:
            sys.exit("번호는 정수로 입력하세요")
        for i in idxs:
            if not 0 <= i < len(samples):
                sys.exit(f"번호 {i}가 범위를 벗어남 (0~{len(samples) - 1})")
            samples.pop(i)
            print(f"'{label}' 샘플 {i} 삭제")
        if not samples:
            del labels[label]
            print(f"샘플이 없어져 '{label}' 라벨 자체를 삭제")
        save(data)

    elif cmd == "remove-last":
        if len(args) < 2:
            sys.exit("사용법: remove-last 라벨 [개수]")
        label = args[1]
        n = int(args[2]) if len(args) > 2 else 1
        samples = labels.get(label)
        if samples is None:
            sys.exit(f"'{label}' 라벨이 없습니다")
        n = min(n, len(samples))
        del samples[-n:]
        print(f"'{label}'의 최근 샘플 {n}개 삭제 (남은 {len(samples)}개)")
        if not samples:
            del labels[label]
            print(f"샘플이 없어져 '{label}' 라벨 자체를 삭제")
        save(data)

    elif cmd == "delete":
        if len(args) < 2:
            sys.exit("사용법: delete 라벨")
        label = args[1]
        if label not in labels:
            sys.exit(f"'{label}' 라벨이 없습니다")
        n = len(labels.pop(label))
        print(f"'{label}' 라벨 삭제 (샘플 {n}개)")
        save(data)

    else:
        print(__doc__)
        sys.exit(f"알 수 없는 명령: {cmd}")


if __name__ == "__main__":
    main()
