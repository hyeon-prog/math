/**
 * =====================================================================
 * app.js — 폼 처리 · 매칭 알고리즘 · 유형별 탭 · 접수상태 · 렌더링
 * 의존성: js/data.js 의 전역 상수 ITEMS, REGIONS, DATA_VERIFIED_AT
 * ===================================================================== */

/* ------------------------------------------------------------------ *
 * 0. 상수 & 상태
 * ------------------------------------------------------------------ */

// 관심도 기반 추천 커트라인: 전체 조건 중 60% 이상 충족하면 "관심 항목"으로 노출
const INTEREST_THRESHOLD = 0.6;

// 결과 화면 탭 정의 (data.js 의 type 필드와 매핑)
const TYPES = [
  { key: "all", label: "전체" },
  { key: "policy", label: "정부정책" },
  { key: "local", label: "지자체 프로그램" },
  { key: "contest", label: "공모전·대외활동" },
];

// 카드에 표시할 유형 라벨 (짧은 버전)
const TYPE_LABELS = { policy: "정부정책", local: "지자체", contest: "공모전" };

// 카테고리별 태그 색상 (css/style.css 의 토큰과 매핑)
const CATEGORY_COLORS = {
  "주거": "var(--cat-housing)",
  "취업": "var(--cat-job)",
  "금융": "var(--cat-fin)",
  "복지·양육": "var(--cat-care)",
  "생활지원": "var(--cat-life)",
  "공모전": "var(--cat-contest)",
};

// 행정구역 개편 별칭: 사용자가 선택한 시/도 ↔ 통합 후 명칭 매칭
// (2026년 개편으로 광주광역시+전라남도 → 전남광주통합특별시)
const REGION_ALIASES = {
  "광주광역시": ["전남광주통합특별시"],
  "전라남도": ["전남광주통합특별시"],
};

// 취업 상태 코드 → 한글 라벨 (미충족 사유 표시에 사용)
const EMPLOYMENT_LABELS = {
  student: "학생", jobseeker: "구직자", employed: "재직자",
  freelancer: "프리랜서", "self-employed": "자영업자", none: "무직/기타",
};

const $ = (selector) => document.querySelector(selector);

// 화면 상태: 마지막 매칭 결과 + 현재 선택된 탭
let lastMatch = null;
let activeType = "all";

// 사용 중인 데이터셋 — 기본은 번들 데이터(js/data.js), 라이브 JSON 로드 성공 시 교체
let itemsData = { items: ITEMS, verifiedAt: DATA_VERIFIED_AT, live: false };

/* ------------------------------------------------------------------ *
 * 1. 거주지 드롭다운 초기화 (시/도 → 시/군/구 연동)
 * ------------------------------------------------------------------ */

function initRegionSelects() {
  const sidoSelect = $("#sido");
  const sigunguSelect = $("#sigungu");

  Object.keys(REGIONS).forEach((sido) => sidoSelect.add(new Option(sido, sido)));

  sidoSelect.addEventListener("change", () => {
    const districts = REGIONS[sidoSelect.value] || [];
    sigunguSelect.innerHTML = "";
    sigunguSelect.disabled = districts.length === 0;
    sigunguSelect.add(new Option(districts.length ? "선택하세요" : "시/도를 먼저 선택하세요", ""));
    districts.forEach((gu) => sigunguSelect.add(new Option(gu, gu)));
  });
}

/* ------------------------------------------------------------------ *
 * 2. 폼 입력값 → 사용자 프로필 객체로 변환
 * ------------------------------------------------------------------ */

function buildUserProfile(form) {
  const data = new FormData(form);
  const family = data.get("family"); // single | married | married-child | single-parent

  return {
    age: Number(data.get("age")),
    sido: data.get("sido"),                    // 예: "서울특별시"
    sigungu: data.get("sigungu"),              // 예: "마포구" (현재 매칭은 시/도 단위, 향후 확장용)
    householdSize: Number(data.get("household")),
    employment: data.get("employment"),
    married: family === "married" || family === "married-child",
    hasChildren: family === "married-child" || family === "single-parent",
  };
}

/* ------------------------------------------------------------------ *
 * 3. ★ 핵심: 매칭 알고리즘
 * ------------------------------------------------------------------ *
 * 항목마다 "실제로 요구하는 조건"만 골라 검사(checks)하고,
 *   - perfect : 모든 조건 충족
 *   - score   : 충족 비율 (관심도 점수, 0~1)
 * 을 계산합니다. 조건이 없는 항목(null)은 검사 대상에서 제외하므로
 * 점수가 불리하게 희석되지 않습니다. (조건이 하나도 없으면 전 국민 대상)
 * ------------------------------------------------------------------ */

function evaluateItem(user, item) {
  const e = item.eligibility;
  const checks = []; // { label: 조건명, pass: 충족 여부, hint: 미충족 사유 }

  // ① 나이 조건
  if (e.minAge !== null || e.maxAge !== null) {
    const pass =
      (e.minAge === null || user.age >= e.minAge) &&
      (e.maxAge === null || user.age <= e.maxAge);
    checks.push({
      label: "나이",
      pass,
      hint: `만 ${e.minAge ?? "제한없음"}~${e.maxAge ?? "제한없음"}세 대상`,
    });
  }

  // ② 거주지 조건 ("전국"이면 무조건 통과, 행정구역 개편 별칭 포함 매칭)
  if (!e.regions.includes("전국")) {
    const userRegions = [user.sido, ...(REGION_ALIASES[user.sido] || [])];
    checks.push({
      label: "거주지",
      pass: e.regions.some((r) => userRegions.includes(r)),
      hint: `${e.regions.join(", ")} 거주자 대상`,
    });
  }

  // ※ 소득 조건은 매칭에서 제외 — 개인이 자신의 중위소득 %를 알기 어려워
  //   입력받지 않고, 카드의 '지원 대상' 문구로만 안내합니다. (e.maxIncomeRatio는 참고용)

  // ③ 취업 상태 조건
  if (e.employment !== null) {
    checks.push({
      label: "취업 상태",
      pass: e.employment.includes(user.employment),
      hint: `${e.employment.map((c) => EMPLOYMENT_LABELS[c]).join("·")} 대상`,
    });
  }

  // ④ 혼인 상태 조건
  if (e.maritalStatus !== null) {
    checks.push({
      label: "혼인 상태",
      pass: (e.maritalStatus === "married") === user.married,
      hint: e.maritalStatus === "married" ? "기혼 가구 대상" : "미혼 대상",
    });
  }

  // ⑤ 자녀 조건
  if (e.requiresChildren) {
    checks.push({ label: "자녀", pass: user.hasChildren, hint: "자녀 양육 가구 대상" });
  }

  // ⑥ 가구원 수 조건
  if (e.minHouseholdSize !== null) {
    checks.push({
      label: "가구원 수",
      pass: user.householdSize >= e.minHouseholdSize,
      hint: `${e.minHouseholdSize}인 이상 가구 대상`,
    });
  }

  const passedCount = checks.filter((c) => c.pass).length;

  return {
    item,
    checks,
    score: checks.length === 0 ? 1 : passedCount / checks.length,
    perfect: passedCount === checks.length,
    failed: checks.filter((c) => !c.pass),
  };
}

/**
 * 전체 항목을 평가한 뒤 세 그룹으로 분류
 *  - perfect : 모든 조건 충족 + 현재 접수 중 → 바로 신청 가능
 *  - waiting : 모든 조건 충족이지만 접수 기간 아님 → 다음 공고 대기
 *  - partial : 60% 이상 충족 → 관심 항목 (점수 내림차순)
 */
function matchItems(user, items) {
  const results = items.map((it) => evaluateItem(user, it));

  return {
    perfect: results.filter((r) => r.perfect && r.item.open),
    waiting: results.filter((r) => r.perfect && !r.item.open),
    partial: results
      .filter((r) => !r.perfect && r.score >= INTEREST_THRESHOLD)
      .sort((a, b) => b.score - a.score),
  };
}

/* ------------------------------------------------------------------ *
 * 4. 유형별 탭 (전체 / 정부정책 / 지자체 / 공모전)
 * ------------------------------------------------------------------ */

/** 특정 탭에 표시될 결과만 필터링 */
function filterByType(results, typeKey) {
  return typeKey === "all" ? results : results.filter((r) => r.item.type === typeKey);
}

/** 탭별 매칭 건수 (신청 가능 + 접수 대기 + 관심 합계) — 탭 배지에 표시 */
function countByType(typeKey) {
  return (
    filterByType(lastMatch.perfect, typeKey).length +
    filterByType(lastMatch.waiting, typeKey).length +
    filterByType(lastMatch.partial, typeKey).length
  );
}

function renderTabs() {
  $("#type-tabs").innerHTML = TYPES.map((t) => `
    <button type="button" class="tab" role="tab" id="tab-${t.key}" data-type="${t.key}"
            aria-selected="${t.key === activeType}" aria-controls="result-panel">
      ${t.label}<span class="count">${countByType(t.key)}</span>
    </button>`).join("");
  $("#result-panel").setAttribute("aria-labelledby", `tab-${activeType}`);
}

function selectTab(typeKey, { focus = false } = {}) {
  activeType = typeKey;
  renderTabs();
  renderLists();
  if (focus) $(`#tab-${typeKey}`)?.focus();
}

function initTabs() {
  const tabsEl = $("#type-tabs");

  // 클릭으로 탭 전환
  tabsEl.addEventListener("click", (event) => {
    const btn = event.target.closest("[role='tab']");
    if (btn) selectTab(btn.dataset.type);
  });

  // 접근성: 좌우 방향키로 탭 이동
  tabsEl.addEventListener("keydown", (event) => {
    const idx = TYPES.findIndex((t) => t.key === activeType);
    if (event.key === "ArrowRight") {
      event.preventDefault();
      selectTab(TYPES[(idx + 1) % TYPES.length].key, { focus: true });
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      selectTab(TYPES[(idx - 1 + TYPES.length) % TYPES.length].key, { focus: true });
    }
  });
}

/* ------------------------------------------------------------------ *
 * 5. 결과 렌더링
 * ------------------------------------------------------------------ */

/** XSS 방지용 이스케이프 (데이터가 API 응답으로 바뀔 때를 대비) */
function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
  );
}

/**
 * 항목 1건 → 카드 HTML
 * variant: "ok"(신청 가능) | "waiting"(접수 대기) | "partial"(관심)
 */
function renderCard(result, variant) {
  const p = result.item;
  const catColor = CATEGORY_COLORS[p.category] || "var(--muted)";
  const regionLabel = p.eligibility.regions.includes("전국") ? "전국" : p.eligibility.regions.join("·");

  // 상태 표시: 접수 여부 + 충족 정보
  const stateChip = {
    ok: `<span class="match-state ok">✓ 조건 충족 · 접수 중</span>`,
    waiting: `<span class="match-state waiting">⏸ 접수 마감 · 다음 공고 대기</span>`,
    partial: `<span class="match-state warn">조건 충족률 ${Math.round(result.score * 100)}%</span>`,
  }[variant];

  // 관심 항목: 미충족 조건 배지 (+ 마감된 항목이면 마감 칩 추가)
  const failedBadges = variant === "partial"
    ? `<div class="failed-row">
         ${p.open ? "" : `<span class="chip chip-closed">접수 마감</span>`}
         ${result.failed.map((c) =>
           `<span class="failed-badge" title="${escapeHtml(c.hint)}">✕ ${escapeHtml(c.label)} 미충족 <span class="why">(${escapeHtml(c.hint)})</span></span>`
         ).join("")}
       </div>`
    : "";

  const linkLabel = variant === "ok" ? "자세히 보기 ↗" : "공고 확인하기 ↗";

  return `
    <article class="policy-card is-${variant}">
      <div class="tag-row">
        <span class="chip chip-type">${escapeHtml(TYPE_LABELS[p.type])}</span>
        <span class="chip chip-cat" style="--cat:${catColor}">${escapeHtml(p.category)}</span>
        <span class="chip chip-region">📍 ${escapeHtml(regionLabel)}</span>
        ${stateChip}
      </div>
      <h4>${escapeHtml(p.name)}</h4>
      <p class="policy-benefit">${escapeHtml(p.summary)}</p>
      <dl class="policy-meta">
        <div><dt>지원 대상</dt><dd>${escapeHtml(p.target)}</dd></div>
        <div><dt>신청 기한</dt><dd>${escapeHtml(p.deadline)}</dd></div>
        <div><dt>신청 방법</dt><dd>${escapeHtml(p.applyMethod)}</dd></div>
      </dl>
      ${failedBadges}
      <a class="card-link ${variant === "partial" ? "warn" : variant}" href="${escapeHtml(p.link)}" target="_blank" rel="noopener noreferrer"
         aria-label="${escapeHtml(p.name)} 상세 안내 새 창에서 보기">${linkLabel}</a>
    </article>`;
}

/** 현재 선택된 탭 기준으로 목록을 다시 그림 */
function renderLists() {
  const perfect = filterByType(lastMatch.perfect, activeType);
  const waiting = filterByType(lastMatch.waiting, activeType);
  const partial = filterByType(lastMatch.partial, activeType);

  $("#perfect-section").classList.toggle("hidden", perfect.length === 0);
  $("#perfect-list").innerHTML = perfect.map((r) => renderCard(r, "ok")).join("");

  $("#waiting-section").classList.toggle("hidden", waiting.length === 0);
  $("#waiting-list").innerHTML = waiting.map((r) => renderCard(r, "waiting")).join("");

  $("#partial-section").classList.toggle("hidden", partial.length === 0);
  $("#partial-list").innerHTML = partial.map((r) => renderCard(r, "partial")).join("");

  // 공모전 탭에서는 실시간 공모전 포털 안내 표시
  $("#contest-cta").classList.toggle("hidden", activeType !== "contest");

  $("#empty-state").classList.toggle("hidden", perfect.length + waiting.length + partial.length > 0);
}

/** 검색 직후 결과 영역 전체를 초기화하고 표시 */
function renderResults() {
  $("#results").classList.remove("hidden");
  $("#result-summary").textContent =
    `전체 ${itemsData.items.length}개 항목 중 바로 신청 가능 ${lastMatch.perfect.length}건, ` +
    `접수 대기 ${lastMatch.waiting.length}건, 관심 항목 ${lastMatch.partial.length}건을 찾았습니다.`;
  $("#data-note").textContent =
    `ℹ️ 정보 기준일 ${itemsData.verifiedAt}` +
    (itemsData.live ? " · 온통청년 API 연동 데이터 포함" : "") +
    ` — 실제 자격·기한·금액은 각 기관 공고를 반드시 확인하세요.`;

  renderTabs();
  renderLists();
  $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* ------------------------------------------------------------------ *
 * 6. 이벤트 바인딩 (제출 / 초기화)
 * ------------------------------------------------------------------ */

function initForm() {
  const form = $("#user-form");
  const errorEl = $("#form-error");

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    if (!form.checkValidity()) {
      errorEl.textContent = "⚠️ 모든 항목을 입력해 주세요. 빈 항목이 있습니다.";
      errorEl.classList.remove("hidden");
      form.querySelector(":invalid")?.focus();
      return;
    }
    errorEl.classList.add("hidden");

    lastMatch = matchItems(buildUserProfile(form), itemsData.items);
    activeType = "all"; // 새 검색은 항상 '전체' 탭부터
    renderResults();
  });

  form.addEventListener("reset", () => {
    errorEl.classList.add("hidden");
    $("#results").classList.add("hidden");
    lastMatch = null;
    activeType = "all";
    const sigunguSelect = $("#sigungu");
    sigunguSelect.innerHTML = '<option value="">시/도를 먼저 선택하세요</option>';
    sigunguSelect.disabled = true;
  });
}

/* ------------------------------------------------------------------ *
 * 7. 라이브 데이터 로드 (GitHub Actions가 매일 갱신하는 data/policies.json)
 * ------------------------------------------------------------------ *
 * 같은 오리진의 정적 JSON이라 CORS·키 노출 문제가 없습니다.
 * 로드 실패(file:// 실행, 네트워크 오류 등) 시 번들 데이터로 폴백합니다.
 * ------------------------------------------------------------------ */

async function loadLiveData() {
  try {
    const res = await fetch("data/policies.json", { cache: "no-store" });
    if (!res.ok) return;
    const json = await res.json();
    if (!Array.isArray(json.items) || json.items.length === 0) return;

    itemsData = {
      items: json.items,
      verifiedAt: (json.generatedAt || json.verifiedAt || DATA_VERIFIED_AT).slice(0, 10),
      live: String(json.source || "").includes("youthcenter"),
    };
    $("#footer-verified").textContent = itemsData.verifiedAt;

    // 이미 검색한 상태라면 새 데이터로 결과 갱신
    if (lastMatch) {
      lastMatch = matchItems(buildUserProfile($("#user-form")), itemsData.items);
      renderTabs();
      renderLists();
    }
  } catch (_) {
    /* 폴백: 번들 데이터(js/data.js) 그대로 사용 */
  }
}

/* ------------------------------------------------------------------ *
 * 8. 앱 시작
 * ------------------------------------------------------------------ */
initRegionSelects();
initTabs();
initForm();
loadLiveData();

// 푸터에 데이터 기준일 표시
document.getElementById("footer-verified").textContent = DATA_VERIFIED_AT;
